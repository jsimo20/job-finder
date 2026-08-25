"""Tests for the pre-tailoring liveness check (liveness.py). No network."""
from __future__ import annotations

import httpx
import pytest

from job_finder import liveness, state


@pytest.fixture
def tracked(tmp_path):
    db = tmp_path / "state.db"
    state.upsert_company({"name": "Acme", "ats_provider": "greenhouse",
                          "ats_slug": "acme"}, db)
    state.upsert_company({"name": "Borealis", "ats_provider": "ashby",
                          "ats_slug": "borealis"}, db)
    state.upsert_company({"name": "Cyngus", "ats_provider": "workday",
                          "ats_slug": "cyngus/wd1/careers"}, db)
    return db


def _client(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        for fragment, payload in routes.items():
            if fragment in str(request.url):
                return httpx.Response(200, json=payload)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def boards(monkeypatch):
    """One Greenhouse board with 111111, one Ashby board with aaa-111."""
    transport = _client({
        "boards-api.greenhouse.io": {"jobs": [{"id": 111111}, {"id": 222222}]},
        "api.ashbyhq.com": {"jobs": [{"id": "aaa-111"}]},
    })
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client",
                        lambda **kw: real(transport=transport, **kw))


def test_listed_posting_is_live(tracked, boards):
    roles = [{"company": "Acme", "external_id": "111111"}]
    assert liveness.check(roles, db_path=tracked)[0]["live"] is True


def test_unlisted_posting_is_dead(tracked, boards):
    roles = [{"company": "Acme", "external_id": "999999"}]
    result = liveness.check(roles, db_path=tracked)[0]
    assert result["live"] is False
    assert "no longer listed" in result["liveness_note"]


def test_ashby_uses_the_listing_not_the_page(tracked, boards):
    """An Ashby posting page returns 200 when closed; only the listing differs."""
    live, dead = liveness.check(
        [{"company": "Borealis", "external_id": "aaa-111"},
         {"company": "Borealis", "external_id": "gone-999"}], db_path=tracked)
    assert live["live"] is True
    assert dead["live"] is False


def test_ids_compare_as_strings(tracked, boards):
    """Greenhouse ids arrive as ints from the board and strings from the digest."""
    assert liveness.check([{"company": "Acme", "external_id": 111111}],
                          db_path=tracked)[0]["live"] is True


def test_untracked_company_is_undetermined(tracked, boards):
    result = liveness.check([{"company": "Nowhere Inc", "external_id": "1"}],
                            db_path=tracked)[0]
    assert result["live"] is None
    assert "not tracked" in result["liveness_note"]


def test_provider_without_a_cheap_listing_is_undetermined(tracked, boards):
    """Workday has no light listing endpoint, so its roles still get tailored."""
    result = liveness.check([{"company": "Cyngus", "external_id": "1"}],
                            db_path=tracked)[0]
    assert result["live"] is None


def test_a_failing_board_is_undetermined_not_dead(tracked, monkeypatch):
    """A network failure must never be read as a closed posting."""
    def boom(request):
        raise httpx.ConnectError("no route")
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(
        transport=httpx.MockTransport(boom), **kw))
    result = liveness.check([{"company": "Acme", "external_id": "111111"}],
                            db_path=tracked)[0]
    assert result["live"] is None


def test_partition_keeps_undetermined_roles(tracked, boards):
    """Skipping a real posting costs an application; tailoring a dead one costs tokens."""
    worth, dead = liveness.partition([
        {"company": "Acme", "external_id": "111111"},      # live
        {"company": "Acme", "external_id": "999999"},      # dead
        {"company": "Cyngus", "external_id": "1"},         # undetermined
    ], db_path=tracked)
    assert [r["external_id"] for r in worth] == ["111111", "1"]
    assert [r["external_id"] for r in dead] == ["999999"]


def test_one_board_is_read_once_for_several_roles(tracked, monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"jobs": [{"id": 111111}, {"id": 222222}]})
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(
        transport=httpx.MockTransport(handler), **kw))

    liveness.check([{"company": "Acme", "external_id": "111111"},
                    {"company": "Acme", "external_id": "222222"},
                    {"company": "Acme", "external_id": "333333"}], db_path=tracked)
    assert len(calls) == 1
