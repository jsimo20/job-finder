#!/usr/bin/env python3
"""Collect every no_transition ADVISORY into a sheet a human can grade.

check_paragraph_chain is ADVISORY on purpose: its docstring says it "collects
signal until there is enough of it to justify blocking on." Nothing was reading
the collected signal, so the promotion decision had no data behind it. This
writes one row per hit, with the sentence before and the flagged opener side by
side, and an empty verdict column.

Fill `verdict` with `real` (the transition is genuinely missing) or `false`
(it reads fine and the regex missed the link). Precision is real / (real+false).
Promote the check to CRITICAL when precision is high enough that a block is
cheaper than a missed defect; keep it advisory while false positives would
stall unattended runs.

Usage:  python3 scripts/transition_sample.py [--out FILE]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_finder import letter_linter as LL  # noqa: E402


def sources(app_dir: Path):
    """Every (label, letter-dict) this repo can lint: letters and form answers."""
    for folder in sorted(p for p in app_dir.glob("*") if p.is_dir()):
        letter = folder / "cover_letter.json"
        if letter.is_file():
            yield folder.name, "cover letter", json.loads(letter.read_text(encoding="utf-8"))
        answers = folder / "form_answers.json"
        if answers.is_file():
            for item in json.loads(answers.read_text(encoding="utf-8")):
                yield folder.name, item.get("question", "form answer"), item


def rows(app_dir: Path):
    for name, kind, letter in sources(app_dir):
        paras = LL.paragraphs(letter)
        findings = LL.check_paragraph_chain(letter) + LL.check_known_new(letter)
        for finding in findings:
            i = int(finding.where.split()[-1])
            prev = LL.sentences(paras[i - 2])
            opener = LL.sentences(paras[i - 1])
            first = opener[0] if opener else ""
            yield {
                "check": finding.check,
                "application": name,
                "field": kind,
                "para": i,
                "sentence_before": prev[-1] if prev else "",
                "flagged_opener": first,
                # Diagnostic, not a verdict. A backref token past BACKREF_WINDOW
                # means the link is there and the window was too narrow to see
                # it; those are the likeliest false positives.
                "backref_past_window": "yes" if LL.BACKREF.search(first) else "no",
                # The retired "name the gap" rule ended paragraphs on a dead end,
                # which left the next one nothing to pick up. Hits marked here
                # should stop appearing now that §15 bans the disclaimer.
                "prev_para_named_a_gap":
                    "yes" if LL.check_gap_disclaimer({"paragraphs": [paras[i - 2]]}) else "no",
                "verdict": "",
            }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--applications-dir", type=Path)
    ap.add_argument("--out", type=Path, default=Path("transition_sample.csv"))
    args = ap.parse_args()

    root = args.applications_dir
    if root is None:
        from job_finder import job_apply, settings
        root = job_apply.load_config(settings.require_profile()).applications_dir

    data = list(rows(root))
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(data[0]) if data else
                           ["check", "application", "field", "para", "sentence_before",
                            "flagged_opener", "backref_past_window",
                            "prev_para_named_a_gap", "verdict"])
        w.writeheader()
        w.writerows(data)

    apps = len({r["application"] for r in data})
    kinds = {}
    for r in data:
        kinds[r["check"]] = kinds.get(r["check"], 0) + 1
    counts = ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))
    print(f"{len(data)} hits ({counts}) across {apps} applications -> {args.out}")
    print("Grade the verdict column: 'real' or 'false'. Precision decides the promotion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
