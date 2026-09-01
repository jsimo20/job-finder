"""Repeat an eval and report the spread, so a change can be told from noise.

Every eval in this repo graded each case exactly once. That is one sample from a
stochastic process: 14/14 and 12/14 on an unchanged prompt are both ordinary
outcomes, so a single pass cannot tell a real regression from variance, and the
second time you use an eval is when that starts to matter.

Shared by eval_factcheck, eval_generation and eval_skill_terms rather than
reimplemented in each, so they agree on what a spread means.
"""
from __future__ import annotations

import statistics
from typing import Any, Callable


def repeat(run: Callable[[], dict[str, Any]], times: int, *,
           score_key: str = "score",
           case_key: str = "results") -> list[dict[str, Any]]:
    runs = []
    for i in range(max(1, times)):
        if times > 1:
            print(f"\nrun {i + 1} of {times}")
        runs.append(run())
    return runs


def format_spread(runs: list[dict[str, Any]], *, score_key: str = "score",
                  case_key: str = "results") -> str:
    """The spread, and the cases that flipped between runs."""
    scores = [r[score_key] for r in runs if score_key in r]
    if not scores:
        return ""
    lines = [f"\n{len(runs)} runs",
             f"  scores : {', '.join(f'{s:.2f}' for s in scores)}",
             f"  median : {statistics.median(scores):.2f}"]
    if len(scores) > 1:
        lines.append(f"  spread : {max(scores) - min(scores):.2f}"
                     f"  (min {min(scores):.2f}, max {max(scores):.2f})")
        lines.append(f"  stdev  : {statistics.stdev(scores):.3f}")
        lines.append("")
        lines.append("  A change smaller than the spread is not a result. Re-run "
                     "before acting on it.")

    passed, failed = set(), set()
    for run in runs:
        for r in run.get(case_key, []):
            (passed if r.get("passed") else failed).add(r.get("id"))
    flaky = sorted(passed & failed)
    if flaky:
        lines.append(f"  unstable cases: {', '.join(flaky)}")
        lines.append("  These flipped between runs; they are noise, not signal, "
                     "until pinned.")
    return "\n".join(lines)
