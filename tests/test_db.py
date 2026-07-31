from job_finder import db


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"companies", "postings", "extractions", "scores"}.issubset(tables)


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
            location="Farport, EX", workplace_type="hybrid",
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
            location="Farport, EX", workplace_type="hybrid",
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
