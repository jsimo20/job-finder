"""Tests for the Layer-1 fill grader (fill_grader.py). Synthetic manifests
only — real audit manifests carry PII and stay out of git."""
from __future__ import annotations

import json

from boston_pm_tracker import fill_grader

PROFILE = {
    "identity": {"name": "Test Person", "email": "t@example.org", "phone": "5", "address": "1 St"},
    "answers": {"work_authorized": True, "requires_sponsorship": False},
    "eeo": {"gender": "Male"},
    "education": {"school": "U", "start_year": "2014"},
}


def _grade(fields, tmp_path, profile=PROFILE):
    p = tmp_path / "x.post.json"
    p.write_text(json.dumps({"slug": "x", "fields": fields}), encoding="utf-8")
    return fill_grader.grade_manifest(p, profile)


def test_vetoed_sponsorship_answer_is_critical_and_caps_at_f(tmp_path):
    """Regression: Smartsheet 2026-07-30 committed 'Yes' on a sponsorship field."""
    fields = [
        {"label": "Do you now or will you in the future require immigration "
                  "sponsorship for work authorization?*",
         "type": "react-select", "required": True, "value": "Yes", "options": ["Yes", "No"]},
        {"label": "First Name*", "type": "text", "required": True, "value": "T", "options": None},
    ]
    r = _grade(fields, tmp_path)
    assert r["counts"]["critical"] == 1
    assert r["grade"] == "F"


def test_salary_blank_is_deliberate_and_filled_is_critical(tmp_path):
    blank = {"label": "Salary expectations*", "type": "text", "required": True,
             "value": "", "options": None}
    filled = dict(blank, value="200000")
    assert _grade([blank], tmp_path)["counts"]["deliberate_blank"] == 1
    assert _grade([filled], tmp_path)["counts"]["critical"] == 1


def test_name_trap_field_with_value_is_critical(tmp_path):
    f = {"label": "If referred by an employee, please indicate their first and last name",
         "type": "text", "required": False, "value": "Person", "options": None}
    assert _grade([f], tmp_path)["counts"]["critical"] == 1


def test_ruled_blank_is_missed_and_unruled_blank_is_backlog(tmp_path):
    fields = [
        {"label": "Email*", "type": "text", "required": True, "value": "", "options": None},
        {"label": "Favorite dinosaur", "type": "text", "required": False, "value": "", "options": None},
    ]
    r = _grade(fields, tmp_path)
    assert r["counts"]["missed"] == 1
    assert r["counts"]["no_rule"] == 1


def test_empty_option_dropdown_is_env_failure_not_missed(tmp_path):
    """Smartsheet's race/disability menus rendered zero options to the filler."""
    f = {"label": "My disability status is:*", "type": "react-select",
         "required": True, "value": "", "options": []}
    profile = dict(PROFILE, eeo={"disability": "no, i do not have"})
    r = _grade([f], tmp_path, profile)
    assert r["counts"]["env_failure"] == 1
    assert r["counts"].get("missed", 0) == 0


def test_legal_question_and_checkbox_are_deliberate_blanks(tmp_path):
    fields = [
        {"label": "Have you entered into an agreement with your current employer "
                  "that impacts your ability to do business in any way?",
         "type": "react-select", "required": True, "value": "", "options": ["Yes", "No"]},
        {"label": "gdpr_demographic_data_consent_given", "type": "checkbox",
         "required": True, "value": "", "options": ["By checking this box..."]},
    ]
    assert _grade(fields, tmp_path)["counts"]["deliberate_blank"] == 2


def test_grade_bands(tmp_path):
    def field(i, filled):
        return {"label": "Email*" if not filled else "First Name*", "type": "text",
                "required": True, "value": "x" if filled else "", "options": None}
    all_filled = [field(i, True) for i in range(10)]
    assert _grade(all_filled, tmp_path)["grade"] == "A"
    nine_of_ten = all_filled[:9] + [field(9, False)]
    assert _grade(nine_of_ten, tmp_path)["grade"] == "B"


def test_bare_list_manifest_shape(tmp_path):
    p = tmp_path / "old.post.json"
    p.write_text(json.dumps([
        {"label": "First Name*", "type": "text", "required": True, "value": "T", "options": None},
        "stray-non-dict-entry",
    ]), encoding="utf-8")
    r = fill_grader.grade_manifest(p, PROFILE)
    assert r["counts"]["filled"] == 1
