"""Collect: fetch each tracked company's ATS feed, normalize, apply Stage 1 filter, upsert into DB."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from . import db, state
from .adapters import DETAIL_REGISTRY, REGISTRY
from .filter import stage1

logger = logging.getLogger(__name__)

# Companies whose feeds are fetched at once. Collect is entirely network-bound,
# so serial fetching scaled with the tracked-company count until it stopped
# fitting the scheduled task's 2h ExecutionTimeLimit and the run was killed
# mid-extract. Threads rather than asyncio because every adapter is sync httpx.
DEFAULT_MAX_WORKERS = 8

# Futures in flight at once, as a multiple of the worker count. Results carry
# full JD text for every posting on a board, so completed-but-unconsumed
# results have to stay bounded rather than accumulating across all companies.
_WINDOW_MULTIPLE = 4


def load_companies(state_db: Path = state.DEFAULT_STATE_DB) -> list[dict]:
    """Tracked companies from state.db. `job-finder companies import <json>`
    populates it; an empty list is a setup problem, so say so loudly."""
    companies = state.list_companies(state_db)
    if not companies:
        logger.warning("no tracked companies in %s — run "
                       "`job-finder companies import <file.json>` (SETUP.md §5)",
                       state_db)
    return companies


def _fetch_company(company: dict, client: httpx.Client) -> dict:
    """Network half of one company's collect, run off the main thread.

    Returns a plain result dict; touches no shared state and writes nothing, so
    the caller can apply every DB write and stat update serially.
    """
    slug = company["ats_slug"]
    result: dict = {"company": company, "rows": [], "error": None, "detail_errors": []}

    try:
        postings = REGISTRY[company["ats_provider"]](slug, client=client)
    # ValueError covers JSONDecodeError: a WAF page or rate-limit interstitial
    # served with a 200 must skip this company, not abort the run.
    except (httpx.HTTPError, ValueError) as e:
        result["error"] = str(e)
        return result

    detail_fetcher = DETAIL_REGISTRY.get(company["ats_provider"])
    for p in postings:
        verdict = stage1(title=p.title, location=p.location, workplace_type=p.workplace_type)
        # Detail-only providers ship the JD separately; fetch it for survivors
        # only. On failure the posting stays kept with jd_text NULL, which
        # extract counts as skipped.
        if verdict.keep and detail_fetcher and p.jd_text is None and p.detail_ref:
            try:
                detail = detail_fetcher(slug, p.detail_ref, client=client)
                p.jd_text = detail["jd_text"]
                p.posted_at = detail["posted_at"] or p.posted_at
            # Any per-posting failure (HTTP, non-JSON body, shape change)
            # degrades to jd_text NULL — never a lost run.
            except Exception as e:
                result["detail_errors"].append(f"{p.detail_ref}: {e}")
        result["rows"].append((p, verdict))
    return result


def _apply_result(conn, result: dict, stats: dict) -> None:
    """Serial half: every DB write and stat mutation happens here, one thread."""
    company = result["company"]
    company_id = db.upsert_company(
        conn,
        name=company["name"],
        ats_provider=company["ats_provider"],
        ats_slug=company["ats_slug"],
        careers_url=company.get("careers_url"),
        sector_tags=company.get("sector_tags", []),
        size_band=company.get("size_band", "unknown"),
    )

    if result["error"]:
        logger.error("fetch failed company=%s err=%s", company["name"], result["error"])
        stats["errors"] += 1
        stats["errors_detail"].append(f"{company['name']}: {result['error']}")
        return

    for detail_error in result["detail_errors"]:
        logger.error("detail fetch failed company=%s %s", company["name"], detail_error)
        stats["errors"] += 1
        stats["errors_detail"].append(f"{company['name']} detail {detail_error}")

    seen_ids: set[str] = set()
    for p, verdict in result["rows"]:
        stats["fetched"] += 1
        seen_ids.add(p.external_id)
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
            url=p.url,
            jd_text=p.jd_text,
            posted_at=p.posted_at,
            hard_filter_verdict=verdict.reason,
        )

    stats["closed"] += db.mark_closed_postings(
        conn, company_id=company_id, seen_external_ids=seen_ids)


def run(state_db: Path = state.DEFAULT_STATE_DB, db_path: Path = db.DEFAULT_DB_PATH,
        max_workers: int = DEFAULT_MAX_WORKERS) -> dict:
    companies = load_companies(state_db)
    stats = {"companies": 0, "fetched": 0, "kept": 0, "discarded": 0, "manual": 0,
             "errors": 0, "errors_detail": [], "closed": 0}

    pollable: list[dict] = []
    for company in companies:
        stats["companies"] += 1
        provider = company["ats_provider"]
        if provider == "manual":
            # No pollable board; the digest lists these for a hand check.
            stats["manual"] += 1
        elif provider not in REGISTRY:
            logger.warning("no adapter for provider=%s slug=%s", provider, company["ats_slug"])
            stats["errors"] += 1
            stats["errors_detail"].append(f"{company['name']}: no adapter for {provider}")
        else:
            pollable.append(company)

    with db.connect(db_path) as conn, httpx.Client(timeout=30.0) as client, \
            ThreadPoolExecutor(max_workers=max_workers) as pool:
        window = max_workers * _WINDOW_MULTIPLE
        for start in range(0, len(pollable), window):
            batch = pollable[start:start + window]
            futures = {pool.submit(_fetch_company, c, client): c for c in batch}
            for future in as_completed(futures):
                try:
                    result = future.result()
                # An adapter raising something unexpected used to cost one
                # company; concurrently it would also discard every sibling
                # still in flight, so it degrades to a per-company error.
                except Exception as e:
                    company = futures[future]
                    logger.error("fetch failed company=%s err=%s", company["name"], e)
                    stats["errors"] += 1
                    stats["errors_detail"].append(f"{company['name']}: {e}")
                    continue
                _apply_result(conn, result, stats)

    return stats
