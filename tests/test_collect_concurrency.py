"""Collect fans out across companies: fetches overlap, and one bad adapter
cannot take the siblings in flight with it."""
from __future__ import annotations

import threading

from job_finder import collect, db, state
from job_finder.adapters.base import NormalizedPosting


def _posting(slug: str) -> NormalizedPosting:
    return NormalizedPosting(
        external_id=f"{slug}-1", title="Senior Product Manager, Platform",
        location="Boston, MA", workplace_type=None,
        url=f"https://example.com/{slug}", jd_text="5+ years of product management",
        posted_at=None, detail_ref=None)


def _companies(state_db, count: int) -> None:
    for i in range(count):
        state.upsert_company({"name": f"Company {i}", "ats_provider": "greenhouse",
                              "ats_slug": f"company{i}"}, state_db)


def test_collect_fetches_companies_concurrently(tmp_path, monkeypatch):
    state_db = tmp_path / "state.db"
    _companies(state_db, 8)
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)

    # Every fetch blocks until four are in flight together. A serial collect
    # never gets a second fetch started, so the barrier times out and breaks.
    barrier = threading.Barrier(4, timeout=10)

    def fake_fetch(slug, *, client=None, timeout=30.0):
        barrier.wait()
        return [_posting(slug)]

    monkeypatch.setitem(collect.REGISTRY, "greenhouse", fake_fetch)

    stats = collect.run(state_db=state_db, db_path=jobs_db, max_workers=4)
    assert stats["fetched"] == 8
    assert stats["errors"] == 0
    with db.connect(jobs_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 8


def test_collect_isolates_unexpected_adapter_failure(tmp_path, monkeypatch):
    state_db = tmp_path / "state.db"
    state.upsert_company({"name": "Good Co", "ats_provider": "greenhouse",
                          "ats_slug": "goodco"}, state_db)
    state.upsert_company({"name": "Bad Co", "ats_provider": "greenhouse",
                          "ats_slug": "badco"}, state_db)
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)

    def fake_fetch(slug, *, client=None, timeout=30.0):
        if slug == "badco":
            raise RuntimeError("adapter raised something collect does not expect")
        return [_posting(slug)]

    monkeypatch.setitem(collect.REGISTRY, "greenhouse", fake_fetch)

    stats = collect.run(state_db=state_db, db_path=jobs_db, max_workers=2)
    assert stats["errors"] == 1
    assert any("Bad Co" in detail for detail in stats["errors_detail"])
    # The healthy sibling still landed.
    assert stats["fetched"] == 1
    with db.connect(jobs_db) as conn:
        rows = [r["external_id"] for r in conn.execute("SELECT external_id FROM postings")]
    assert rows == ["goodco-1"]


def test_collect_stats_survive_a_window_boundary(tmp_path, monkeypatch):
    """More companies than one submission window: nothing is dropped or
    double-counted when the pool is refilled."""
    state_db = tmp_path / "state.db"
    _companies(state_db, 20)
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)

    monkeypatch.setitem(collect.REGISTRY, "greenhouse",
                        lambda slug, *, client=None, timeout=30.0: [_posting(slug)])

    stats = collect.run(state_db=state_db, db_path=jobs_db, max_workers=2)
    assert stats["companies"] == 20
    assert stats["fetched"] == 20
    assert stats["errors"] == 0
    with db.connect(jobs_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0] == 20
