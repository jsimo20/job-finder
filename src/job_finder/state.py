"""Durable local state: one SQLite database for everything personal.

data/state.db (gitignored) holds the tracked-company list, the no-auto-apply
blocklist, the applied and seen ledgers, and the digest archive. The repo
itself carries no personal or regional data; the pipeline runs locally on a
schedule, so nothing needs to round-trip through git or CI anymore.

data/jobs.db remains separate on purpose: it is ephemeral working state,
rebuilt from scratch by every pipeline run. state.db is the memory.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DEFAULT_STATE_DB = Path(__file__).resolve().parents[2] / "data" / "state.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  name TEXT PRIMARY KEY,
  ats_provider TEXT NOT NULL,
  ats_slug TEXT NOT NULL,
  careers_url TEXT,
  sector_tags TEXT,          -- JSON list
  size_band TEXT,
  -- Per-company staleness override, tighter than the global STALE_DAYS.
  -- Set it for high-volume boards worth watching but not worth re-reading:
  -- the digest then shows only postings newer than this many days.
  max_age_days INTEGER
);

CREATE TABLE IF NOT EXISTS no_auto_apply (
  name TEXT PRIMARY KEY,
  reason TEXT,
  added TEXT
);

CREATE TABLE IF NOT EXISTS applied (
  external_id TEXT PRIMARY KEY,
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  applied_at TEXT NOT NULL,
  source TEXT
);

CREATE TABLE IF NOT EXISTS seen (
  external_id TEXT PRIMARY KEY,
  first_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digests (
  date TEXT PRIMARY KEY,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was first created.
    CREATE TABLE IF NOT EXISTS is a no-op on an existing table, so new
    columns need an explicit ALTER."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(companies)")}
    if "max_age_days" not in have:
        conn.execute("ALTER TABLE companies ADD COLUMN max_age_days INTEGER")


@contextmanager
def connect(db_path: Path = DEFAULT_STATE_DB) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # TRUNCATE, not the default DELETE: DELETE unlinks the rollback journal on
    # every commit, and a device-bridge mount blocks unlink. The commit then
    # fails and leaves a hot journal, which wedges the database for the next
    # reader because rollback also needs to delete it. TRUNCATE zeroes the
    # journal instead of removing it, so no unlink is ever required and the
    # rollback guarantee is unchanged. MEMORY would also avoid the file, at the
    # cost of crash-safety, which is not worth trading for the durable ledgers.
    conn.execute("PRAGMA journal_mode = TRUNCATE")
    conn.executescript(SCHEMA)
    _migrate(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── Companies ────────────────────────────────────────────────────────────────

def list_companies(db_path: Path = DEFAULT_STATE_DB) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM companies ORDER BY name").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["sector_tags"] = json.loads(d["sector_tags"]) if d["sector_tags"] else []
        out.append(d)
    return out


def upsert_company(company: dict[str, Any], db_path: Path = DEFAULT_STATE_DB) -> None:
    if not company.get("name") or not company.get("ats_provider"):
        raise ValueError("company needs name and ats_provider")
    # Manual-tier companies have no pollable board, so the careers URL is the
    # only thing the digest can surface — require it instead of a slug.
    if company["ats_provider"] == "manual":
        if not company.get("careers_url"):
            raise ValueError("manual companies need careers_url")
    elif not company.get("ats_slug"):
        raise ValueError("company needs ats_slug")
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO companies (name, ats_provider, ats_slug, careers_url,
                                      sector_tags, size_band, max_age_days)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 ats_provider=excluded.ats_provider, ats_slug=excluded.ats_slug,
                 careers_url=excluded.careers_url, sector_tags=excluded.sector_tags,
                 size_band=excluded.size_band, max_age_days=excluded.max_age_days""",
            (company["name"], company["ats_provider"], company.get("ats_slug") or "",
             company.get("careers_url"), json.dumps(company.get("sector_tags") or []),
             company.get("size_band"), company.get("max_age_days")),
        )


def max_age_overrides(db_path: Path = DEFAULT_STATE_DB) -> dict[str, int]:
    """{lowercased company name: max_age_days} for companies that set one."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name, max_age_days FROM companies WHERE max_age_days IS NOT NULL"
        ).fetchall()
    return {r["name"].strip().lower(): int(r["max_age_days"]) for r in rows}


def remove_company(name: str, db_path: Path = DEFAULT_STATE_DB) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM companies WHERE lower(name) = lower(?)", (name,))
    return cur.rowcount > 0


def import_companies(path: Path, db_path: Path = DEFAULT_STATE_DB) -> int:
    """Merge companies from a JSON file (a bare list, or {companies: [...]},
    the shape both the old seed file and discover_companies.py emit)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data["companies"] if isinstance(data, dict) else data
    n = 0
    for row in rows:
        row = {k: v for k, v in row.items() if not k.startswith("_")}
        upsert_company(row, db_path)
        n += 1
    return n


def export_companies(path: Path, db_path: Path = DEFAULT_STATE_DB) -> int:
    rows = list_companies(db_path)
    Path(path).write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return len(rows)


# ── No-auto-apply blocklist ──────────────────────────────────────────────────

def list_no_auto(db_path: Path = DEFAULT_STATE_DB) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        return [dict(r) for r in
                conn.execute("SELECT * FROM no_auto_apply ORDER BY name").fetchall()]


def add_no_auto(name: str, reason: str = "", added: str = "",
                db_path: Path = DEFAULT_STATE_DB) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO no_auto_apply (name, reason, added) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET reason=excluded.reason",
            (name.strip(), reason, added))


def remove_no_auto(name: str, db_path: Path = DEFAULT_STATE_DB) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM no_auto_apply WHERE lower(name) = lower(?)", (name,))
    return cur.rowcount > 0


def is_no_auto(name: str, db_path: Path = DEFAULT_STATE_DB) -> bool:
    with connect(db_path) as conn:
        return conn.execute("SELECT 1 FROM no_auto_apply WHERE lower(name) = lower(?)",
                            (name,)).fetchone() is not None


# ── Digest archive ───────────────────────────────────────────────────────────

def save_digest(date: str, body: str, db_path: Path = DEFAULT_STATE_DB) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT INTO digests (date, body) VALUES (?, ?) "
                     "ON CONFLICT(date) DO UPDATE SET body=excluded.body",
                     (date, body))


def get_digest(date: str | None = None, db_path: Path = DEFAULT_STATE_DB) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        if date:
            row = conn.execute("SELECT * FROM digests WHERE date = ?", (date,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM digests ORDER BY date DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def list_digests(db_path: Path = DEFAULT_STATE_DB) -> list[str]:
    with connect(db_path) as conn:
        return [r["date"] for r in
                conn.execute("SELECT date FROM digests ORDER BY date").fetchall()]
