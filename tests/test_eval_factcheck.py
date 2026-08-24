"""Tests for the fact-checker eval harness (eval_factcheck.py).

Covers case loading, patching and grading. The API-calling path is deliberately
untested here: the eval spends real tokens, so it stays a manual run.
"""
from __future__ import annotations

import json

import pytest

from job_finder import eval_factcheck as ef


def test_strip_frontmatter_removes_yaml_header():
    body = ef.strip_frontmatter("---\nname: x\ntools: a, b\n---\n\nReal body here.")
    assert body == "Real body here."


def test_strip_frontmatter_passes_through_plain_markdown():
    assert ef.strip_frontmatter("# Heading\n\nbody") == "# Heading\n\nbody"


def test_apply_patch_indexes_into_lists():
    base = {"resume_data": {"experience": [{"bullets": ["a", "b"]}]}}
    out = ef.apply_patch(base, [
        {"path": "resume_data.experience.0.bullets.1", "value": "patched"}])
    assert out["resume_data"]["experience"][0]["bullets"] == ["a", "patched"]


def test_apply_patch_does_not_mutate_the_base():
    base = {"cover_letter": {"closing": "Thanks,"}}
    ef.apply_patch(base, [{"path": "cover_letter.closing", "value": "Best,"}])
    assert base["cover_letter"]["closing"] == "Thanks,"


def test_apply_patch_replaces_whole_subtrees():
    base = {"resume_data": {"skills": {"A": ["x"]}}}
    out = ef.apply_patch(base, [
        {"path": "resume_data.skills", "value": {"B": ["y"], "C": ["z"]}}])
    assert list(out["resume_data"]["skills"]) == ["B", "C"]


def test_severity_ladder_is_inclusive_upward():
    report = "### MEDIUM - voice slip"
    assert ef.severity_at_least(report, "LOW") is True
    assert ef.severity_at_least(report, "MEDIUM") is True
    assert ef.severity_at_least(report, "CRITICAL") is False


def test_clean_verdict_recognised_from_the_documented_format():
    assert ef.is_clean_verdict("## Fact-check summary\n- Verdict: CLEAN\n") is True
    assert ef.is_clean_verdict("CLEAN - no findings") is True


def test_nit_only_report_counts_as_clean():
    """A NIT on a compliant draft is noise, not a false positive worth failing."""
    assert ef.is_clean_verdict("### NIT - consider tightening paragraph 2") is True


def test_grade_defect_case_requires_keyword_and_severity():
    case = {"id": "invented_metric", "expect":
            {"min_severity": "CRITICAL", "keywords": ["32%", "invent"]}}
    caught = ef.grade_case(case, "### CRITICAL - invented metric in bullet 2")
    assert caught["passed"] is True and "invent" in caught["detail"]

    missed = ef.grade_case(case, "### NIT - consider rewording bullet 2")
    assert missed["passed"] is False


def test_grade_defect_case_flags_correct_finding_at_too_low_a_severity():
    case = {"id": "rounded_metric", "expect":
            {"min_severity": "CRITICAL", "keywords": ["100,000"]}}
    result = ef.grade_case(case, "### LOW - 100,000 looks rounded")
    assert result["passed"] is False
    assert result["detected"] is True
    assert "below CRITICAL" in result["detail"]


def test_summary_separates_a_miss_from_an_under_severity_finding():
    """Live run showed both voice defects caught but filed NIT, which the old
    report called MISSED. A defect nobody named can reach an employer; one filed
    a rung low still reaches the report."""
    results = [
        {"id": "under", "kind": "defect", "passed": False, "detected": True, "detail": ""},
        {"id": "gone", "kind": "defect", "passed": False, "detected": False, "detail": ""},
        {"id": "ok", "kind": "defect", "passed": True, "detected": True, "detail": ""},
    ]
    summary = ef.summarize(results)
    assert summary["missed"] == ["gone"]
    assert summary["under_severity"] == ["under"]
    assert summary["detected"] == 2
    assert summary["detection_rate"] == pytest.approx(2 / 3)
    assert summary["recall"] == pytest.approx(1 / 3)


def test_grade_control_case_fails_on_a_false_positive():
    case = {"id": "clean_control_a", "clean": True}
    assert ef.grade_case(case, "- Verdict: CLEAN")["passed"] is True
    flagged = ef.grade_case(case, "### CRITICAL - invented metric")
    assert flagged["passed"] is False
    assert "false positive" in flagged["detail"]


def test_summary_penalises_a_checker_that_flags_everything():
    """Perfect recall bought with false positives must not grade well."""
    results = [
        {"id": "d1", "kind": "defect", "passed": True, "detected": True, "detail": ""},
        {"id": "d2", "kind": "defect", "passed": True, "detected": True, "detail": ""},
        {"id": "c1", "kind": "control", "passed": False, "detail": ""},
        {"id": "c2", "kind": "control", "passed": False, "detail": ""},
    ]
    summary = ef.summarize(results)
    assert summary["recall"] == 1.0
    assert summary["precision"] == 0.0
    assert summary["grade"] == "F"
    assert summary["false_positives"] == ["c1", "c2"]


def test_summary_reports_missed_defects_by_id():
    results = [
        {"id": "people_management", "kind": "defect", "passed": False, "detected": False, "detail": ""},
        {"id": "em_dash", "kind": "defect", "passed": True, "detected": True, "detail": ""},
        {"id": "c1", "kind": "control", "passed": True, "detail": ""},
    ]
    summary = ef.summarize(results)
    assert summary["missed"] == ["people_management"]
    assert summary["recall"] == 0.5


# ── Fixture integrity ────────────────────────────────────────────────────────

def test_every_case_patches_cleanly_and_declares_expectations():
    base, cases = ef.load_cases()
    assert len(cases) >= 10
    for case in cases:
        document = ef.apply_patch(base, case["patch"])
        assert set(document) == {"resume_data", "cover_letter"}
        if case.get("clean"):
            assert not case.get("expect")
        else:
            assert case["expect"]["keywords"], case["id"]
            assert case["expect"]["min_severity"] in ef.SEVERITIES, case["id"]


def test_case_ids_are_unique():
    _, cases = ef.load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))


def test_suite_has_clean_controls():
    """Without controls the eval cannot distinguish a good checker from a noisy one."""
    _, cases = ef.load_cases()
    assert sum(1 for c in cases if c.get("clean")) >= 2


def test_every_defect_case_actually_changes_the_document():
    base, cases = ef.load_cases()
    for case in cases:
        if case.get("clean"):
            continue
        assert ef.apply_patch(base, case["patch"]) != base, case["id"]


def test_ground_truth_files_load():
    truth = ef.load_ground_truth()
    assert set(truth) == {"resume_master", "personal_statement", "claims_ground_truth"}
    assert "Northwind Logistics" in truth["resume_master"]


def test_prompt_inlines_every_ground_truth_file():
    base, _ = ef.load_cases()
    prompt = ef.build_prompt(base, ef.load_ground_truth())
    for marker in ("resume_master.md", "personal_statement.md", "claims_ground_truth.md"):
        assert marker in prompt
    assert "Northwind Logistics" in prompt


def test_fixtures_carry_no_real_identity():
    """The eval must never reach for the real profile; canary the owner's markers."""
    blob = json.dumps(ef.load_cases()) + json.dumps(ef.load_ground_truth())
    for canary in ("simonelli", "jsimo", "spectrum", "gmail.com"):
        assert canary not in blob.lower()


@pytest.mark.parametrize("case_id", [
    "invented_metric", "people_management", "phase_overstatement", "em_dash"])
def test_headline_defects_are_present_in_the_suite(case_id):
    _, cases = ef.load_cases()
    assert case_id in {c["id"] for c in cases}
