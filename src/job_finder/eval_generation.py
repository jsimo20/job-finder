"""Does the drafter write a good cover letter unattended? Spends tokens.

`eval_factcheck` measures the checker. This measures the thing being checked.
Under `/job-apply` a human reads the draft before it renders; under the batch
skill in Cowork nobody does, and the drafting prompt (the cover-letter skill plus
the writing-style file plus the claims ground truth) had never been graded.

The graders are the two that already exist, so there is no new rubric to drift:

- `letter_linter` for the rules that survive as patterns. Zero tokens.
- The `materials-fact-checker` prompt for claims and judgment, read from the
  same agent definition `eval_factcheck` reads.

A letter passes when neither grader reports a CRITICAL. ADVISORY lines and
MEDIUM findings are reported as texture and do not fail it.

Two deliberate differences from `eval_factcheck`:

- **It reads the real profile.** A synthetic person would measure a different
  system, because the drafting prompt's whole job is turning these documents
  into a letter. Output therefore lands in a gitignored directory.
- **The JDs are live, not fixtures.** The question is whether the drafter handles
  an arbitrary real posting, and a frozen JD goes stale while quietly becoming
  the thing the prompt was tuned against. Runs are not reproducible by design;
  the report names the postings it used.

Held-out means held out: any company in the applied ledger is skipped, so this
cannot grade against a letter that already exists.

Roughly 25k tokens per case. Manual, and never part of pytest.

Usage:
    python -m job_finder.eval_generation --n 3
    python -m job_finder.eval_generation --n 1 --show-letter
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

import anthropic
import httpx
from dotenv import load_dotenv

from . import (applied, eval_factcheck, eval_spread, job_apply, letter_linter,
               settings, state)

DRAFT_MODEL = "claude-opus-5"
DRAFT_MAX_TOKENS = 3000
TITLE_RE = re.compile(r"product manager", re.I)
GRADE_BANDS = [(0.95, "A"), (0.85, "B"), (0.70, "C"), (0.50, "D"), (0.0, "F")]

_BOM = chr(0xfeff)
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _client() -> anthropic.Anthropic:
    load_dotenv(_REPO_ROOT / ".env")
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().replace(_BOM, "")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set; this eval spends tokens.")
    return anthropic.Anthropic(api_key=key)


# --- held-out postings ------------------------------------------------------

def _greenhouse(slug: str, c: httpx.Client) -> list[dict[str, Any]]:
    r = c.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    r.raise_for_status()
    return [{"external_id": str(j["id"]), "title": j["title"],
             "jd": _strip_html(j.get("content", "")),
             "url": j.get("absolute_url", "")}
            for j in r.json().get("jobs", [])]


def _ashby(slug: str, c: httpx.Client) -> list[dict[str, Any]]:
    r = c.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false")
    r.raise_for_status()
    return [{"external_id": str(j["id"]), "title": j["title"],
             "jd": _strip_html(j.get("descriptionHtml") or j.get("descriptionPlain") or ""),
             "url": j.get("jobUrl", "")}
            for j in r.json().get("jobs", [])]


BOARDS = {"greenhouse": _greenhouse, "ashby": _ashby}


def _strip_html(raw: str) -> str:
    import html
    text = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def held_out_postings(n: int, *, db_path=state.DEFAULT_STATE_DB,
                      seed: int | None = None) -> list[dict[str, Any]]:
    """Live PM postings at tracked companies the user has not applied to."""
    applied_ids = applied.applied_external_ids(db_path=db_path)
    companies = [c for c in state.list_companies(db_path)
                 if (c.get("ats_provider") or "").lower() in BOARDS]
    random.Random(seed).shuffle(companies)

    out: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for company in companies:
            if len(out) >= n:
                break
            lister = BOARDS[company["ats_provider"].lower()]
            try:
                jobs = lister(company["ats_slug"], client)
            except Exception as exc:
                print(f"  skipped {company['name']}: {exc}", file=sys.stderr)
                continue
            for job in jobs:
                if (TITLE_RE.search(job["title"]) and len(job["jd"]) > 800
                        and job["external_id"] not in applied_ids):
                    out.append({**job, "company": company["name"]})
                    break
    return out


# --- drafting ---------------------------------------------------------------

def ground_truth(config: job_apply.Config) -> dict[str, str]:
    """The documents the real drafting prompt loads, read from the real profile."""
    docs = {
        "resume_master": config.inputs_dir / "resume_master.md",
        "personal_statement": config.inputs_dir / "personal_statement.md",
        "claims_ground_truth": config.claims_ground_truth,
        "writing_style": config.writing_style,
        "cover_letter_skill": config.resume_skill.parent.parent
        / "cover_letter_skill" / "SKILL.md",
    }
    missing = [str(p) for p in docs.values() if not p.is_file()]
    if missing:
        raise SystemExit("Cannot grade the drafter without its inputs:\n  "
                         + "\n  ".join(missing))
    return {k: v.read_text(encoding="utf-8") for k, v in docs.items()}


def draft_prompt(posting: dict[str, Any], gt: dict[str, str]) -> str:
    return f"""Draft the cover letter for the posting below, following the
instructions exactly. You have no file access in this run, so the documents
inlined here are the complete source of truth. Invent nothing that is not in
them.

<writing_style.md>
{gt['writing_style']}
</writing_style.md>

<cover_letter_skill/SKILL.md>
{gt['cover_letter_skill']}
</cover_letter_skill/SKILL.md>

<claims_ground_truth.md>
{gt['claims_ground_truth']}
</claims_ground_truth.md>

<resume_master.md>
{gt['resume_master']}
</resume_master.md>

<personal_statement.md>
{gt['personal_statement']}
</personal_statement.md>

company: {posting['company']}
role: {posting['title']}

<jd_text>
{posting['jd'][:12000]}
</jd_text>

Return ONLY a JSON object, no prose around it, with keys: date, recipient,
salutation, paragraphs (a list of 4 strings), closing, title_subtitle."""


def parse_letter(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        letter = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return letter if isinstance(letter.get("paragraphs"), list) else None


def draft(client: anthropic.Anthropic, posting: dict[str, Any],
          gt: dict[str, str], model: str) -> dict[str, Any] | None:
    resp = client.messages.create(
        model=model, max_tokens=DRAFT_MAX_TOKENS,
        messages=[{"role": "user", "content": draft_prompt(posting, gt)}])
    return parse_letter("".join(b.text for b in resp.content if b.type == "text"))


# --- grading ----------------------------------------------------------------

def fact_check(client: anthropic.Anthropic, letter: dict[str, Any],
               posting: dict[str, Any], gt: dict[str, str]) -> str:
    system = eval_factcheck.strip_frontmatter(
        eval_factcheck.AGENT_PATH.read_text(encoding="utf-8"))
    prompt = f"""The ground-truth files are inlined below; you have no file access
in this run, so treat these as the complete source of truth.

<resume_master.md>
{gt['resume_master']}
</resume_master.md>

<personal_statement.md>
{gt['personal_statement']}
</personal_statement.md>

<claims_ground_truth.md>
{gt['claims_ground_truth']}
</claims_ground_truth.md>

<writing_style.md>
{gt['writing_style']}
</writing_style.md>

company: {posting['company']}

jd_text:
{posting['jd'][:8000]}

resume_data: (not drafted in this run; check the cover letter only)

cover_letter:
{json.dumps(letter, indent=2)}

Produce your fact-check report in the documented output format."""
    resp = client.messages.create(
        model=eval_factcheck.MODEL, max_tokens=eval_factcheck.MAX_TOKENS,
        system=system, messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in resp.content if b.type == "text")


def grade_one(letter: dict[str, Any], report: str) -> dict[str, Any]:
    findings = letter_linter.lint(letter)
    lint_critical = [f for f in findings if f.severity == letter_linter.CRITICAL]
    check_critical = eval_factcheck.severity_at_least(report, "CRITICAL")
    return {
        "passed": not lint_critical and not check_critical,
        "lint_critical": [f"{f.check} ({f.where})" for f in lint_critical],
        "lint_advisory": [f"{f.check} ({f.where})" for f in findings
                          if f.severity == letter_linter.ADVISORY],
        "check_critical": check_critical,
        "check_medium": eval_factcheck.severity_at_least(report, "MEDIUM"),
    }


def grade(results: list[dict[str, Any]]) -> dict[str, Any]:
    graded = [r for r in results if r.get("grade")]
    rate = (sum(1 for r in graded if r["grade"]["passed"]) / len(graded)
            if graded else 0.0)
    return {"drafted": len(graded), "attempted": len(results), "pass_rate": rate,
            "band": next(b for cut, b in GRADE_BANDS if rate >= cut),
            # Per-posting outcomes, so repeated runs can name which postings
            # flipped rather than only showing the rate moving.
            "results": [{"id": r["posting"].get("company", "?"),
                         "passed": bool(r.get("grade", {}).get("passed"))}
                        for r in results]}


def print_report(results: list[dict[str, Any]], summary: dict[str, Any],
                 show_letter: bool) -> None:
    print("\n=== cover letter generation eval ===\n")
    for r in results:
        print(f"{r['posting']['company']} — {r['posting']['title']}")
        print(f"  {r['posting']['url']}")
        if not r.get("grade"):
            print("  DRAFT FAILED: model returned no parseable letter\n")
            continue
        g = r["grade"]
        print(f"  {'PASS' if g['passed'] else 'FAIL'}")
        if g["lint_critical"]:
            print(f"    linter CRITICAL: {', '.join(g['lint_critical'])}")
        if g["check_critical"]:
            print("    fact-checker: CRITICAL finding")
        elif g["check_medium"]:
            print("    fact-checker: MEDIUM finding (does not fail)")
        if g["lint_advisory"]:
            print(f"    advisory: {', '.join(g['lint_advisory'])}")
        if show_letter:
            for i, para in enumerate(r["letter"]["paragraphs"], 1):
                print(f"\n    [{i}] {para}")
        print()
    print(f"  drafted   {summary['drafted']}/{summary['attempted']} postings")
    print(f"  pass rate {summary['pass_rate']:.0%}  grade {summary['band']}")
    print("\n  Neither grader can tell whether the opening's contrast is true.")
    print("  Read one letter yourself; a manufactured departure passes every check.\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=3, help="how many postings to draft for")
    ap.add_argument("--model", default=DRAFT_MODEL, help="the drafting model")
    ap.add_argument("--seed", type=int, help="fix the company shuffle")
    ap.add_argument("--show-letter", action="store_true")
    ap.add_argument("--repeat", type=int, default=1,
                    help="draft the same postings N times and report the spread")
    args = ap.parse_args(argv)

    config = job_apply.load_config(settings.require_profile())
    gt = ground_truth(config)
    # Pinned outside the repeat loop on purpose: repeating is for the drafter's
    # variance, and re-shuffling the postings would confound it with the
    # postings' own difficulty.
    postings = held_out_postings(args.n, seed=args.seed)
    if not postings:
        print("No held-out PM postings found on the tracked boards.")
        return 3

    client = _client()
    runs = []
    for attempt in range(max(1, args.repeat)):
        if args.repeat > 1:
            print(f"\nrun {attempt + 1} of {args.repeat}")
        results = []
        for posting in postings:
            print(f"drafting {posting['company']}...", file=sys.stderr)
            letter = draft(client, posting, gt, args.model)
            if letter is None:
                results.append({"posting": posting})
                continue
            report = fact_check(client, letter, posting, gt)
            results.append({"posting": posting, "letter": letter,
                            "grade": grade_one(letter, report), "report": report})
        summary = grade(results)
        print_report(results, summary, args.show_letter)
        runs.append(summary)

    if len(runs) > 1:
        print(eval_spread.format_spread(runs, score_key="pass_rate", case_key="results"))
    return 0 if min(r["pass_rate"] for r in runs) >= 0.7 else 1


if __name__ == "__main__":
    sys.exit(main())
