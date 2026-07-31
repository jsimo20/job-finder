"""Durable applied-log: the roles the user has applied to, across pipeline runs.

`data/jobs.db` is rebuilt from scratch every pipeline run, so its `applied_at`
flag can never persist — a role you applied to last week reappears in the next
digest. This append-only JSONL log fixes that. Unlike the outreach log, it is
**committed to the repo** (not gitignored) so the CI-generated digest can read
it and suppress roles already applied to. It also captures ad-hoc roles applied
to outside the pipeline (pasted URLs never in the seed set), which the DB never
knew about.

Keyed by `external_id` (gh_jid for Greenhouse, slug for Lever, id for Ashby) —
the same key `mark-applied` and the postings table use.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

DEFAULT_APPLIED_PATH = Path(__file__).resolve().parents[2] / "data" / "applied.jsonl"


def _norm_url(url: str | None) -> str | None:
    """Normalize a URL for loose matching: drop scheme, query string, and
    trailing slash, lowercase. So an `/apply` form URL with `?gh_src=...` matches
    the plain posting URL of the same role."""
    if not url:
        return None
    u = url.strip().lower()
    u = u.split("://", 1)[-1]
    u = u.split("?", 1)[0].split("#", 1)[0]
    u = u.rstrip("/")
    for suffix in ("/application", "/apply"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
            break
    return u or None


def record_applied(
    external_id: str,
    *,
    company: str,
    title: str,
    url: str | None = None,
    applied_on: str | None = None,
    source: str = "manual",
    path: Path = DEFAULT_APPLIED_PATH,
) -> dict[str, Any] | None:
    """Append one applied record, keyed by external_id. Idempotent: returns the
    new record, or None if this external_id is already logged."""
    external_id = str(external_id).strip()
    company = company.strip()
    title = title.strip()
    if not external_id or not company or not title:
        raise ValueError("external_id, company, and title are all required")
    if is_applied(external_id=external_id, path=path):
        return None

    record = {
        "external_id": external_id,
        "company": company,
        "title": title,
        "url": url.strip() if url else None,
        "applied_at": applied_on or date.today().isoformat(),
        "source": source,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_applied(*, company: str | None = None, path: Path = DEFAULT_APPLIED_PATH) -> list[dict[str, Any]]:
    """Return applied records, oldest first. Filter by company (case-insensitive substring)."""
    if not path.exists():
        return []
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if company:
        needle = company.strip().lower()
        records = [r for r in records if needle in r.get("company", "").lower()]
    records.sort(key=lambda r: r.get("applied_at", ""))
    return records


def applied_external_ids(*, path: Path = DEFAULT_APPLIED_PATH) -> set[str]:
    """The set of applied external_ids — used by the digest to suppress rows."""
    return {r["external_id"] for r in list_applied(path=path) if r.get("external_id")}


def _norm_title(title: str | None) -> str | None:
    """Lowercase, punctuation-free, whitespace-collapsed — so 'Senior PM -
    AI Data Foundation' and 'Senior PM, AI Data Foundation' compare equal."""
    if not title:
        return None
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() or None


def applied_company_titles(*, path: Path = DEFAULT_APPLIED_PATH) -> set[tuple[str, str]]:
    """(company, normalized title) pairs for repost suppression.

    A reposted req gets a fresh external_id (observed live), so the id-keyed
    check alone lets an applied role resurface in the digest. Same company + same
    title is treated as the same application.
    """
    pairs = set()
    for r in list_applied(path=path):
        company = (r.get("company") or "").strip().lower()
        title = _norm_title(r.get("title"))
        if company and title:
            pairs.add((company, title))
    return pairs


def is_applied(
    *,
    external_id: str | None = None,
    url: str | None = None,
    path: Path = DEFAULT_APPLIED_PATH,
) -> bool:
    """True if we've logged an application matching this external_id or URL."""
    records = list_applied(path=path)
    if external_id:
        eid = str(external_id).strip()
        if any(r.get("external_id") == eid for r in records):
            return True
    if url:
        target = _norm_url(url)
        if target and any(_norm_url(r.get("url")) == target for r in records):
            return True
    return False


def remove_applied(external_id: str, *, path: Path = DEFAULT_APPLIED_PATH) -> dict[str, Any] | None:
    """Remove the record for external_id (e.g. a role you decided not to submit).
    Returns the removed record, or None if there was no match."""
    if not path.exists():
        return None
    eid = str(external_id).strip()
    kept: list[dict[str, Any]] = []
    removed: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if record.get("external_id") == eid and removed is None:
            removed = record
        else:
            kept.append(record)
    if removed is not None:
        with path.open("w", encoding="utf-8") as f:
            for record in kept:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return removed


def format_applied(records: Iterable[dict[str, Any]]) -> str:
    """Render applied records grouped by company for terminal display."""
    records = list(records)
    if not records:
        return "No applications logged yet."

    by_company: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_company.setdefault(r.get("company", "?"), []).append(r)

    lines: list[str] = []
    for company in sorted(by_company):
        lines.append(f"\n{company}")
        for r in sorted(by_company[company], key=lambda x: x.get("applied_at", "")):
            line = f"  {r.get('applied_at', '?')}  {r.get('title', '?')}  [{r.get('external_id', '?')}]"
            if r.get("source") and r["source"] != "manual":
                line += f"  ({r['source']})"
            lines.append(line)

    total = len(records)
    lines.append(f"\n{total} application{'s' if total != 1 else ''} across {len(by_company)} company(ies).")
    return "\n".join(lines).lstrip("\n")
