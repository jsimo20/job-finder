"""Collect: fetch each tracked company's ATS feed, normalize, apply Stage 1 filter, upsert into DB."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from . import db, state
from .adapters import DETAIL_REGISTRY, REGISTRY
from .filter import stage1

logger = logging.getLogger(__name__)


def load_companies(state_db: Path = state.DEFAULT_STATE_DB) -> list[dict]:
    """Tracked companies from state.db. `job-finder companies import <json>`
    populates it; an empty list is a setup problem, so say so loudly."""
    companies = state.list_companies(state_db)
    if not companies:
        logger.warning("no tracked companies in %s — run "
                       "`job-finder companies import <file.json>` (SETUP.md §5)",
                       state_db)
    return companies


def run(state_db: Path = state.DEFAULT_STATE_DB, db_path: Path = db.DEFAULT_DB_PATH) -> dict:
    companies = load_companies(state_db)
    stats = {"companies": 0, "fetched": 0, "kept": 0, "discarded": 0, "errors": 0, "errors_detail": []}

    with db.connect(db_path) as conn, httpx.Client(timeout=30.0) as client:
        for company in companies:
            stats["companies"] += 1
            provider = company["ats_provider"]
            slug = company["ats_slug"]
            if provider == "manual":
                # No pollable board; the digest lists these for a hand check.
                stats["manual"] = stats.get("manual", 0) + 1
                continue
            fetcher = REGISTRY.get(provider)
            if not fetcher:
                logger.warning("no adapter for provider=%s slug=%s", provider, slug)
                stats["errors"] += 1
                stats["errors_detail"].append(f"{company['name']}: no adapter for {provider}")
                continue

            company_id = db.upsert_company(
                conn,
                name=company["name"],
                ats_provider=provider,
                ats_slug=slug,
                careers_url=company.get("careers_url"),
                sector_tags=company.get("sector_tags", []),
                size_band=company.get("size_band", "unknown"),
            )

            try:
                postings = fetcher(slug, client=client)
            except httpx.HTTPError as e:
                logger.error("fetch failed company=%s err=%s", company["name"], e)
                stats["errors"] += 1
                stats["errors_detail"].append(f"{company['name']}: {e}")
                continue

            detail_fetcher = DETAIL_REGISTRY.get(provider)
            seen_ids: set[str] = set()
            for p in postings:
                stats["fetched"] += 1
                seen_ids.add(p.external_id)
                verdict = stage1(
                    title=p.title,
                    location=p.location,
                    workplace_type=p.workplace_type,
                )
                if verdict.keep:
                    stats["kept"] += 1
                    # Detail-only providers ship the JD separately; fetch it
                    # for survivors only. On failure the posting stays kept
                    # with jd_text NULL, which extract counts as skipped.
                    if detail_fetcher and p.jd_text is None and p.detail_ref:
                        try:
                            detail = detail_fetcher(slug, p.detail_ref, client=client)
                            p.jd_text = detail["jd_text"]
                            p.posted_at = detail["posted_at"] or p.posted_at
                        except httpx.HTTPError as e:
                            logger.error("detail fetch failed company=%s ref=%s err=%s",
                                         company["name"], p.detail_ref, e)
                            stats["errors"] += 1
                            stats["errors_detail"].append(
                                f"{company['name']} detail {p.detail_ref}: {e}")
                else:
                    stats["discarded"] += 1
                db.upsert_posting(
                    conn,
                    company_id=company_id,
                    external_id=p.external_id,
                    title=p.title,
                    location=p.location,
                    workplace_type=p.workplace_type,
                    url=p.url,
                    jd_text=p.jd_text,
                    posted_at=p.posted_at,
                    hard_filter_verdict=verdict.reason,
                )

            closed = db.mark_closed_postings(conn, company_id=company_id, seen_external_ids=seen_ids)
            stats.setdefault("closed", 0)
            stats["closed"] += closed

    return stats
