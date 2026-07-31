"""Ashby public job board adapter.

API: POST https://jobs.ashbyhq.com/api/non-user-graphql (GraphQL, no auth)
Two-pass fetch: brief list for all job IDs, then per-job detail for description
and published date (both unavailable in the board-level brief type).
"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

API_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"
JOB_BASE = "https://jobs.ashbyhq.com"
_BOM = chr(0xfeff)  # U+FEFF byte-order mark; escape avoids source-encoding ambiguity

_BRIEF_QUERY = (
    "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {"
    " jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {"
    " jobPostings { id title locationName workplaceType } } }"
)

_DETAIL_QUERY = (
    "query JobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {"
    " jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName,"
    " jobPostingId: $jobPostingId) {"
    " id title isListed locationName workplaceType"
    " descriptionHtml publishedDate compensationTierSummary } }"
)


@dataclass
class NormalizedPosting:
    external_id: str
    title: str
    location: str | None
    workplace_type: str | None
    level: str | None
    url: str
    jd_text: str | None
    posted_at: str | None


def _strip_html(content: str | None) -> str | None:
    if not content:
        return None
    text = html.unescape(content).replace(_BOM, "")
    return BeautifulSoup(text, "html.parser").get_text(separator="\n").strip()


def _infer_workplace(job: dict[str, Any]) -> str | None:
    wt = (job.get("workplaceType") or "").lower()
    if wt == "remote":
        return "remote"
    if wt == "hybrid":
        return "hybrid"
    return None


_LEVEL_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|group|head of product)\b",
    re.IGNORECASE,
)


def _infer_level(title: str) -> str | None:
    m = _LEVEL_RE.search(title)
    if not m:
        return None
    tok = m.group(1).lower().replace(".", "")
    if tok in {"sr", "senior"}:
        return "senior"
    if tok == "head of product":
        return "head"
    return tok


def normalize(job: dict[str, Any], slug: str) -> NormalizedPosting:
    title = job["title"].replace(_BOM, "")
    jd_parts: list[str] = []
    if comp := job.get("compensationTierSummary"):
        jd_parts.append(f"Compensation: {comp}")
    if body := _strip_html(job.get("descriptionHtml")):
        jd_parts.append(body)
    jd_text = "\n\n".join(jd_parts) or None

    return NormalizedPosting(
        external_id=str(job["id"]),
        title=title,
        location=job.get("locationName"),
        workplace_type=_infer_workplace(job),
        level=_infer_level(title),
        url=f"{JOB_BASE}/{slug}/{job['id']}",
        jd_text=jd_text,
        posted_at=job.get("publishedDate"),
    )


_DETAIL_DELAY = 0.15  # seconds between detail requests within a single fetch()
_MIN_INTERVAL = 1.0   # global floor between any two Ashby requests, across slugs
_last_request_at = 0.0


def _gql(client: httpx.Client, query: str, variables: dict[str, str],
          operation: str, timeout: float) -> dict[str, Any]:
    global _last_request_at
    for attempt in range(5):
        if _MIN_INTERVAL > 0:
            elapsed = time.monotonic() - _last_request_at
            if elapsed < _MIN_INTERVAL:
                time.sleep(_MIN_INTERVAL - elapsed)
        resp = client.post(
            API_URL,
            json={"operationName": operation, "variables": variables, "query": query},
            timeout=timeout,
        )
        _last_request_at = time.monotonic()
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()  # re-raise after exhausting retries
    return {}  # unreachable; satisfies type checker


def fetch(slug: str, *, client: httpx.Client | None = None,
          timeout: float = 30.0) -> list[NormalizedPosting]:
    own_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        # Pass 1: get all job IDs from the board brief
        board_data = _gql(
            client, _BRIEF_QUERY,
            {"organizationHostedJobsPageName": slug},
            "ApiJobBoardWithTeams", timeout,
        )
        board = (board_data.get("data") or {}).get("jobBoard")
        if not board:
            return []
        briefs = board.get("jobPostings") or []

        # Pass 2: fetch full details for each posting
        result: list[NormalizedPosting] = []
        for brief in briefs:
            job_id = brief["id"]
            detail_data = _gql(
                client, _DETAIL_QUERY,
                {"organizationHostedJobsPageName": slug, "jobPostingId": job_id},
                "JobPosting", timeout,
            )
            job = (detail_data.get("data") or {}).get("jobPosting")
            if job and job.get("isListed"):
                result.append(normalize(job, slug))
            time.sleep(_DETAIL_DELAY)
        return result
    finally:
        if own_client:
            client.close()
