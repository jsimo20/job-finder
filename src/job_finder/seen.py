"""Durable first-seen ledger: which postings any prior digest has shown.

data/jobs.db is rebuilt from scratch every pipeline run, so first_seen_at is
always "now" and can never distinguish a brand-new posting from one that has
been sitting in the digest for weeks. This table in data/state.db carries
the distinction across runs; before it existed, every digest labeled all
rows "new" and carried forward nothing.
"""
from __future__ import annotations

from pathlib import Path

from . import state

DEFAULT_STATE_DB = state.DEFAULT_STATE_DB


def load_seen(db_path: Path = DEFAULT_STATE_DB) -> dict[str, str]:
    """{external_id: first date a digest showed it}."""
    with state.connect(db_path) as conn:
        return {r["external_id"]: r["first_seen"] for r in
                conn.execute("SELECT external_id, first_seen FROM seen").fetchall()}


def record_seen(external_ids: list[str], first_seen: str,
                db_path: Path = DEFAULT_STATE_DB) -> int:
    """Record ids not already in the ledger. Returns how many were added."""
    fresh = 0
    with state.connect(db_path) as conn:
        for eid in external_ids:
            if not eid:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO seen (external_id, first_seen) VALUES (?, ?)",
                (eid, first_seen))
            fresh += cur.rowcount
    return fresh
