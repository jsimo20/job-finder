"""Collect: fetch each seeded company's ATS feed, normalize, apply Stage 1 filter, upsert into DB."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from . import db
from .adapters import REGISTRY
from .filter import stage1

logger = logging.getLogger(__name__)

DEFAULT_SEEDS = Path(__file__).resolve().parents[2] / "seeds" / "companies.json"


def load_seeds(seeds_path: Path = DEFAULT_SEEDS) -> list[dict]:
    return json.loads(seeds_path.read_text(encoding="utf-8"))


def run(seeds_path: Path = DEFAULT_SEEDS, db_path: Path = db.DEFAULT_DB_PATH) -> dict:
    seeds = load_seeds(seeds_path)
    stats = {"companies": 0, "fetched": 0, "kept": 0, "discarded": 0, "errors": 0, "errors_detail": []}

    with db.connect(db_path) as conn, httpx.Client(timeout=30.0) as client:
        for seed in seeds:
            stats["companies"] += 1
            provider = seed["ats_provider"]
            slug = seed["ats_slug"]
            fetcher = REGISTRY.get(provider)
            if not fetcher:
                logger.warning("no adapter for provider=%s slug=%s", provider, slug)
                stats["errors"] += 1
                stats["errors_detail"].append(f"{seed['name']}: no adapter for {provider}")
                continue

            company_id = db.upsert_company(
                conn,
                name=seed["name"],
                ats_provider=provider,
                ats_slug=slug,
                careers_url=seed.get("careers_url"),
                sector_tags=seed.get("sector_tags", []),
                size_band=seed.get("size_band", "unknown"),
            )

            try:
                postings = fetcher(slug, client=client)
            except httpx.HTTPError as e:
                logger.error("fetch failed company=%s err=%s", seed["name"], e)
                stats["errors"] += 1
                stats["errors_detail"].append(f"{seed['name']}: {e}")
                continue

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
                else:
                    stats["discarded"] += 1
                db.upsert_posting(
                    conn,
                    company_id=company_id,
                    external_id=p.external_id,
                    title=p.title,
                    location=p.location,
                    workplace_type=p.workplace_type,
                    level=p.level,
                    url=p.url,
                    jd_text=p.jd_text,
                    raw_json=p.raw_json,
                    posted_at=p.posted_at,
                    hard_filter_verdict=verdict.reason,
                )

            closed = db.mark_closed_postings(conn, company_id=company_id, seen_external_ids=seen_ids)
            stats.setdefault("closed", 0)
            stats["closed"] += closed

    return stats
