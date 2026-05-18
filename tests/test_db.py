from boston_pm_tracker import db


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"companies", "postings", "extractions", "scores", "daily_log"}.issubset(tables)


def test_upsert_company_and_posting(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        cid = db.upsert_company(
            conn, name="Acme", ats_provider="greenhouse", ats_slug="acme",
            careers_url=None, sector_tags=["saas"], size_band="51-200",
        )
        pid = db.upsert_posting(
            conn, company_id=cid, external_id="1", title="Senior PM",
            location="Boston", workplace_type="hybrid", level="senior",
            url="https://example.com/1", jd_text="JD",
            posted_at="2026-05-01T00:00:00+00:00",
            hard_filter_verdict="keep",
        )
        row = conn.execute("SELECT * FROM postings WHERE id = ?", (pid,)).fetchone()
        assert row["title"] == "Senior PM"
        assert row["closed_at"] is None

        closed = db.mark_closed_postings(conn, company_id=cid, seen_external_ids=set())
        assert closed == 1


def test_mark_applied_and_dismiss_round_trip(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        cid = db.upsert_company(
            conn, name="Acme", ats_provider="greenhouse", ats_slug="acme",
            careers_url=None, sector_tags=[], size_band="51-200",
        )
        db.upsert_posting(
            conn, company_id=cid, external_id="42", title="Senior PM",
            location="Boston", workplace_type="hybrid", level="senior",
            url="https://example.com/42", jd_text="JD",
            posted_at=None, hard_filter_verdict="keep",
        )
        assert db.mark_applied(conn, external_id="42") == 1
        row = conn.execute("SELECT applied_at, dismissed_at FROM postings WHERE external_id='42'").fetchone()
        assert row["applied_at"] is not None and row["dismissed_at"] is None
        assert db.mark_dismissed(conn, external_id="42") == 1
        row = conn.execute("SELECT applied_at, dismissed_at FROM postings WHERE external_id='42'").fetchone()
        assert row["applied_at"] is None and row["dismissed_at"] is not None
        assert db.unmark(conn, external_id="42") == 1
        row = conn.execute("SELECT applied_at, dismissed_at FROM postings WHERE external_id='42'").fetchone()
        assert row["applied_at"] is None and row["dismissed_at"] is None


def test_init_db_adds_missing_columns(tmp_path):
    # Simulate an existing DB created before the applied_at / dismissed_at columns
    # existed: create just the legacy postings table, then run init_db and verify
    # the migration adds them without dropping data.
    import sqlite3 as _sql
    db_path = tmp_path / "legacy.db"
    legacy = _sql.connect(db_path)
    legacy.executescript("""
      CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
        ats_provider TEXT NOT NULL, ats_slug TEXT NOT NULL, careers_url TEXT,
        sector_tags TEXT, size_band TEXT, added_at TEXT NOT NULL, last_checked_at TEXT,
        UNIQUE(ats_provider, ats_slug));
      CREATE TABLE postings (id INTEGER PRIMARY KEY,
        company_id INTEGER NOT NULL, external_id TEXT NOT NULL,
        title TEXT NOT NULL, location TEXT, workplace_type TEXT, level TEXT,
        url TEXT NOT NULL, jd_text TEXT, raw_json TEXT NOT NULL,
        posted_at TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
        closed_at TEXT, hard_filter_verdict TEXT,
        UNIQUE(company_id, external_id));
    """)
    legacy.execute(
        "INSERT INTO companies (name, ats_provider, ats_slug, added_at) VALUES (?, ?, ?, ?)",
        ("Acme", "greenhouse", "acme", "2026-01-01T00:00:00+00:00"),
    )
    legacy.commit()
    legacy.close()

    db.init_db(db_path)

    with db.connect(db_path) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(postings)")}
        assert "applied_at" in cols
        assert "dismissed_at" in cols
        # Data preserved
        n = conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"]
        assert n == 1
