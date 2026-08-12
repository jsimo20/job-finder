"""Workday CXS adapter.

Workday exposes an unauthenticated JSON API behind every public job board:

  POST https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
  GET  https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{externalPath}

The slug encodes all three board coordinates as "tenant/wdN/site" (read them
off the careers URL, e.g. examplecorp.wd1.myworkdayjobs.com/External →
"examplecorp/wd1/External").

The list payload carries no job description, and big tenants post thousands of
roles, so fetch() returns jd_text=None with a detail_ref; collect fetches the
detail only for postings that survive Stage 1.
"""
from __future__ import annotations

import html
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .base import NormalizedPosting

logger = logging.getLogger(__name__)

_BOM = chr(0xfeff)
_PAGE_LIMIT = 20          # the CXS jobs endpoint caps limit at 20
_MAX_POSTINGS = 5000      # runaway-pagination backstop


def _parse_slug(slug: str) -> tuple[str, str, str]:
    parts = slug.split("/")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"workday slug must be tenant/wdN/site, got {slug!r}")
    return parts[0], parts[1], parts[2]


def _strip_html(content: str | None) -> str | None:
    if not content:
        return None
    text = html.unescape(content).replace(_BOM, "")
    return BeautifulSoup(text, "html.parser").get_text(separator="\n").strip()


def _external_id(job: dict[str, Any]) -> str:
    # bulletFields[0] is the requisition id (stable across reposts of the same
    # req); the externalPath tail carries the same id as a suffix fallback.
    bullets = job.get("bulletFields") or []
    if bullets and bullets[0]:
        return str(bullets[0])
    return str(job["externalPath"]).rsplit("_", 1)[-1]


def _infer_workplace(job: dict[str, Any]) -> str | None:
    blob = (job.get("locationsText") or "").lower()
    if "remote" in blob:
        return "remote"
    if "hybrid" in blob:
        return "hybrid"
    return None


def normalize(job: dict[str, Any], slug: str) -> NormalizedPosting:
    tenant, instance, site = _parse_slug(slug)
    path = job["externalPath"]
    return NormalizedPosting(
        external_id=_external_id(job),
        title=job["title"].replace(_BOM, ""),
        location=job.get("locationsText"),
        workplace_type=_infer_workplace(job),
        url=f"https://{tenant}.{instance}.myworkdayjobs.com/{site}{path}",
        # The list payload has no description and "postedOn" is relative text
        # ("Posted Today"); both come from the detail fetch for kept postings.
        jd_text=None,
        posted_at=None,
        detail_ref=path,
    )


def fetch(slug: str, *, client: httpx.Client | None = None,
          timeout: float = 30.0) -> list[NormalizedPosting]:
    tenant, instance, site = _parse_slug(slug)
    url = f"https://{tenant}.{instance}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    own_client = client is None
    client = client or httpx.Client(timeout=timeout)
    postings: list[NormalizedPosting] = []
    try:
        offset = 0
        while offset < _MAX_POSTINGS:
            resp = client.post(url, json={"appliedFacets": {}, "limit": _PAGE_LIMIT,
                                          "offset": offset, "searchText": ""})
            resp.raise_for_status()
            payload = resp.json()
            page = payload.get("jobPostings", [])
            if not page:
                break
            for j in page:
                if not (j.get("externalPath") and j.get("title")):
                    logger.warning("skipping malformed posting slug=%s entry=%.120s",
                                   slug, j)
                    continue
                postings.append(normalize(j, slug))
            offset += len(page)
            # The empty-page check above is the real terminator; total is only
            # an early exit, so a missing key must not truncate the board.
            total = payload.get("total")
            if total is not None and offset >= total:
                break
        return postings
    finally:
        if own_client:
            client.close()


def fetch_detail(slug: str, detail_ref: str, *, client: httpx.Client | None = None,
                 timeout: float = 30.0) -> dict[str, str | None]:
    """JD text and posting date for one posting; called for kept postings only."""
    tenant, instance, site = _parse_slug(slug)
    url = f"https://{tenant}.{instance}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{detail_ref}"
    own_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        resp = client.get(url, headers={"Accept": "application/json"})
        resp.raise_for_status()
        info = resp.json().get("jobPostingInfo", {})
        return {
            "jd_text": _strip_html(info.get("jobDescription")),
            "posted_at": info.get("startDate"),
        }
    finally:
        if own_client:
            client.close()
