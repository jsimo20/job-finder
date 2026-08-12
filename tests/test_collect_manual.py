"""Manual-tier companies: collect skips them cleanly, the digest lists them."""
from __future__ import annotations

from job_finder import collect, db, digest, state


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


def test_digest_manual_section_empty_when_none(tmp_path):
    state_db = tmp_path / "state.db"
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)
    out = digest.render(target_date="2026-08-10", db_path=jobs_db,
                        digest_dir=tmp_path / "digests", state_db=state_db)
    body = out.read_text(encoding="utf-8")
    assert "## Manual check (0)" in body
    assert "_(none tracked)_" in body
