"""Durable applied-log: the roles the user has applied to, across pipeline runs.

data/jobs.db is rebuilt from scratch every pipeline run, so its applied_at
flag can never persist. This table in data/state.db (gitignored, local-only)
is the durable record; the digest reads it to suppress roles already applied
to, including ad-hoc roles the pipeline never tracked.

Keyed by external_id (gh_jid for Greenhouse, slug for Lever, id for Ashby) —
the same key mark-applied and the postings table use.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from . import state

DEFAULT_STATE_DB = state.DEFAULT_STATE_DB


def _norm_url(url: str | None) -> str | None:
    """Normalize a URL for loose matching: drop scheme, query string, and
    trailing slash, lowercase. So an /apply form URL with tracking params
    matches the plain posting URL of the same role."""
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


def _norm_title(title: str | None) -> str | None:
    """Lowercase, punctuation-free, whitespace-collapsed — so 'Senior PM -
    AI Data Foundation' and 'Senior PM, AI Data Foundation' compare equal."""
    if not title:
        return None
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() or None


def record_applied(
    external_id: str,
    *,
    company: str,
    title: str,
    url: str | None = None,
    applied_on: str | None = None,
    source: str = "manual",
    db_path: Path = DEFAULT_STATE_DB,
) -> dict[str, Any] | None:
    """Insert one applied record. Idempotent: returns the new record, or None
    if this external_id is already logged."""
    external_id = str(external_id).strip()
    company = company.strip()
    title = title.strip()
    if not external_id or not company or not title:
        raise ValueError("external_id, company, and title are all required")
    if is_applied(external_id=external_id, db_path=db_path):
        return None

    record = {
        "external_id": external_id,
        "company": company,
        "title": title,
        "url": url.strip() if url else None,
        "applied_at": applied_on or date.today().isoformat(),
        "source": source,
    }
    with state.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO applied (external_id, company, title, url, applied_at, source) "
            "VALUES (:external_id, :company, :title, :url, :applied_at, :source)",
            record,
        )
    return record


def list_applied(*, company: str | None = None,
                 db_path: Path = DEFAULT_STATE_DB) -> list[dict[str, Any]]:
    """Applied records, oldest first. Filter by company (case-insensitive substring)."""
    with state.connect(db_path) as conn:
        rows = [dict(r) for r in
                conn.execute("SELECT * FROM applied ORDER BY applied_at, external_id").fetchall()]
    if company:
        needle = company.strip().lower()
        rows = [r for r in rows if needle in (r.get("company") or "").lower()]
    return rows


def applied_external_ids(*, db_path: Path = DEFAULT_STATE_DB) -> set[str]:
    """The set of applied external_ids — used by the digest to suppress rows."""
    with state.connect(db_path) as conn:
        return {r["external_id"] for r in
                conn.execute("SELECT external_id FROM applied").fetchall()}


def applied_company_titles(*, db_path: Path = DEFAULT_STATE_DB) -> set[tuple[str, str]]:
    """(company, normalized title) pairs for repost suppression.

    A reposted req gets a fresh external_id (observed live), so the id-keyed
    check alone lets an applied role resurface in the digest. Same company +
    same title is treated as the same application.
    """
    pairs = set()
    for r in list_applied(db_path=db_path):
        company = (r.get("company") or "").strip().lower()
        title = _norm_title(r.get("title"))
        if company and title:
            pairs.add((company, title))
    return pairs


def drop_applied(rows: Iterable[Any], *,
                 db_path: Path = DEFAULT_STATE_DB) -> list[Any]:
    """Remove rows for roles already applied to, by external_id or by reposted
    (company, title).

    Any query against jobs.db that means "roles still to apply to" has to end
    here. Its own `postings.applied_at` cannot answer the question: jobs.db is
    rebuilt from scratch every pipeline run, so the column is NULL for every
    row that predates the current run, and a role applied to last month reads
    as pending. Filtering on it is what put two duplicate applications in on
    2026-08-31.

    Rows need `external_id`, `company_name` and `title`; sqlite3.Row and dict
    both work.
    """
    applied_ids = applied_external_ids(db_path=db_path)
    applied_pairs = applied_company_titles(db_path=db_path)
    return [
        r for r in rows
        if r["external_id"] not in applied_ids
        and ((r["company_name"] or "").strip().lower(),
             _norm_title(r["title"])) not in applied_pairs
    ]


def is_applied(
    *,
    external_id: str | None = None,
    url: str | None = None,
    db_path: Path = DEFAULT_STATE_DB,
) -> bool:
    """True if an application matching this external_id or URL is logged."""
    if external_id:
        eid = str(external_id).strip()
        with state.connect(db_path) as conn:
            if conn.execute("SELECT 1 FROM applied WHERE external_id = ?",
                            (eid,)).fetchone():
                return True
    if url:
        target = _norm_url(url)
        if target and any(_norm_url(r.get("url")) == target
                          for r in list_applied(db_path=db_path)):
            return True
    return False


def remove_applied(external_id: str, *,
                   db_path: Path = DEFAULT_STATE_DB) -> dict[str, Any] | None:
    """Remove the record for external_id (e.g. a role you decided not to
    submit). Returns the removed record, or None if there was no match."""
    eid = str(external_id).strip()
    with state.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM applied WHERE external_id = ?", (eid,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM applied WHERE external_id = ?", (eid,))
        return dict(row)


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
