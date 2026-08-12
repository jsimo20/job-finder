"""The normalized posting shape every adapter's fetch() returns."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NormalizedPosting:
    external_id: str
    title: str
    location: str | None
    workplace_type: str | None
    url: str
    jd_text: str | None
    posted_at: str | None
    # Adapters whose list payload has no JD (Workday) set this to the opaque
    # reference their fetch_detail() needs; collect enriches kept postings only.
    detail_ref: str | None = None
