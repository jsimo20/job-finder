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
            url="https://example.com/1", jd_text="JD", raw_json={"id": 1},
            posted_at="2026-05-01T00:00:00+00:00",
            hard_filter_verdict="keep",
        )
        row = conn.execute("SELECT * FROM postings WHERE id = ?", (pid,)).fetchone()
        assert row["title"] == "Senior PM"
        assert row["closed_at"] is None

        closed = db.mark_closed_postings(conn, company_id=cid, seen_external_ids=set())
        assert closed == 1
