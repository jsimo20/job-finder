"""Per-company staleness overrides: high-volume boards surface only fresh roles."""
from __future__ import annotations

import sqlite3

from job_finder import state
from job_finder.digest import drop_stale_for_company


def _row(company, posted_at):
    """Minimal stand-in for the digest's sqlite3.Row shape."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE r (company_name TEXT, posted_at TEXT)")
    conn.execute("INSERT INTO r VALUES (?, ?)", (company, posted_at))
    return conn.execute("SELECT * FROM r").fetchone()


def test_override_keeps_fresh_drops_old():
    rows = [
        _row("Loud Board Co", "2026-08-12"),   # 2 days before target
        _row("Loud Board Co", "2026-07-01"),   # 44 days before target
        _row("Quiet Co", "2026-05-01"),        # no override, survives
    ]
    kept = drop_stale_for_company(rows, {"loud board co": 14}, "2026-08-14")
    assert [(r["company_name"], r["posted_at"]) for r in kept] == [
        ("Loud Board Co", "2026-08-12"),
        ("Quiet Co", "2026-05-01"),
    ]


def test_override_is_case_insensitive_on_company_name():
    rows = [_row("LOUD BOARD CO", "2026-08-13")]
    assert len(drop_stale_for_company(rows, {"loud board co": 14}, "2026-08-14")) == 1


def test_boundary_day_is_inclusive():
    rows = [_row("Loud Board Co", "2026-07-31")]   # exactly 14 days
    assert len(drop_stale_for_company(rows, {"loud board co": 14}, "2026-08-14")) == 1
    rows = [_row("Loud Board Co", "2026-07-30")]   # 15 days
    assert drop_stale_for_company(rows, {"loud board co": 14}, "2026-08-14") == []


def test_undated_posting_fails_closed_under_override():
    # first_seen_at is always "now", so an undated row cannot be trusted as fresh.
    rows = [_row("Loud Board Co", None)]
    assert drop_stale_for_company(rows, {"loud board co": 14}, "2026-08-14") == []
    # ...but with no override for that company it still surfaces.
    assert len(drop_stale_for_company(rows, {}, "2026-08-14")) == 1


def test_iso_timestamp_with_zulu_suffix_parses():
    rows = [_row("Loud Board Co", "2026-08-13T09:15:00Z")]
    assert len(drop_stale_for_company(rows, {"loud board co": 14}, "2026-08-14")) == 1


def test_unparseable_date_fails_closed():
    rows = [_row("Loud Board Co", "not-a-date")]
    assert drop_stale_for_company(rows, {"loud board co": 14}, "2026-08-14") == []


def test_no_overrides_is_a_passthrough():
    rows = [_row("A", None), _row("B", "2020-01-01")]
    assert len(drop_stale_for_company(rows, {}, "2026-08-14")) == 2


def test_max_age_roundtrips_through_state(tmp_path):
    db = tmp_path / "state.db"
    state.upsert_company({"name": "Loud Board Co", "ats_provider": "greenhouse",
                          "ats_slug": "loudboard", "max_age_days": 14}, db)
    state.upsert_company({"name": "Quiet Co", "ats_provider": "greenhouse",
                          "ats_slug": "quiet"}, db)
    assert state.max_age_overrides(db) == {"loud board co": 14}
    row = [c for c in state.list_companies(db) if c["name"] == "Loud Board Co"][0]
    assert row["max_age_days"] == 14
    # Clearing it puts the company back on the global staleness window.
    state.upsert_company({"name": "Loud Board Co", "ats_provider": "greenhouse",
                          "ats_slug": "loudboard"}, db)
    assert state.max_age_overrides(db) == {}


def test_migration_adds_column_to_preexisting_db(tmp_path):
    db = tmp_path / "state.db"
    # Simulate a database created before the column existed.
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE companies (name TEXT PRIMARY KEY, ats_provider TEXT NOT NULL,
                    ats_slug TEXT NOT NULL, careers_url TEXT, sector_tags TEXT, size_band TEXT)""")
    conn.execute("INSERT INTO companies VALUES ('Old Co','greenhouse','oldco',NULL,'[]','500+')")
    conn.commit()
    conn.close()

    state.upsert_company({"name": "Loud Board Co", "ats_provider": "greenhouse",
                          "ats_slug": "loudboard", "max_age_days": 14}, db)
    assert state.max_age_overrides(db) == {"loud board co": 14}
    assert {c["name"] for c in state.list_companies(db)} == {"Old Co", "Loud Board Co"}
