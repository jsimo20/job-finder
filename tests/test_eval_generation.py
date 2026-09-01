"""Tests for the deterministic half of the generation eval. No network, no tokens."""
from __future__ import annotations

import httpx
import pytest

from job_finder import applied, eval_generation as E, letter_linter, state


CLEAN_LETTER = {
    "closing": "Thanks,",
    "paragraphs": [
        "Most carrier integrations get built one at a time and maintained forever. "
        "Meridian is turning them into configuration, which moves the weight onto "
        "onboarding. That weight is what I have spent three years on.",
        "That work serves 340 freight partners.",
        "Those partners came from the self-serve onboarding flow.",
        "Getting to work on any of that means leaving my current role. I look "
        "forward to discussing this opportunity in greater detail with you.",
    ],
}


def test_parse_letter_accepts_json_wrapped_in_prose():
    text = 'Here you go:\n{"paragraphs": ["one", "two"], "closing": "Thanks,"}\nHope that helps.'
    assert E.parse_letter(text)["paragraphs"] == ["one", "two"]


@pytest.mark.parametrize("text", [
    "I could not complete this request.",
    '{"salutation": "Hi"}',          # no paragraphs key
    '{"paragraphs": "not a list"}',
    "{ this is not json }",
])
def test_parse_letter_rejects_anything_unusable(text):
    assert E.parse_letter(text) is None


def test_a_clean_letter_and_a_clean_report_passes():
    grade = E.grade_one(CLEAN_LETTER, "## Fact-check summary\n- Verdict: CLEAN")
    assert grade["passed"] is True
    assert grade["lint_critical"] == []


def test_a_linter_critical_fails_the_letter():
    bad = {**CLEAN_LETTER,
           "paragraphs": ["Your posting caught my attention.", "Then this."]}
    grade = E.grade_one(bad, "## Fact-check summary\n- Verdict: CLEAN")
    assert grade["passed"] is False
    assert any("reaction_opener" in f for f in grade["lint_critical"])


def test_a_fact_checker_critical_fails_the_letter():
    grade = E.grade_one(CLEAN_LETTER, "### CRITICAL — invented metric\n**Issue:** made up")
    assert grade["passed"] is False
    assert grade["check_critical"] is True


def test_a_medium_finding_does_not_fail_the_letter():
    grade = E.grade_one(CLEAN_LETTER, "### MEDIUM — voice slip\n**Issue:** minor")
    assert grade["passed"] is True
    assert grade["check_medium"] is True


def test_advisories_are_reported_without_failing():
    letter = {**CLEAN_LETTER,
              "paragraphs": ["The Directory is public, which is a harder place to earn it.",
                             "Golf remains difficult. I look forward to discussing this "
                             "opportunity in greater detail with you."]}
    grade = E.grade_one(letter, "- Verdict: CLEAN")
    assert grade["passed"] is True
    assert grade["lint_advisory"]


def test_grade_bands_ignore_postings_that_never_drafted():
    """A model that returns junk should not be graded as if it wrote a bad letter."""
    results = [
        {"posting": {}, "grade": {"passed": True}},
        {"posting": {}, "grade": {"passed": True}},
        {"posting": {}},  # draft failed
    ]
    summary = E.grade(results)
    assert summary["drafted"] == 2
    assert summary["attempted"] == 3
    assert summary["pass_rate"] == 1.0
    assert summary["band"] == "A"


def test_grade_reports_per_posting_outcomes_for_repeat_runs():
    """--repeat names the postings that flipped, which needs a per-case list."""
    results = [
        {"posting": {"company": "Acme"}, "grade": {"passed": True}},
        {"posting": {"company": "Borealis"}, "grade": {"passed": False}},
        {"posting": {"company": "Cyngus"}},  # draft failed
    ]
    assert E.grade(results)["results"] == [
        {"id": "Acme", "passed": True},
        {"id": "Borealis", "passed": False},
        {"id": "Cyngus", "passed": False},
    ]


def test_grade_of_an_empty_run_is_f_not_a_crash():
    assert E.grade([])["band"] == "F"


@pytest.fixture
def tracked(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state.upsert_company({"name": "Acme", "ats_provider": "greenhouse",
                          "ats_slug": "acme"}, db)
    state.upsert_company({"name": "Cyngus", "ats_provider": "workday",
                          "ats_slug": "cyngus/wd1/careers"}, db)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [
            {"id": 1, "title": "Staff Engineer", "content": "x" * 900,
             "absolute_url": "https://x/1"},
            {"id": 2, "title": "Senior Product Manager", "content": "y" * 900,
             "absolute_url": "https://x/2"},
            {"id": 3, "title": "Principal Product Manager", "content": "z" * 900,
             "absolute_url": "https://x/3"},
        ]})
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return db


def test_it_picks_a_product_manager_posting(tracked):
    got = E.held_out_postings(1, db_path=tracked)
    assert [p["title"] for p in got] == ["Senior Product Manager"]


def test_an_applied_posting_is_held_out(tracked):
    """Grading against a letter that already exists measures nothing."""
    applied.record_applied(external_id="2", company="Acme",
                           title="Senior Product Manager", db_path=tracked)
    got = E.held_out_postings(1, db_path=tracked)
    assert [p["title"] for p in got] == ["Principal Product Manager"]


def test_providers_without_a_cheap_board_are_skipped(tracked):
    """Workday has no light listing endpoint, so it contributes no postings."""
    got = E.held_out_postings(5, db_path=tracked)
    assert {p["company"] for p in got} == {"Acme"}


def test_a_board_that_errors_does_not_abort_the_run(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state.upsert_company({"name": "Acme", "ats_provider": "greenhouse",
                          "ats_slug": "acme"}, db)
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(
        transport=httpx.MockTransport(
            lambda r: (_ for _ in ()).throw(httpx.ConnectError("no route"))), **kw))
    assert E.held_out_postings(1, db_path=db) == []


def test_the_linter_and_the_eval_agree_on_what_blocks():
    """grade_one must not invent its own severity model."""
    assert letter_linter.CRITICAL == "CRITICAL"
    bad = {**CLEAN_LETTER, "paragraphs": ["A letter with an em-dash — right here."]}
    assert E.grade_one(bad, "- Verdict: CLEAN")["passed"] is False
