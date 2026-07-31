"""Location gate + commute warning, exercised against the fictional fixture
geography in tests/fixtures/pipeline_test.toml (see conftest.py). The
mechanisms under test are real; no real region is baked into the suite.

Fixture model: far = Farport/Bigcity, mid = Midway, near = Nearville/Centerton,
state token EX covers the near tier. "Farport, EX" therefore matches both the
far city token and the near state token — the far reading must win.
"""
from __future__ import annotations

import pytest

from job_finder import filter as f
from job_finder.extract import _clamp_days


# ── Stage-1 location gate ────────────────────────────────────────────────────

@pytest.mark.parametrize("loc", [
    "Farport, EX", "Bigcity", "Midway, EX", "Nearville", "Centerton, EX",
    "Somewhere, EX",          # bare state token qualifies
    "East Coast (Remote OK)", # region phrase qualifies
])
def test_in_scope_locations_keep(loc):
    r = f.stage1(title="Senior Product Manager", location=loc, workplace_type="hybrid")
    assert r.keep, (loc, r.reason)


@pytest.mark.parametrize("loc", ["Otherville, ZZ", "London, UK", "Ambleton"])
def test_out_of_scope_locations_discard(loc):
    r = f.stage1(title="Senior Product Manager", location=loc, workplace_type="hybrid")
    assert r.reason == "discard:wrong_location", loc


def test_city_name_collision_needs_the_state_token():
    """A near-tier city name that also exists elsewhere qualifies only through
    the explicit state token (the Manchester-CT-vs-Manchester-UK class of bug:
    the city name alone is not in scope, EX is)."""
    assert f.stage1(title="Senior Product Manager", location="Nearville, EX",
                    workplace_type="hybrid").keep
    r = f.stage1(title="Senior Product Manager", location="Ambleton, UK",
                 workplace_type="hybrid")
    assert not r.keep


def test_us_remote_is_always_in_scope():
    r = f.stage1(title="Senior Product Manager", location="Remote - US",
                 workplace_type="remote")
    assert r.keep


# ── Metro tiers ──────────────────────────────────────────────────────────────

def test_tiers_resolve():
    assert f.metro_tier("Nearville") == "near"
    assert f.metro_tier("Midway") == "mid"
    assert f.metro_tier("Farport") == "far"
    assert f.metro_tier("Otherville") is None
    assert f.metro_tier(None) is None


def test_far_city_wins_over_near_state_token():
    """"Farport, EX" matches the near tier's EX token too; checked far-first
    because the far reading is the one that matters for commute."""
    assert f.metro_tier("Farport, EX") == "far"


# ── Commute warning ──────────────────────────────────────────────────────────

def test_far_metro_heavy_onsite_warns():
    assert f.commute_warning("Farport, EX", 5) is not None
    assert f.commute_warning("Farport, EX", 4) is not None


def test_far_metro_hybrid_does_not_warn():
    # The case the rule must never break: distance is fine when hybrid.
    assert f.commute_warning("Farport, EX", 3) is None
    assert f.commute_warning("Farport, EX", 2) is None


def test_mid_metro_warns_only_at_five_days():
    assert f.commute_warning("Midway", 5) is not None
    assert f.commute_warning("Midway", 4) is None


def test_near_metro_never_warns():
    assert f.commute_warning("Nearville", 5) is None


def test_remote_never_warns():
    assert f.commute_warning("Farport, EX", 5, remote_us_ok=True) is None


def test_unknown_schedule_never_warns():
    # Null means the JD said nothing; warning on that would fire on most roles.
    assert f.commute_warning("Farport, EX", None) is None


def test_warning_carries_the_configured_note():
    warning = f.commute_warning("Farport, EX", 5)
    assert warning == "5 days onsite, ~2h each way from home base"


# ── onsite_days_per_week boundary validation ─────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    (3, 3), (0, 0), (5, 5), ("4", 4), (None, None),
    (6, None), (-1, None), ("many", None), (2.0, 2),
])
def test_clamp_days(raw, expected):
    assert _clamp_days(raw) == expected
