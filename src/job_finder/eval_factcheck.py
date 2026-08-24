"""Recall and precision eval for the materials-fact-checker subagent.

The fact-checker is the last automated check between a fabricated claim and a
PDF that goes to an employer. Under the interactive `/job-apply` loop the user
reviews every finding, so a miss is recoverable. Running unattended it is the
only check, and until now nobody had measured whether it catches a defect that
was deliberately planted.

Each case in tests/fixtures/factcheck/cases.json is a clean draft plus exactly
one defect, so a miss points at one rule. Clean controls carry no defect at all
and measure the opposite failure: a checker that flags everything scores
perfect recall and is useless.

The system prompt is read from .claude/agents/materials-fact-checker.md, so
this grades the real agent definition rather than a copy that can drift. Two
deliberate differences from a live dispatch:

- Ground truth is inlined into the user message instead of being read off disk
  by the agent, which keeps the eval hermetic and free of personal data. This
  grades the checker's judgment, not its file-reading.
- The synthetic ground truth in tests/fixtures/factcheck/ describes a person
  who does not exist, so the eval never touches the real profile.

Detection is graded by substring match against the case's expected keywords.
That is crude, and it can only ever be a floor: a report that identifies the
defect in wording no keyword anticipates counts as a miss. Prefer adding
keywords over loosening the check.

Costs real tokens (one call per case), so it is never part of the pytest run.

Usage:
    python -m job_finder.eval_factcheck
    python -m job_finder.eval_factcheck --case invented_metric --show-report
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 2000

_BOM = chr(0xfeff)
_REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_PATH = _REPO_ROOT / ".claude" / "agents" / "materials-fact-checker.md"
FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "factcheck"

SEVERITIES = ["NIT", "LOW", "MEDIUM", "CRITICAL"]
GRADE_BANDS = [(0.95, "A"), (0.85, "B"), (0.70, "C"), (0.50, "D"), (0.0, "F")]


def strip_frontmatter(text: str) -> str:
    """Return an agent definition's body, dropping its YAML frontmatter."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4:].lstrip("\n") if end != -1 else text


def apply_patch(base: dict[str, Any], patch: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply dotted-path overrides to a deep copy of the base document.

    Integer path segments index into lists, so
    'resume_data.experience.0.bullets.1' addresses one bullet.
    """
    doc = json.loads(json.dumps(base))
    for op in patch:
        segments = op["path"].split(".")
        target = doc
        for segment in segments[:-1]:
            target = target[int(segment)] if segment.isdigit() else target[segment]
        last = segments[-1]
        if last.isdigit():
            target[int(last)] = op["value"]
        else:
            target[last] = op["value"]
    return doc


def load_cases(fixture_dir: Path = FIXTURE_DIR) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    spec = json.loads((fixture_dir / "cases.json").read_text(encoding="utf-8"))
    return spec["base"], spec["cases"]


def load_ground_truth(fixture_dir: Path = FIXTURE_DIR) -> dict[str, str]:
    return {
        name: (fixture_dir / f"{name}.md").read_text(encoding="utf-8")
        for name in ("resume_master", "personal_statement", "session_context")
    }


def build_prompt(document: dict[str, Any], ground_truth: dict[str, str]) -> str:
    return f"""The ground-truth files are inlined below; you have no file access
in this run, so treat these as the complete source of truth.

<resume_master.md>
{ground_truth['resume_master']}
</resume_master.md>

<personal_statement.md>
{ground_truth['personal_statement']}
</personal_statement.md>

<session_context.md>
{ground_truth['session_context']}
</session_context.md>

company: Meridian Freight

jd_text: Meridian Freight is hiring a Senior Product Manager for our carrier
platform. You will own partner integrations, onboarding, and the exception
handling that keeps freight moving. We are looking for someone who has built
integration surfaces at scale and can talk to operations teams in their own
language.

resume_data:
{json.dumps(document['resume_data'], indent=2)}

cover_letter:
{json.dumps(document['cover_letter'], indent=2)}

Produce your fact-check report in the documented output format."""


def severity_at_least(report: str, minimum: str) -> bool:
    """Whether the report carries a finding at or above the given severity."""
    floor = SEVERITIES.index(minimum)
    return any(level in report for level in SEVERITIES[floor:])


def is_clean_verdict(report: str) -> bool:
    if re.search(r"verdict:\s*clean", report, re.I) or re.search(r"^clean\b", report.strip(), re.I):
        return True
    return not severity_at_least(report, "MEDIUM")


def grade_case(case: dict[str, Any], report: str) -> dict[str, Any]:
    """Score one report against what the case planted.

    Clean controls invert the test: any CRITICAL or MEDIUM finding on a
    compliant draft is a false positive, which is how over-flagging shows up.
    """
    if case.get("clean"):
        passed = is_clean_verdict(report)
        return {
            "id": case["id"], "kind": "control", "passed": passed,
            "detail": "no CRITICAL/MEDIUM findings" if passed
                      else "false positive on a compliant draft",
        }

    expect = case["expect"]
    lowered = report.lower()
    hit = next((kw for kw in expect["keywords"] if kw.lower() in lowered), None)
    severe_enough = severity_at_least(report, expect["min_severity"])

    # Detection and severity are reported apart because they fail differently.
    # A defect nobody mentioned can reach an employer. One that was mentioned
    # but filed a rung too low still reaches the report the caller reads, and
    # is a calibration disagreement rather than a hole.
    if not hit:
        detail = "defect not mentioned"
    elif not severe_enough:
        detail = f"found, but filed below {expect['min_severity']}"
    else:
        detail = f"matched on '{hit}'"
    return {"id": case["id"], "kind": "defect", "detected": bool(hit),
            "passed": bool(hit) and severe_enough, "detail": detail}


def run_case(client: anthropic.Anthropic, system_prompt: str, document: dict[str, Any],
             ground_truth: dict[str, str]) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": build_prompt(document, ground_truth)}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def evaluate(case_filter: str | None = None, fixture_dir: Path = FIXTURE_DIR,
             show_report: bool = False) -> dict[str, Any]:
    # The key lives in the repo's .env, same as the pipeline; only cli.py loaded
    # it before, so a module run straight from the command line saw nothing.
    load_dotenv(override=True)
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().replace(_BOM, "")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set (checked the environment and .env)")

    system_prompt = strip_frontmatter(AGENT_PATH.read_text(encoding="utf-8"))
    base, cases = load_cases(fixture_dir)
    ground_truth = load_ground_truth(fixture_dir)
    if case_filter:
        cases = [c for c in cases if c["id"] == case_filter]
        if not cases:
            raise SystemExit(f"no case named {case_filter}")

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    for case in cases:
        document = apply_patch(base, case["patch"])
        report = run_case(client, system_prompt, document, ground_truth)
        result = grade_case(case, report)
        results.append(result)
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"  [{mark}] {result['id']:<28} {result['detail']}")
        if show_report:
            print("\n" + report + "\n" + "-" * 70)

    return summarize(results)


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    defects = [r for r in results if r["kind"] == "defect"]
    controls = [r for r in results if r["kind"] == "control"]
    caught = sum(1 for r in defects if r["passed"])
    detected = sum(1 for r in defects if r.get("detected"))
    clean = sum(1 for r in controls if r["passed"])

    recall = caught / len(defects) if defects else 0.0
    precision = clean / len(controls) if controls else 1.0
    # Harmonic, not arithmetic: a checker that flags every draft has perfect
    # recall and is useless, and averaging would still hand it a passing band.
    combined = (2 * recall * precision / (recall + precision)
                if recall + precision else 0.0)
    return {
        "results": results,
        "recall": recall, "caught": caught, "defects": len(defects),
        "precision": precision, "clean": clean, "controls": len(controls),
        "detected": detected,
        "detection_rate": detected / len(defects) if defects else 0.0,
        "missed": [r["id"] for r in defects if not r.get("detected")],
        "under_severity": [r["id"] for r in defects
                           if r.get("detected") and not r["passed"]],
        "false_positives": [r["id"] for r in controls if not r["passed"]],
        "grade": next(g for floor, g in GRADE_BANDS if combined >= floor),
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"\n{'=' * 70}")
    print(f"FACT-CHECKER  -  grade {summary['grade']}")
    print(f"  detection {summary['detected']}/{summary['defects']} planted defects "
          f"noticed at all ({summary['detection_rate']:.0%})")
    print(f"  recall    {summary['caught']}/{summary['defects']} of those filed at the "
          f"expected severity ({summary['recall']:.0%})")
    print(f"  precision {summary['clean']}/{summary['controls']} clean drafts left alone "
          f"({summary['precision']:.0%})")
    if summary["missed"]:
        print(f"\n  NOT DETECTED (could reach an employer): "
              f"{', '.join(summary['missed'])}")
    if summary["under_severity"]:
        print(f"\n  UNDER-SEVERITY: {', '.join(summary['under_severity'])}")
        print("  Caught, filed lower than expected. The finding still reaches the report,")
        print("  so this is a calibration disagreement, not a hole.")
    if summary["false_positives"]:
        print(f"\n  FALSE POSITIVES (noise on clean drafts): "
              f"{', '.join(summary['false_positives'])}")
    if not summary["missed"] and not summary["false_positives"]:
        print("\n  Nothing planted went unnoticed, and no clean draft was flagged.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", help="run a single case by id")
    ap.add_argument("--show-report", action="store_true",
                    help="print each full fact-check report")
    ap.add_argument("--fixtures", type=Path, default=FIXTURE_DIR)
    args = ap.parse_args()

    print(f"Running fact-checker eval against {AGENT_PATH.name} on {MODEL}\n")
    summary = evaluate(args.case, args.fixtures, args.show_report)
    print_summary(summary)
    # Under-severity does not fail the run; an undetected defect does.
    return 0 if not summary["missed"] else 1


if __name__ == "__main__":
    sys.exit(main())
