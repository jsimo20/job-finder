"""Tests for the deterministic half of the skill-term eval. No network, no tokens."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_finder import eval_skill_terms as E, eval_spread, skill_terms

FIXTURES = Path(__file__).parent / "fixtures"
POOL = skill_terms.parse_source_pool(
    (FIXTURES / "skill_pool_sample.md").read_text(encoding="utf-8"))
SKILLS, CASES = E.load_cases(FIXTURES / "skillterms")
BY_ID = {c["id"]: c for c in CASES}


def _out(subs=(), rejected=()):
    return {"substitutions": list(subs), "rejected": list(rejected)}


def _sub(term, replaces, confidence=0.95):
    return {"term": term, "replaces": replaces, "evidence": "pool: AI/LLM",
            "confidence": confidence, "justification": "same capability"}


def test_the_suite_balances_swaps_against_holds():
    """A mapper that proposes nothing must not be able to score well, so the
    cases where a swap is right match the cases where it is wrong."""
    kinds = [c["kind"] for c in CASES]
    assert kinds.count("swap") == 4
    assert kinds.count("gap") + kinds.count("covered") == 5


def test_an_already_covered_term_must_not_be_swapped():
    """One in, one out: a redundant swap takes a real skill off the resume to add
    a word that is already on it."""
    case = BY_ID["covered-chatgpt"]
    assert E.grade_case(case, _out(), POOL)["passed"] is True
    bad = _out([_sub("ChatGPT", "SQL")])
    assert E.grade_case(case, bad, POOL)["passed"] is False


def test_covered_and_gap_share_the_precision_bucket():
    results = [E.grade_case(c, _out(), POOL) for c in CASES]
    s = E.summarize(results)
    assert s["covered_total"] == 1 and s["covered_left_alone"] == 1
    assert s["precision"] == 1.0


def test_json_is_parsed_out_of_prose_on_either_side():
    text = ('Here is my analysis.\n{"substitutions": [], "rejected": []}\n'
            "The JD is really asking for telemetry work.")
    assert E.parse_output(text) == {"substitutions": [], "rejected": []}


def test_a_response_with_no_usable_json_is_not_a_pass():
    assert E.parse_output("I could not complete this request.") is None
    r = E.grade_case(BY_ID["swap-lovable-for-figma"], None, POOL)
    assert r["passed"] is False


def test_an_earlier_json_object_without_substitutions_is_skipped():
    text = '{"note": "thinking"} then {"substitutions": [], "rejected": []}'
    assert E.parse_output(text) == {"substitutions": [], "rejected": []}


def test_taking_an_honest_keyword_passes():
    out = _out([_sub("Lovable", "Figma")])
    assert E.grade_case(BY_ID["swap-lovable-for-figma"], out, POOL)["passed"] is True


def test_missing_an_honest_keyword_fails():
    r = E.grade_case(BY_ID["swap-lovable-for-figma"], _out(), POOL)
    assert r["passed"] is False
    assert "did not swap" in r["detail"]


def test_swapping_the_right_word_for_the_wrong_reason_fails():
    """Lovable for SQL is the right output attached to nonsense."""
    out = _out([_sub("Lovable", "SQL")])
    r = E.grade_case(BY_ID["swap-lovable-for-figma"], out, POOL)
    assert r["passed"] is False
    assert "not a term it names" in r["detail"]


def test_refusing_a_gap_passes_and_naming_it_is_recorded():
    named = _out(rejected=[{"term": "Databricks", "reason": "not in the pool"}])
    r = E.grade_case(BY_ID["gap-databricks"], named, POOL)
    assert r["passed"] is True and r["named_gap"] is True

    silent = E.grade_case(BY_ID["gap-databricks"], _out(), POOL)
    assert silent["passed"] is True and silent["named_gap"] is False
    assert "did not name it" in silent["detail"]


def test_swapping_in_a_gap_fails():
    """The failure the whole system exists to prevent."""
    out = _out([_sub("Databricks", "SQL")])
    r = E.grade_case(BY_ID["gap-databricks"], out, POOL)
    assert r["passed"] is False
    assert "Databricks" in r["detail"]


@pytest.mark.parametrize("case_id", ["gap-assembly-line", "gap-kubernetes",
                                     "gap-transformer-training"])
def test_every_gap_case_fails_when_swapped_in(case_id):
    case = BY_ID[case_id]
    out = _out([_sub(case["term"], "SQL")])
    assert E.grade_case(case, out, POOL)["passed"] is False


def test_structure_is_graded_separately_from_judgment():
    """A right call recorded wrongly is a different defect from a wrong call."""
    out = _out([_sub("Lovable", "Figma", confidence=0.4)])
    r = E.grade_case(BY_ID["swap-lovable-for-figma"], out, POOL)
    assert r["passed"] is True          # the judgment was right
    assert "low_confidence" in r["structural"]   # the record was not


def test_a_mapper_that_refuses_everything_does_not_score_well():
    results = [E.grade_case(c, _out(), POOL) for c in CASES]
    s = E.summarize(results)
    assert s["gaps_refused"] == 4 and s["swaps_taken"] == 0
    assert s["score"] == 0.0
    assert s["grade"] == "F"


def test_a_perfect_run_grades_a():
    results = []
    for c in CASES:
        out = _out() if c["kind"] in ("gap", "covered") else _out(
            [_sub(c["term"], c["expect_replaces_any"][0])])
        results.append(E.grade_case(c, out, POOL))
    s = E.summarize(results)
    assert s["score"] == 1.0 and s["grade"] == "A"


def test_the_spread_names_cases_that_flipped_between_runs():
    runs = [
        {"score": 0.9, "results": [{"id": "a", "passed": True},
                                   {"id": "b", "passed": True}]},
        {"score": 0.7, "results": [{"id": "a", "passed": True},
                                   {"id": "b", "passed": False}]},
    ]
    out = eval_spread.format_spread(runs)
    assert "spread : 0.20" in out
    assert "unstable cases: b" in out
    assert "a" not in out.split("unstable cases:")[1].split("\n")[0]


def test_a_single_run_reports_no_spread():
    out = eval_spread.format_spread([{"score": 0.9, "results": []}])
    assert "median" in out
    assert "spread" not in out


def test_the_shipped_prompt_is_what_gets_graded():
    """Not a copy: a prompt edit has to change the measurement."""
    assert E.AGENT_PATH.exists()
    body = E.strip_frontmatter(E.AGENT_PATH.read_text(encoding="utf-8"))
    assert not body.startswith("---")
    assert "90%" in body


def test_the_real_profile_is_never_read():
    """Ground truth is synthetic, so a failing case cannot be fixed by quietly
    making the candidate more qualified."""
    assert "tests" in E.POOL_PATH.parts and "fixtures" in E.POOL_PATH.parts
    raw = json.loads((FIXTURES / "skillterms" / "cases.json").read_text(encoding="utf-8"))
    assert "Synthetic" in raw["_comment"]
