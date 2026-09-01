"""Does the skill-term mapper swap honest keywords and refuse dishonest ones?

`skill_terms.py` checks the structure of a swap and cannot check the judgment.
This measures the judgment, which is the part that reaches an employer.

Each case is one JD built around a single term repeated the way a real posting
repeats its central skill. Half the cases are terms the mapper **should** swap in
(the pool holds the same thing under another name); half are genuine gaps it
**must** refuse. Both halves matter and for the same reason as `eval_factcheck`:
a mapper that swaps nothing is safe and useless, and one that swaps everything is
the failure this whole system exists to prevent, so the grade is the harmonic
mean of the two rates.

Ground truth is synthetic — the pool in tests/fixtures/skill_pool_sample.md and
invented postings. The real profile is never read, so a bad case cannot be fixed
by quietly making the candidate more qualified.

    python -m job_finder.eval_skill_terms
    python -m job_finder.eval_skill_terms --repeat 3     # same cases, 3 samples
    python -m job_finder.eval_skill_terms --case gap-databricks --show-report

**Repeat before you act on a change.** A single pass is one sample from a
stochastic grader: 7/8 and 6/8 on the same prompt are not a regression, and
without a spread you cannot tell which one you are looking at.
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

from . import eval_spread, skill_terms

_BOM = chr(0xfeff)

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_PATH = REPO_ROOT / ".claude" / "agents" / "skill-term-mapper.md"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "skillterms"
POOL_PATH = REPO_ROOT / "tests" / "fixtures" / "skill_pool_sample.md"


def strip_frontmatter(text: str) -> str:
    """The agent definition is the shipped prompt; grade that, not a copy."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def load_cases(fixture_dir: Path) -> tuple[list[list[str]], list[dict[str, Any]]]:
    raw = json.loads((fixture_dir / "cases.json").read_text(encoding="utf-8"))
    return raw["skills"], raw["cases"]


def build_prompt(case: dict[str, Any], skills: list[list[str]], pool_md: str) -> str:
    rendered = "\n".join(f"{i+1}. {cat}: {body}" for i, (cat, body) in enumerate(skills))
    return (
        "Here is the claims-ground-truth source pool:\n\n"
        f"{pool_md}\n\n"
        "Here is the current skills section:\n\n"
        f"{rendered}\n\n"
        "Here is the job description:\n\n"
        f"{case['jd']}\n\n"
        "Return the JSON object described in your instructions, then your note."
    )


def parse_output(text: str) -> dict[str, Any] | None:
    """The agent returns JSON then prose; take the first well-formed object."""
    for match in re.finditer(r"\{", text):
        depth = 0
        for i in range(match.start(), len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[match.start():i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict) and "substitutions" in obj:
                        return obj
                    break
    return None


def _mentions(term: str, entries: list[dict[str, Any]], key: str) -> dict | None:
    want = skill_terms.normalize(term)
    for e in entries:
        if not isinstance(e, dict):
            continue
        got = skill_terms.normalize(str(e.get(key, "")))
        if want and (want in got or got in want):
            return e
    return None


def grade_case(case: dict[str, Any], output: dict[str, Any] | None,
               pool: dict[str, list[str]]) -> dict[str, Any]:
    result = {"id": case["id"], "kind": case["kind"], "passed": False,
              "structural": [], "detail": ""}
    if output is None:
        result["detail"] = "no parseable JSON in the response"
        return result

    subs = [s for s in output.get("substitutions", []) if isinstance(s, dict)]
    rejected = [r for r in output.get("rejected", []) if isinstance(r, dict)]

    # Structure is graded separately from judgment: a right call recorded wrongly
    # is a different defect from a wrong call, and only one of them is this
    # agent's reasoning.
    parsed = [skill_terms.Substitution(
        replaces=str(s.get("replaces", "")), term=str(s.get("term", "")),
        evidence=str(s.get("evidence", "")), confidence=float(s.get("confidence", 0) or 0),
        justification=str(s.get("justification", ""))) for s in subs]
    result["structural"] = [f.check for f in
                            skill_terms.check_substitutions(parsed, pool)]

    proposed = _mentions(case["term"], subs, "term")
    if case["kind"] in ("gap", "covered"):
        if proposed:
            result["detail"] = (f'swapped in "{case["term"]}" - {case["why"]}')
            return result
        result["passed"] = True
        named = _mentions(case["term"], rejected, "term")
        kept = "refused" if case["kind"] == "gap" else "left it alone"
        result["detail"] = (f"{kept}, and said why" if named
                            else f"{kept}, but did not name it in `rejected`")
        result["named_gap"] = bool(named)
        return result

    # kind == "swap"
    if not proposed:
        result["detail"] = f'did not swap in "{case["term"]}" - {case["why"]}'
        return result
    replaces = skill_terms.normalize(str(proposed.get("replaces", "")))
    wanted = [skill_terms.normalize(w) for w in case.get("expect_replaces_any", [])]
    if wanted and not any(w in replaces or replaces in w for w in wanted):
        result["detail"] = (f'swapped in "{case["term"]}" but replaced '
                            f'"{proposed.get("replaces")}", not a term it names')
        return result
    result["passed"] = True
    result["detail"] = f'swapped for "{proposed.get("replaces")}"'
    return result


def run_case(client: anthropic.Anthropic, system_prompt: str, prompt: str) -> str:
    response = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS,
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    swaps = [r for r in results if r["kind"] == "swap"]
    # A gap and an already-covered term are one bucket for scoring: both are
    # cases where proposing a swap is the wrong move, and one-in-one-out means a
    # redundant swap costs a real skill off the resume.
    holds = [r for r in results if r["kind"] in ("gap", "covered")]
    gaps = [r for r in results if r["kind"] == "gap"]
    covered = [r for r in results if r["kind"] == "covered"]
    took = sum(1 for r in swaps if r["passed"])
    refused = sum(1 for r in holds if r["passed"])
    recall = took / len(swaps) if swaps else 0.0
    precision = refused / len(holds) if holds else 1.0
    # Harmonic, for the same reason eval_factcheck uses it: a mapper that
    # proposes nothing scores 100% on gaps and is worthless.
    combined = (2 * recall * precision / (recall + precision)
                if recall + precision else 0.0)
    grade = ("A" if combined >= 0.9 else "B" if combined >= 0.8
             else "C" if combined >= 0.7 else "D" if combined >= 0.6 else "F")
    return {
        "swaps_taken": took, "swaps_total": len(swaps),
        "gaps_refused": sum(1 for r in gaps if r["passed"]), "gaps_total": len(gaps),
        "covered_left_alone": sum(1 for r in covered if r["passed"]),
        "covered_total": len(covered),
        "gaps_named": sum(1 for r in holds if r.get("named_gap")),
        "structural": sum(len(r["structural"]) for r in results),
        "recall": recall, "precision": precision,
        "score": combined, "grade": grade,
        "results": results,
    }


def evaluate(*, case_filter: str | None = None, fixture_dir: Path = FIXTURE_DIR,
             show_report: bool = False) -> dict[str, Any]:
    load_dotenv(override=True)
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().replace(_BOM, "")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set (checked the environment and .env)")

    system_prompt = strip_frontmatter(AGENT_PATH.read_text(encoding="utf-8"))
    pool_md = POOL_PATH.read_text(encoding="utf-8")
    pool = skill_terms.parse_source_pool(pool_md)
    skills, cases = load_cases(fixture_dir)
    if case_filter:
        cases = [c for c in cases if c["id"] == case_filter]
        if not cases:
            raise SystemExit(f"no case named {case_filter}")

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    for case in cases:
        text = run_case(client, system_prompt, build_prompt(case, skills, pool_md))
        result = grade_case(case, parse_output(text), pool)
        results.append(result)
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"  [{mark}] {result['id']:<28} {result['detail']}")
        if result["structural"]:
            print(f"         structural: {', '.join(result['structural'])}")
        if show_report:
            print("\n" + text + "\n" + "-" * 70)
    return summarize(results)


def _print_summary(s: dict[str, Any]) -> None:
    print(f"\n  honest keywords taken : {s['swaps_taken']}/{s['swaps_total']}")
    print(f"  gaps refused          : {s['gaps_refused']}/{s['gaps_total']}"
          f"  ({s['gaps_named']} named in `rejected`)")
    if s["covered_total"]:
        print(f"  already-covered left  : {s['covered_left_alone']}/{s['covered_total']}"
              "  (a redundant swap costs a real skill)")
    if s["structural"]:
        print(f"  structural violations : {s['structural']}"
              "  (a right call recorded wrongly)")
    print(f"  grade                 : {s['grade']}  ({s['score']:.2f})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", help="run a single case by id")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run every case N times and report the spread (default 1)")
    ap.add_argument("--show-report", action="store_true",
                    help="print each full agent response")
    ap.add_argument("--fixtures", type=Path, default=FIXTURE_DIR)
    args = ap.parse_args(argv)

    runs = []
    for i in range(max(1, args.repeat)):
        if args.repeat > 1:
            print(f"\nrun {i + 1} of {args.repeat}")
        s = evaluate(case_filter=args.case, fixture_dir=args.fixtures,
                     show_report=args.show_report)
        _print_summary(s)
        runs.append(s)

    if len(runs) > 1:
        print(eval_spread.format_spread(runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
