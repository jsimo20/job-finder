"""Ashby public job board adapter.

API: POST https://jobs.ashbyhq.com/api/non-user-graphql (GraphQL, no auth)

The board-level brief type carries no description or published date, so those
come from a per-posting detail query. fetch() returns the brief pass only, with
a detail_ref; collect calls fetch_detail() for postings that survive Stage 1,
which is what keeps a 138-role board at one request instead of 139.
"""
from __future__ import annotations

import html
import threading
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .base import NormalizedPosting

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


def normalize(job: dict[str, Any], slug: str) -> NormalizedPosting:
    """One entry of the board brief. The brief type has no description or
    publishedDate, so both arrive later via fetch_detail()."""
    return NormalizedPosting(
        external_id=str(job["id"]),
        title=job["title"].replace(_BOM, ""),
        location=job.get("locationName"),
        workplace_type=_infer_workplace(job),
        url=f"{JOB_BASE}/{slug}/{job['id']}",
        jd_text=None,
        posted_at=None,
        detail_ref=str(job["id"]),
    )


_MIN_INTERVAL = 1.0   # global floor between any two Ashby requests, across slugs
_pace_lock = threading.Lock()
_last_request_at = 0.0


def _pace() -> None:
    """Space out Ashby request starts across every collect worker thread.

    Collect fans companies out over a thread pool. Reading and writing the
    timestamp without the lock let every worker observe the same value, sleep
    the same amount and then fire together, so the floor held within a thread
    and not at all across them. The stamp is taken before the request, because
    what the far end rate-limits is arrival, not completion.
    """
    global _last_request_at
    if _MIN_INTERVAL <= 0:
        return
    with _pace_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_request_at = time.monotonic()


def _gql(client: httpx.Client, query: str, variables: dict[str, str],
         operation: str, timeout: float) -> dict[str, Any]:
    for attempt in range(5):
        _pace()
        resp = client.post(
            API_URL,
            json={"operationName": operation, "variables": variables, "query": query},
            timeout=timeout,
        )
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
        board_data = _gql(
            client, _BRIEF_QUERY,
            {"organizationHostedJobsPageName": slug},
            "ApiJobBoardWithTeams", timeout,
        )
        board = (board_data.get("data") or {}).get("jobBoard")
        if not board:
            return []
        return [normalize(b, slug) for b in board.get("jobPostings") or []]
    finally:
        if own_client:
            client.close()


def fetch_detail(slug: str, detail_ref: str, *, client: httpx.Client | None = None,
                 timeout: float = 30.0) -> dict[str, str | None]:
    """JD text and posting date for one posting; called for kept postings only."""
    own_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        data = _gql(
            client, _DETAIL_QUERY,
            {"organizationHostedJobsPageName": slug, "jobPostingId": detail_ref},
            "JobPosting", timeout,
        )
        job = (data.get("data") or {}).get("jobPosting")
        # The public board brief only carries listed postings, so an unlisted
        # one here means it closed between the two passes.
        if not job or not job.get("isListed"):
            return {"jd_text": None, "posted_at": None}

        parts: list[str] = []
        if comp := job.get("compensationTierSummary"):
            parts.append(f"Compensation: {comp}")
        if body := _strip_html(job.get("descriptionHtml")):
            parts.append(body)
        return {
            "jd_text": "\n\n".join(parts) or None,
            "posted_at": job.get("publishedDate"),
        }
    finally:
        if own_client:
            client.close()
