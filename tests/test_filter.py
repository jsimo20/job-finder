from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import pytest

from job_finder import filter as filter_mod
from job_finder.filter import stage1, stage3

FIXTURE = Path(__file__).parent / "fixtures" / "pipeline_test.toml"


@pytest.fixture
def reconfigured():
    """Reconfigure the filter from an edited copy of the fixture, then restore it."""
    with FIXTURE.open("rb") as fh:
        base = tomllib.load(fh)

    def apply(**location_overrides):
        cfg = {**base, "location": {**base["location"], **location_overrides}}
        filter_mod.configure(cfg)

    yield apply
    filter_mod.configure(base)


def test_stage1_keeps_senior_pm_far_metro():
    r = stage1(title="Senior Product Manager, Platform", location="Farport, EX", workplace_type="hybrid")
    assert r.keep, r.reason


def test_stage1_keeps_staff_pm_remote_us():
    r = stage1(title="Staff Product Manager", location="Remote - US", workplace_type="remote")
    assert r.keep


def test_stage1_rejects_pmm():
    r = stage1(title="Senior Product Marketing Manager", location="Farport, EX", workplace_type=None)
    assert not r.keep
    assert "wrong_track" in r.reason


def test_stage1_rejects_project_manager():
    r = stage1(title="Senior Project Manager", location="Farport, EX", workplace_type=None)
    assert not r.keep


def test_stage1_rejects_product_owner():
    r = stage1(title="Senior Product Owner", location="Farport, EX", workplace_type=None)
    assert not r.keep


def test_stage1_rejects_apm():
    r = stage1(title="Associate Product Manager", location="Farport, EX", workplace_type=None)
    assert not r.keep
    assert "too_junior" in r.reason


def test_stage1_rejects_director():
    r = stage1(title="Director of Product", location="Farport, EX", workplace_type=None)
    assert not r.keep
    assert "director_plus" in r.reason


def test_stage1_rejects_engineering_manager_with_product():
    r = stage1(title="Senior Software Engineering Manager, Web Platform",
               location="Farport, EX", workplace_type="hybrid")
    assert not r.keep
    assert "engineering_or_ic_role" in r.reason


def test_stage1_rejects_product_security_engineer():
    r = stage1(title="Senior Product Security Engineer", location="Farport, EX", workplace_type=None)
    assert not r.keep


def test_stage1_rejects_full_stack_with_product():
    r = stage1(title="Senior Full Stack Engineer - New Product", location="Farport, EX", workplace_type=None)
    assert not r.keep


def test_stage1_keeps_pm_for_developer_experience():
    # "Developer Experience" is the product area, not the role; PM stem wins.
    r = stage1(title="Lead Product Manager, Developer Experience",
               location="Farport, EX", workplace_type="hybrid")
    assert r.keep


def test_stage1_keeps_engineering_product_manager():
    r = stage1(title="Principal Engineering Product Manager, Optics",
               location="Bigcity, EX", workplace_type="hybrid")
    assert r.keep


def test_stage1_keeps_head_of_product():
    r = stage1(title="Head of Product, Platform", location="Farport", workplace_type="hybrid")
    assert r.keep


def test_stage1_rejects_unscoped_location():
    r = stage1(title="Senior Product Manager", location="San Francisco, CA", workplace_type="onsite")
    assert not r.keep
    assert "wrong_location" in r.reason


def test_stage1_rejects_eu_remote():
    r = stage1(title="Senior Product Manager", location="Remote - EMEA", workplace_type="remote")
    assert not r.keep
    assert "remote_out_of_scope" in r.reason


def test_stage1_rejects_remote_japan():
    r = stage1(title="Senior Product Manager", location="Remote - Japan", workplace_type="remote")
    assert not r.keep
    assert "remote_out_of_scope" in r.reason


def test_stage1_rejects_uk_first_remote():
    r = stage1(title="Senior Product Manager", location="United Kingdom, Remote", workplace_type="remote")
    assert not r.keep
    assert "remote_out_of_scope" in r.reason


def test_remote_require_patterns_demand_the_users_market(reconfigured):
    reconfigured(remote_exclude_patterns=[], remote_require_patterns=[r"\b(uk|united kingdom|europe|emea)\b"])
    kept = stage1(title="Senior Product Manager", location="Remote - EMEA", workplace_type="remote")
    assert kept.keep, kept.reason
    bare = stage1(title="Senior Product Manager", location="Remote", workplace_type="remote")
    assert bare.reason == "discard:remote_out_of_scope"


def test_remote_require_patterns_never_block_the_configured_geography(reconfigured):
    reconfigured(remote_require_patterns=[r"\b(uk|united kingdom)\b"])
    r = stage1(title="Senior Product Manager", location="Nearville, EX (Remote)", workplace_type="remote")
    assert r.keep, r.reason


def test_empty_remote_exclude_patterns_keep_every_remote_role(reconfigured):
    reconfigured(remote_exclude_patterns=[])
    r = stage1(title="Senior Product Manager", location="Remote - Canada", workplace_type="remote")
    assert r.keep, r.reason


def test_stage1_keeps_remote_us_variants():
    for loc in ["Remote, US", "Remote, USA", "Remote, United States", "Remote-United-States",
                "REMOTE - US", "United States, Remote", "Remote"]:
        r = stage1(title="Senior Product Manager", location=loc, workplace_type="remote")
        assert r.keep, f"{loc!r} should be kept: {r.reason}"


def test_stage1_rejects_dublin_pm():
    r = stage1(title="Senior Product Manager - Banking", location="Dublin, Ireland",
               workplace_type="hybrid")
    assert not r.keep
    assert "wrong_location" in r.reason


def test_stage1_keeps_near_metro():
    r = stage1(title="Principal Product Manager", location="Nearville, EX", workplace_type="hybrid")
    assert r.keep


def test_stage1_keeps_east_coast():
    r = stage1(title="Principal Product Manager, Agent Platform",
               location="East Coast, USA", workplace_type=None)
    assert r.keep


def test_stage1_rejects_west_coast():
    r = stage1(title="Principal Product Manager", location="West Coast, USA", workplace_type=None)
    assert not r.keep
    assert "wrong_location" in r.reason


def test_stage3_main_queue():
    r = stage3(yoe_required=5, comp_base_min=180000, comp_base_max=240000, comp_source="posted")
    assert r.keep and r.queue == "main"


def test_stage3_stretch_queue():
    r = stage3(yoe_required=9, comp_base_min=210000, comp_base_max=280000, comp_source="posted")
    assert r.keep and r.queue == "stretch"


def test_stage3_comp_ceiling_below_floor_discards():
    r = stage3(yoe_required=5, comp_base_min=110000, comp_base_max=130000, comp_source="posted")
    assert not r.keep and r.queue == "discard"


def test_stage3_wide_range_spans_floor_kept():
    # $136K-204K — bottom is under $140K floor but ceiling is well above.
    r = stage3(yoe_required=5, comp_base_min=136000, comp_base_max=204000, comp_source="posted")
    assert r.keep and r.queue == "main"


def test_stage3_null_comp_kept():
    r = stage3(yoe_required=None, comp_base_min=None, comp_base_max=None, comp_source=None)
    assert r.keep and r.queue == "main"


def test_dash_separated_out_of_scope_remote_is_discarded():
    """Regression: a live posting's "Canada - Remote" passed the location gate because
    the country-then-remote pattern only allowed comma/space separators."""
    for loc in ("Canada - Remote", "Remote - Canada", "Canada, Remote"):
        r = stage1(title="Senior Product Manager", location=loc, workplace_type="remote")
        assert r.reason == "discard:remote_out_of_scope", loc


def test_stage1_keeps_a_pm_title_with_no_level_word():
    r = stage1(title="Product Manager, Growth", location="Farport, EX", workplace_type="hybrid")
    assert r.keep and r.reason == "keep"


def test_stage1_still_rejects_an_explicitly_junior_title():
    r = stage1(title="Product Manager II", location="Farport, EX", workplace_type="hybrid")
    assert not r.keep and r.reason == "discard:too_junior"


def test_stage3_untitled_role_asking_enough_experience_reaches_main():
    r = stage3(yoe_required=6, comp_base_min=None, comp_base_max=None, comp_source=None, titled=False)
    assert r.keep and r.queue == "main"


def test_stage3_untitled_role_asking_little_experience_goes_to_stretch():
    r = stage3(yoe_required=3, comp_base_min=None, comp_base_max=None, comp_source=None, titled=False)
    assert r.keep and r.queue == "stretch" and r.reason == "untitled_yoe_required:3"


def test_stage3_untitled_role_with_no_stated_experience_goes_to_stretch():
    r = stage3(yoe_required=None, comp_base_min=None, comp_base_max=None, comp_source=None, titled=False)
    assert r.keep and r.queue == "stretch"


def test_stage3_untitled_role_below_comp_floor_is_still_discarded():
    r = stage3(yoe_required=6, comp_base_min=110000, comp_base_max=130000, comp_source="posted", titled=False)
    assert not r.keep and r.queue == "discard"
