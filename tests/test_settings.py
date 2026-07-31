"""Tests for the config/profile loaders and the profile-driven combo builder."""
from __future__ import annotations

from job_finder import settings
from job_finder.fill_greenhouse import build_combo_fields


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
    assert r"(?<!trans)gender" in patterns
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


SPONSOR_AUTH_LABEL = ("Do you now or will you in the future require immigration "
                    "sponsorship for work authorization?")


def _first_matching(combos, label):
    import re
    for pattern, candidates in combos:
        if re.search(pattern, label, re.I):
            return pattern, candidates
    return None, None


def test_sponsorship_label_mentioning_authorization_hits_sponsor_row_first():
    """Regression from a live form. The label contains both 'sponsorship'
    and 'authorization'; matching the authorization row first committed its
    'yes' candidate, answering that the applicant DOES need sponsorship."""
    profile = {"answers": {"work_authorized": True, "requires_sponsorship": False}}
    pattern, candidates = _first_matching(build_combo_fields(profile), SPONSOR_AUTH_LABEL)
    assert pattern == r"sponsor"
    assert "yes" not in [c.lower() for c in candidates]
    # and against a plain Yes/No dropdown, the row resolves to No
    from job_finder.fill_greenhouse import match_option
    assert match_option(["yes", "no"], candidates[-1]) == 1


def test_sponsor_veto_blocks_bare_yes_option():
    import re
    from job_finder.fill_greenhouse import veto_for
    veto = veto_for(SPONSOR_AUTH_LABEL)
    assert veto is not None
    assert re.search(veto, "Yes", re.I)
    assert re.search(veto, " yes. ", re.I)
    # a longer option containing "yes" that declines sponsorship stays allowed
    assert not re.search(veto, "Yes, I am authorized and do not require sponsorship", re.I)


def test_custom_combos_prepend_and_override():
    profile = {
        "answers": {"work_authorized": True, "requires_sponsorship": False},
        "custom_combos": [
            {"label": r"export.control", "candidates": ["US Passport or US birth certificate"]},
            {"label": r"\bsms\b|text messag", "candidates": ["Yes"]},
        ],
    }
    combos = build_combo_fields(profile)
    assert combos[0][0] == r"export.control"
    pattern, candidates = _first_matching(combos, "We would like to use SMS communication. Do you approve?")
    assert candidates == ["Yes"]


def test_education_rows_only_when_configured():
    plain = build_combo_fields({})
    assert not any("school" in p for p, _ in plain)
    profile = {"education": {"school": "Example University", "degree": "Bachelor's Degree",
                             "discipline": "Cartography", "start_month": "September"}}
    combos = build_combo_fields(profile)
    pattern, candidates = _first_matching(combos, "School")
    assert candidates == ["Example University"]
    pattern, candidates = _first_matching(combos, "Start date month")
    assert candidates == ["September"]


def test_parse_answers_pulls_address_and_years_from_profile(tmp_path):
    from job_finder.fill_greenhouse import parse_answers
    profile = {"identity": {"name": "Test Person", "address": "1 Test St"},
               "education": {"start_year": "2014", "end_year": "2018"}}
    answers = parse_answers(tmp_path, profile)   # no standard_answers.md present
    assert answers["address"] == "1 Test St"
    assert answers["start_year"] == "2014"
    assert answers["end_year"] == "2018"


def test_education_values_accept_ordered_fallback_lists():
    profile = {"education": {"discipline": ["Cartography", "Geography"]}}
    combos = build_combo_fields(profile)
    pattern, candidates = _first_matching(combos, "Discipline")
    assert candidates == ["Cartography", "Geography"]


def test_transgender_question_never_routes_to_the_gender_row():
    """Regression from a live form. 'I identify as transgender:' contains
    the substring 'gender' and used to hit the gender row's 'Male' candidate."""
    profile = {"eeo": {"gender": "Male", "transgender": "No"}}
    combos = build_combo_fields(profile)
    pattern, candidates = _first_matching(combos, "I identify as transgender:")
    assert candidates == ["No"]
    pattern, candidates = _first_matching(combos, "I identify my gender as:")
    assert candidates == ["Male"]


def test_gender_row_ignores_transgender_even_without_a_transgender_answer():
    combos = build_combo_fields({"eeo": {"gender": "Male"}})
    pattern, candidates = _first_matching(combos, "I identify as transgender:")
    assert candidates is None


def test_veteran_fallback_list_covers_both_phrasings():
    from job_finder.fill_greenhouse import match_option
    profile = {"eeo": {"veteran": ["not a protected", "not a veteran"]}}
    _, candidates = _first_matching(build_combo_fields(profile), "My veteran status is:")
    greenhouse = ["i am not a protected veteran", "i identify as one or more", "i don't wish to answer"]
    vendor_b = ["yes, i am a veteran", "no, i am not a veteran", "i don't wish to answer"]
    assert match_option(greenhouse, candidates[0]) == 0
    assert match_option(vendor_b, candidates[0]) is None
    assert match_option(vendor_b, candidates[1]) == 1


def test_custom_text_rules_parse_and_filter():
    from job_finder.fill_greenhouse import build_custom_text
    profile = {"custom_text": [
        {"label": r"zip.{0,10}code", "value": "99999"},
        {"label": "", "value": "orphan"},
        {"label": "no-value"},
    ]}
    assert build_custom_text(profile) == [(r"zip.{0,10}code", "99999")]
