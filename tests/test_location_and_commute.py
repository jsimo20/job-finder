"""Search-radius expansion and the commute warning.

The committed config places the home base in central Connecticut and targets
Boston deliberately, accepting the
drive when the schedule is hybrid. What he rules out is 4-5 days onsite at that
distance, which is why this produces a warning rather than a discard.
"""
from __future__ import annotations

import pytest

from job_finder import filter as f
from job_finder.extract import _clamp_days


def _keep(location, title="Senior Product Manager", workplace_type=None):
    return f.stage1(title=title, location=location, workplace_type=workplace_type).keep


@pytest.mark.parametrize("loc", [
    "New Haven",          # city with no state — matched nothing before
    "Stamford",
    "Providence",
    "Springfield",
    "Worcester",
    "Hartford, CT",
    "Anytown, CT",
    "New London, CT",
    "Pawtucket, RI",
    "Northampton, MA",
])
def test_expanded_metros_are_in_scope(loc):
    assert _keep(loc), f"{loc} should be in scope"


@pytest.mark.parametrize("loc", ["Boston, MA", "New York, NY", "Remote, US", "East Coast, USA"])
def test_original_scope_still_kept(loc):
    assert _keep(loc)


@pytest.mark.parametrize("loc", ["Nashua, NH", "Manchester, NH", "Albany, NY", "Schenectady, NY"])
def test_second_ring_metros_in_scope(loc):
    # Same ~2h drive as Boston, so same tolerance.
    assert _keep(loc)
    assert f.metro_tier(loc) == "far"


def test_manchester_ct_is_near_not_far():
    # Manchester, CT is ten minutes away. It must not inherit the NH tier.
    assert f.metro_tier("Manchester, CT") == "near"
    assert f.commute_warning("Manchester, CT", 5) is None


def test_bare_manchester_does_not_pull_in_the_uk():
    # "Manchester" alone qualifies for nothing; only an explicit NH token does.
    assert not _keep("Manchester, United Kingdom")


@pytest.mark.parametrize("loc", ["Austin, TX", "San Francisco, CA", "Denver, CO", "Seattle, WA"])
def test_out_of_region_still_discarded(loc):
    assert not _keep(loc)


@pytest.mark.parametrize("loc,tier", [
    ("Boston, MA", "far"),
    ("Somerville, MA", "far"),
    ("New York, NY", "far"),
    ("Providence, RI", "mid"),
    ("Worcester, MA", "mid"),
    ("Stamford, CT", "mid"),
    ("Hartford, CT", "near"),
    ("New Haven, CT", "near"),
    ("Springfield, MA", "near"),
    ("Austin, TX", None),
])
def test_metro_tiers(loc, tier):
    assert f.metro_tier(loc) == tier


def test_boston_reads_as_far_not_near_despite_ma_token():
    # "Boston, MA" also matches the MA tokens that place Springfield; the far
    # reading is the one that matters for commute, so it must win.
    assert f.metro_tier("Boston, MA") == "far"


def test_far_metro_heavy_onsite_case_warns():
    # The role that prompted this: Somerville, MA, 4-5 days onsite.
    assert f.commute_warning("Somerville, MA", 5) is not None
    assert f.commute_warning("Somerville, MA", 4) is not None


def test_hybrid_boston_does_not_warn():
    # Explicitly acceptable per the config's intent — the case the rule must not break.
    assert f.commute_warning("Boston, MA", 3) is None
    assert f.commute_warning("Boston, MA", 2) is None


def test_remote_never_warns():
    assert f.commute_warning("Boston, MA", 5, remote_us_ok=True) is None


def test_unknown_schedule_does_not_warn():
    # Null means the JD said nothing; warning on that would fire on most roles.
    assert f.commute_warning("Boston, MA", None) is None


def test_nearby_onsite_does_not_warn():
    assert f.commute_warning("Hartford, CT", 5) is None


def test_mid_tier_warns_only_at_five_days():
    assert f.commute_warning("Providence, RI", 4) is None
    assert f.commute_warning("Providence, RI", 5) is not None


@pytest.mark.parametrize("raw,expected", [
    (3, 3), ("3", 3), (0, 0), (5, 5),
    (None, None), (7, None), (-1, None), ("hybrid", None), (2.9, 2),
])
def test_clamp_days_validates_model_output(raw, expected):
    assert _clamp_days(raw) == expected
