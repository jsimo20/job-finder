"""Lint the free-text answers typed straight into application forms.

The letter linter only ever sees `cover_letter.json`. Anything written into a
form textarea -- "Why Anthropic?", "describe a developer experience you made
better", any other essay box -- never reaches it, so the voice rules go
unenforced exactly where the writing is most personal. On 2026-09-27 that let
two paragraphs open on "I" straight past a gate that forbids it.

This closes that. Each application folder may carry `form_answers.json`:

    [{"question": "Why Anthropic?", "paragraphs": ["...", "..."]}]

Every answer is run through the letter linter's checks, minus the two that are
letter-specific: a form answer has no "Thanks," closing and no fixed final line.

    python -m scripts.lint_form_answers --date 2026-09-27
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path[:0] = [".cowork-deps", "src"]

from job_finder import letter_linter as LL  # noqa: E402
from job_finder import job_apply, settings  # noqa: E402

# check_closing wants "Thanks,"; check_final_line wants the fixed sign-off.
# Neither belongs to a form answer.
FORM_CHECKS = tuple(c for c in LL.CHECKS
                    if c not in (LL.check_closing, LL.check_final_line))


def lint_answer(answer: dict) -> list:
    letter = {"paragraphs": answer.get("paragraphs", [])}
    return [f for check in FORM_CHECKS for f in check(letter)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", help="lint every folder from YYYY-MM-DD")
    ap.add_argument("--folder", type=Path, help="one per-application folder")
    args = ap.parse_args(argv)

    cfg = job_apply.load_config(settings.require_profile())
    if args.folder:
        folders = [args.folder]
    else:
        pattern = f"{args.date}_*" if args.date else "*"
        folders = sorted(p for p in cfg.applications_dir.glob(pattern)
                         if (p / "form_answers.json").is_file())

    if not folders:
        print("No form_answers.json found. Nothing to lint.")
        return LL.EXIT_NOTHING

    blocked = False
    for folder in folders:
        answers = json.loads((folder / "form_answers.json").read_text(encoding="utf-8"))
        for answer in answers:
            findings = lint_answer(answer)
            crit = [f for f in findings if f.severity == LL.CRITICAL]
            adv = [f for f in findings if f.severity == LL.ADVISORY]
            blocked = blocked or bool(crit)
            status = "BLOCKED" if crit else ("clean" if not adv else "clean, with notes")
            print(f"\n{folder.name} :: {answer.get('question', '?')}: {status}")
            for f in crit + adv:
                print(f)
    print()
    return LL.EXIT_BLOCKED if blocked else LL.EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
