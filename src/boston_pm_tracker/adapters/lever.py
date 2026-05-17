"""Lever public postings adapter.

API: GET https://api.lever.co/v0/postings/{slug}?mode=json
Returns published postings. No auth required.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

API_BASE = "https://api.lever.co/v0/postings"


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
    raw_json: dict[str, Any]


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


def _infer_workplace(posting: dict[str, Any]) -> str | None:
    workplace = (posting.get("workplaceType") or "").lower()
    if workplace in {"remote", "hybrid", "on-site", "onsite"}:
        return "onsite" if workplace in {"on-site", "onsite"} else workplace
    categories = posting.get("categories") or {}
    loc = (categories.get("location") or "").lower()
    if "remote" in loc:
        return "remote"
    if "hybrid" in loc:
        return "hybrid"
    return None


def _jd_text(posting: dict[str, Any]) -> str | None:
    parts: list[str] = []
    if desc := posting.get("descriptionPlain"):
        parts.append(desc)
    for section in posting.get("lists", []) or []:
        title = section.get("text") or ""
        content = section.get("content") or ""
        parts.append(title)
        parts.append(content)
    if extra := posting.get("additionalPlain"):
        parts.append(extra)
    txt = "\n".join(p for p in parts if p).strip()
    return txt or None


def normalize(posting: dict[str, Any]) -> NormalizedPosting:
    categories = posting.get("categories") or {}
    # Lever's createdAt is epoch milliseconds. Convert to ISO so all adapters
    # produce comparable strings.
    posted_at = None
    if created := posting.get("createdAt"):
        from datetime import datetime, timezone
        try:
            posted_at = datetime.fromtimestamp(int(created) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
        except (ValueError, TypeError, OSError):
            posted_at = None
    return NormalizedPosting(
        external_id=str(posting["id"]),
        title=posting["text"],
        location=categories.get("location"),
        workplace_type=_infer_workplace(posting),
        level=_infer_level(posting["text"]),
        url=posting["hostedUrl"],
        jd_text=_jd_text(posting),
        posted_at=posted_at,
        raw_json=posting,
    )


def fetch(slug: str, *, client: httpx.Client | None = None,
          timeout: float = 30.0) -> list[NormalizedPosting]:
    own_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        url = f"{API_BASE}/{slug}?mode=json"
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()
        return [normalize(p) for p in payload]
    finally:
        if own_client:
            client.close()
