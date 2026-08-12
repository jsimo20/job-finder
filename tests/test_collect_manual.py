"""Manual-tier companies: collect skips them cleanly, the digest lists them.
Detail-only providers: collect enriches kept postings, never discarded ones."""
from __future__ import annotations

from job_finder import collect, db, digest, state
from job_finder.adapters.base import NormalizedPosting


def _state_with_manual(tmp_path):
    state_db = tmp_path / "state.db"
    state.upsert_company({"name": "Handmade Widgets", "ats_provider": "manual",
                          "careers_url": "https://example.com/careers",
                          "sector_tags": ["iot_edge"]}, state_db)
    return state_db


def test_collect_skips_manual_without_error(tmp_path):
    state_db = _state_with_manual(tmp_path)
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)
    stats = collect.run(state_db=state_db, db_path=jobs_db)
    assert stats["manual"] == 1
    assert stats["errors"] == 0
    assert stats["fetched"] == 0


def test_digest_lists_manual_companies(tmp_path):
    state_db = _state_with_manual(tmp_path)
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)
    out = digest.render(target_date="2026-08-10", db_path=jobs_db,
                        digest_dir=tmp_path / "digests", state_db=state_db)
    body = out.read_text(encoding="utf-8")
    assert "## Manual check (1)" in body
    assert "[Handmade Widgets](https://example.com/careers)" in body
    assert "iot_edge" in body


def test_collect_enriches_kept_postings_only(tmp_path, monkeypatch):
    state_db = tmp_path / "state.db"
    state.upsert_company({"name": "Example Corp", "ats_provider": "workday",
                          "ats_slug": "examplecorp/wd1/External"}, state_db)
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)

    def fake_fetch(slug, *, client=None, timeout=30.0):
        mk = lambda eid, title, loc: NormalizedPosting(
            external_id=eid, title=title, location=loc, workplace_type=None,
            url=f"https://example.com/{eid}", jd_text=None, posted_at=None,
            detail_ref=f"/job/{eid}")
        return [mk("R1", "Senior Product Manager, Platform", "Farport, EX"),
                mk("R2", "Equipment Maintenance Technician", "Farport, EX")]

    detail_calls = []

    def fake_detail(slug, ref, *, client=None, timeout=30.0):
        detail_calls.append(ref)
        return {"jd_text": "5+ years of product management experience",
                "posted_at": "2026-08-01"}

    monkeypatch.setitem(collect.REGISTRY, "workday", fake_fetch)
    monkeypatch.setitem(collect.DETAIL_REGISTRY, "workday", fake_detail)

    stats = collect.run(state_db=state_db, db_path=jobs_db)
    assert stats["kept"] == 1 and stats["discarded"] == 1
    # Only the surviving posting cost a detail request.
    assert detail_calls == ["/job/R1"]
    with db.connect(jobs_db) as conn:
        rows = {r["external_id"]: r for r in
                conn.execute("SELECT external_id, jd_text, posted_at FROM postings")}
    assert "5+ years" in rows["R1"]["jd_text"]
    assert rows["R1"]["posted_at"] == "2026-08-01"
    assert rows["R2"]["jd_text"] is None


def test_digest_manual_section_empty_when_none(tmp_path):
    state_db = tmp_path / "state.db"
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)
    out = digest.render(target_date="2026-08-10", db_path=jobs_db,
                        digest_dir=tmp_path / "digests", state_db=state_db)
    body = out.read_text(encoding="utf-8")
    assert "## Manual check (0)" in body
    assert "_(none tracked)_" in body
