"""Greenhouse public board adapter.

API: GET https://api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Returns published jobs with full content. No auth required.
"""
from __future__ import annotations

import html
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .base import NormalizedPosting

API_BASE = "https://api.greenhouse.io/v1/boards"


def _strip_html(content: str | None) -> str | None:
    if not content:
        return None
    text = html.unescape(content)
    return BeautifulSoup(text, "html.parser").get_text(separator="\n").strip()


def _infer_workplace(job: dict[str, Any]) -> str | None:
    blob = (job.get("location", {}).get("name") or "").lower()
    if "remote" in blob:
        return "remote"
    if "hybrid" in blob:
        return "hybrid"
    return None


def normalize(job: dict[str, Any]) -> NormalizedPosting:
    # Greenhouse's `updated_at` tracks the last edit; `first_published` (when present)
    # is the original post date. Prefer first_published to avoid resetting age on minor edits.
    posted_at = job.get("first_published") or job.get("updated_at")
    return NormalizedPosting(
        external_id=str(job["id"]),
        title=job["title"],
        location=(job.get("location") or {}).get("name"),
        workplace_type=_infer_workplace(job),
        url=job["absolute_url"],
        jd_text=_strip_html(job.get("content")),
        posted_at=posted_at,
    )


def fetch(slug: str, *, client: httpx.Client | None = None,
          timeout: float = 30.0) -> list[NormalizedPosting]:
    own_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        url = f"{API_BASE}/{slug}/jobs?content=true"
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()
        return [normalize(j) for j in payload.get("jobs", [])]
    finally:
        if own_client:
            client.close()
