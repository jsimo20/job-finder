"""Tests for the config/profile loaders and the profile-driven combo builder."""
from __future__ import annotations

from boston_pm_tracker import settings
from boston_pm_tracker.fill_greenhouse import build_combo_fields


def test_pipeline_config_parses_and_has_required_tables():
    cfg = settings.pipeline_config()
    assert cfg["filters"]["comp_floor_usd"] > 0
    assert cfg["location"]["in_scope_patterns"]
    assert set(cfg["location"]["tiers"]) == {"near", "mid", "far"}
    for spec in cfg["domains"].values():
        assert {"weight", "definition"} <= set(spec)


def test_profile_example_is_a_loadable_fallback():
    example = settings.load_profile(settings.PROFILE_EXAMPLE_DIR / "profile.toml")
    assert example["identity"]["name"]
    # The example must never carry EEO answers — an unconfigured clone
    # falling back to it must not fill those questions with someone else's
    # defaults.
    assert all(v == "" for v in example["eeo"].values())


def test_combo_fields_from_example_profile_have_no_eeo_rows():
    example = settings.load_profile(settings.PROFILE_EXAMPLE_DIR / "profile.toml")
    combos = build_combo_fields(example)
    patterns = [p for p, _ in combos]
    assert r"sponsor" in patterns          # authorized + no sponsorship in example
    assert r"gender" not in patterns
    assert r"disabilit" not in patterns
    assert r"pronoun" not in patterns


def test_combo_fields_include_eeo_rows_only_when_set():
    profile = {
        "answers": {"work_authorized": True, "requires_sponsorship": False},
        "eeo": {"gender": "Male", "hispanic": "", "veteran": "not a protected"},
    }
    patterns = [p for p, _ in build_combo_fields(profile)]
    assert r"gender" in patterns
    assert r"veteran" in patterns
    assert r"hispanic" not in patterns


def test_combo_fields_omit_authorization_when_sponsorship_needed():
    """Someone who needs sponsorship must get a blank, never the stock 'no'."""
    profile = {"answers": {"work_authorized": True, "requires_sponsorship": True}}
    patterns = [p for p, _ in build_combo_fields(profile)]
    assert r"sponsor" not in patterns
    assert r"authori[sz]" not in patterns


def test_combo_fields_omit_authorization_when_answers_missing():
    patterns = [p for p, _ in build_combo_fields({})]
    assert r"sponsor" not in patterns
    assert r"authori[sz]" not in patterns
