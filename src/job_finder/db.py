"""SQLite schema, connection, and core CRUD helpers."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  ats_provider TEXT NOT NULL,
  ats_slug TEXT NOT NULL,
  careers_url TEXT,
  sector_tags TEXT,
  size_band TEXT,
  added_at TEXT NOT NULL,
  last_checked_at TEXT,
  UNIQUE(ats_provider, ats_slug)
);

CREATE TABLE IF NOT EXISTS postings (
  id INTEGER PRIMARY KEY,
  company_id INTEGER NOT NULL REFERENCES companies(id),
  external_id TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT,
  workplace_type TEXT,
  url TEXT NOT NULL,
  jd_text TEXT,
  posted_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  closed_at TEXT,
  applied_at TEXT,
  dismissed_at TEXT,
  hard_filter_verdict TEXT,
  UNIQUE(company_id, external_id)
);

CREATE TABLE IF NOT EXISTS extractions (
  posting_id INTEGER PRIMARY KEY REFERENCES postings(id),
  yoe_required INTEGER,
  yoe_confidence TEXT,
  comp_base_min INTEGER,
  comp_base_max INTEGER,
  comp_source TEXT,
  domain_tags TEXT,
  company_stage TEXT,
  people_management INTEGER,
  remote_us_ok INTEGER,
  onsite_days_per_week INTEGER,
  stretch_reason TEXT,
  extracted_at TEXT NOT NULL,
  model TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
  posting_id INTEGER PRIMARY KEY REFERENCES postings(id),
  domain_score INTEGER,
  stage_score INTEGER,
  comp_score INTEGER,
  total_score INTEGER,
  queue TEXT,
  scored_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_postings_company ON postings(company_id);
CREATE INDEX IF NOT EXISTS idx_postings_closed ON postings(closed_at);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # TRUNCATE, not the default DELETE: DELETE unlinks the rollback journal on
    # every commit, and a device-bridge mount blocks unlink. The commit then
    # fails and leaves a hot journal, which wedges the database for the next
    # reader because rollback also needs to delete it. TRUNCATE zeroes the
    # journal instead of removing it, so no unlink is ever required and the
    # rollback guarantee is unchanged. MEMORY would also avoid the file, at the
    # cost of crash-safety, which is not worth trading for the durable ledgers.
    conn.execute("PRAGMA journal_mode = TRUNCATE")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def mark_applied(conn: sqlite3.Connection, *, external_id: str) -> int:
    cur = conn.execute(
        "UPDATE postings SET applied_at = ?, dismissed_at = NULL WHERE external_id = ?",
        (now_iso(), external_id),
    )
    return cur.rowcount


def mark_dismissed(conn: sqlite3.Connection, *, external_id: str) -> int:
    cur = conn.execute(
        "UPDATE postings SET dismissed_at = ?, applied_at = NULL WHERE external_id = ?",
        (now_iso(), external_id),
    )
    return cur.rowcount


def unmark(conn: sqlite3.Connection, *, external_id: str) -> int:
    cur = conn.execute(
        "UPDATE postings SET applied_at = NULL, dismissed_at = NULL WHERE external_id = ?",
        (external_id,),
    )
    return cur.rowcount


def upsert_company(conn: sqlite3.Connection, *, name: str, ats_provider: str, ats_slug: str,
                   careers_url: str | None, sector_tags: list[str], size_band: str) -> int:
    row = conn.execute(
        "SELECT id FROM companies WHERE ats_provider = ? AND ats_slug = ?",
        (ats_provider, ats_slug),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE companies SET name = ?, careers_url = ?, sector_tags = ?, size_band = ?, last_checked_at = ? WHERE id = ?",
            (name, careers_url, json.dumps(sector_tags), size_band, now_iso(), row["id"]),
        )
        return row["id"]
    cur = conn.execute(
        "INSERT INTO companies (name, ats_provider, ats_slug, careers_url, sector_tags, size_band, added_at, last_checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, ats_provider, ats_slug, careers_url, json.dumps(sector_tags), size_band, now_iso(), now_iso()),
    )
    return cur.lastrowid


def upsert_posting(conn: sqlite3.Connection, *, company_id: int, external_id: str, title: str,
                   location: str | None, workplace_type: str | None,
                   url: str, jd_text: str | None, posted_at: str | None,
                   hard_filter_verdict: str) -> int:
    row = conn.execute(
        "SELECT id, closed_at FROM postings WHERE company_id = ? AND external_id = ?",
        (company_id, external_id),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE postings SET title = ?, location = ?, workplace_type = ?, url = ?, jd_text = ?, posted_at = COALESCE(?, posted_at), last_seen_at = ?, closed_at = NULL, hard_filter_verdict = ? WHERE id = ?",
            (title, location, workplace_type, url, jd_text, posted_at, now_iso(), hard_filter_verdict, row["id"]),
        )
        return row["id"]
    cur = conn.execute(
        "INSERT INTO postings (company_id, external_id, title, location, workplace_type, url, jd_text, posted_at, first_seen_at, last_seen_at, hard_filter_verdict) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (company_id, external_id, title, location, workplace_type, url, jd_text, posted_at, now_iso(), now_iso(), hard_filter_verdict),
    )
    return cur.lastrowid


def mark_closed_postings(conn: sqlite3.Connection, *, company_id: int,
                         seen_external_ids: set[str]) -> int:
    """Mark any open posting for this company not in seen_external_ids as closed."""
    placeholders = ",".join("?" * len(seen_external_ids)) if seen_external_ids else "''"
    params: list = [now_iso(), company_id, *seen_external_ids]
    sql = (
        "UPDATE postings SET closed_at = ? "
        "WHERE company_id = ? AND closed_at IS NULL "
        f"AND external_id NOT IN ({placeholders})"
    )
    cur = conn.execute(sql, params)
    return cur.rowcount
