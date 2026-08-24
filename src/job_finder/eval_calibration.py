"""Layer-1 scoring calibration eval: does the score predict what gets applied to?

Read-only over data/state.db, zero LLM tokens. The labels are free: every
application the user records is a positive, and every scored role that reached
a digest and was never applied to is a negative. Design sibling of
fill_grader.py; the shared shape is documented in
.claude/context/form-fill-evals.md.

The digest archive is the only durable record of what a role scored --
data/jobs.db is rebuilt by every pipeline run, so scores, extractions and
filter verdicts do not survive the week. Everything here is reconstructed by
parsing the archived digest bodies.

Four readouts:

- Coverage    -- how many applications came through the pipeline at all.
  Ad-hoc and backfilled ones cannot grade the scorer; they are reported
  separately because a low share is itself a finding about where sourcing
  really happens.
- Precision@k -- share of applications that sat in the top k of the digest
  that triggered them, against the share chance alone would produce.
- Score bands -- apply rate per score band. Monotonically increasing is the
  whole claim the scorer makes; flat means the weights are noise.
- Signal lift -- apply rate for roles carrying each domain tag, stage or comp
  signal, over baseline. The actionable one: a signal with high lift and a low
  weight in config/pipeline.toml is an underweighted signal.

Grade is the median percentile of applied roles within their trigger digest:
A >= 80%, B >= 65%, C >= 50%, D >= 35%, F below.

Usage:
    python -m job_finder.eval_calibration
    python -m job_finder.eval_calibration --min-support 3 --json
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

from . import state

# Digest markdown separates fields with en/em dashes and a middle dot. Spell
# them as escapes: a literal here has been corrupted before by a round trip
# through a non-UTF-8 editor (see the BOM gotcha in CLAUDE.md).
_DASH = "[—–-]"
_MIDDOT = "·"

SECTION_RE = re.compile(
    rf"^##\s+(Main|Stretch)\s+queue\s*{_DASH}\s*(new|carried forward)", re.I)
OTHER_SECTION_RE = re.compile(r"^##\s+(Closed|Stats|Manual check)", re.I)
ENTRY_RE = re.compile(
    rf"^###\s+\[Score\s+(-?\d+)\]\s+(.+?)\s+{_DASH}\s+\[(.+?)\]\((\S+?)\)\s*$")
# Stage slugs carry digits (mega_corp_10k), so the class cannot be letters only.
STAGE_RE = re.compile(r"Stage:\s*([a-z0-9_]+)")
COMP_LO_RE = re.compile(r"\$(\d+)")
# digest._fmt_comp renders a bare maximum as "Comp <=$XK", which means the
# minimum was null. Reading that X as a floor would invent a comp score.
COMP_MAX_ONLY = "≤"

GRADE_BANDS = [(0.80, "A"), (0.65, "B"), (0.50, "C"), (0.35, "D"), (0.0, "F")]
SCORE_BANDS = [(17, None), (13, 16), (9, 12), (5, 8), (None, 4)]
PRECISION_KS = (1, 3, 5, 10)

# Below this an id substring-matches unrelated URLs by accident, which would
# silently inflate every metric in this module.
MIN_ID_LEN = 4


def _band_label(lo: int | None, hi: int | None) -> str:
    if lo is None:
        return f"<={hi}"
    if hi is None:
        return f"{lo}+"
    return f"{lo}-{hi}"


def parse_digest(body: str) -> list[dict[str, Any]]:
    """Extract the pending role entries from one rendered digest, in reading order.

    Closed, Stats and Manual check sections carry no score, so they are not part
    of the ranking being graded and are skipped.
    """
    entries: list[dict[str, Any]] = []
    section: tuple[str, str] | None = None
    current: dict[str, Any] | None = None

    for line in body.splitlines():
        sec = SECTION_RE.match(line)
        if sec:
            section = (sec.group(1).lower(), sec.group(2).lower())
            current = None
            continue
        if OTHER_SECTION_RE.match(line):
            section = None
            current = None
            continue
        if section is None:
            continue

        entry = ENTRY_RE.match(line)
        if entry:
            current = {
                "score": int(entry.group(1)),
                "company": entry.group(2).strip(),
                "title": entry.group(3).strip(),
                "url": entry.group(4),
                "queue": section[0],
                "freshness": section[1],
                "rank": len(entries) + 1,
                "domain_tags": [],
                "stage": None,
                "comp_posted": False,
                "comp_min": None,
            }
            entries.append(current)
            continue

        if current is None:
            continue
        if line.startswith("- Domain:"):
            head = line[len("- Domain:"):].split(_MIDDOT)[0]
            current["domain_tags"] = [
                tag.strip() for tag in head.split(",")
                if tag.strip() and tag.strip() != "domain:?"
            ]
            stage = STAGE_RE.search(line)
            if stage:
                current["stage"] = stage.group(1)
        elif "YOE" in line and "Comp" in line:
            current["comp_posted"] = "Comp not posted" not in line
            if current["comp_posted"] and COMP_MAX_ONLY not in line:
                floor = COMP_LO_RE.search(line)
                current["comp_min"] = int(floor.group(1)) * 1000 if floor else None
    return entries


def reconstruct_score(entry: dict[str, Any]) -> int:
    """Recompute an archived entry's score under the weights configured today."""
    from .score import comp_score, domain_score, stage_score

    return (domain_score(entry["domain_tags"])
            + stage_score(entry["stage"])
            + comp_score(entry["comp_min"], "posted" if entry["comp_posted"] else None))


def reconstruction_check(digests: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Detect archived scores that today's weights no longer reproduce.

    The scorer is additive, so an archived score should recompute exactly. When
    it does not, config/pipeline.toml was reweighted partway through the archive
    and the digests on either side of that edit are not directly comparable --
    which silently contaminates every rank and lift in this module. Nothing here
    can repair it, so it is surfaced rather than corrected.
    """
    exact = 0
    drifted: list[dict[str, Any]] = []
    for date, entries in digests.items():
        for entry in entries:
            residual = reconstruct_score(entry) - entry["score"]
            if residual:
                drifted.append({"date": date, "residual": residual,
                                "tags": entry["domain_tags"], "stage": entry["stage"]})
            else:
                exact += 1

    total = exact + len(drifted)
    suspects: dict[str, int] = {}
    for row in drifted:
        for tag in row["tags"]:
            suspects[f"domain:{tag}"] = suspects.get(f"domain:{tag}", 0) + 1
        if row["stage"]:
            suspects[f"stage:{row['stage']}"] = suspects.get(f"stage:{row['stage']}", 0) + 1

    return {
        "exact": exact,
        "total": total,
        "rate": exact / total if total else 1.0,
        "drifted": len(drifted),
        "last_drift_date": max((r["date"] for r in drifted), default=None),
        "suspects": sorted(suspects.items(), key=lambda kv: -kv[1])[:5],
    }


def load_digests(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    return {
        date: parse_digest(body)
        for date, body in conn.execute("SELECT date, body FROM digests ORDER BY date")
    }


def load_applied(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT external_id, company, title, url, applied_at, source FROM applied")
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, row)) for row in cur]


def _matches(external_id: str | None, url: str | None, entry_url: str) -> bool:
    if external_id and len(external_id) >= MIN_ID_LEN and external_id in entry_url:
        return True
    return bool(url) and url.rstrip("/") == entry_url.rstrip("/")


def link_applications(
    digests: dict[str, list[dict[str, Any]]],
    applications: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pair each application with the digest that plausibly triggered it.

    That is the most recent digest published on or before the application date
    that still listed the role. A role applied to before it ever appeared (a
    backfilled date, or an ad-hoc find the pipeline only picked up later) falls
    back to the earliest digest listing it, flagged so callers can discount it.
    """
    linked: list[dict[str, Any]] = []
    unlinked: list[dict[str, Any]] = []

    for app in applications:
        hits = [
            (date, entry)
            for date, entries in digests.items()
            for entry in entries
            if _matches(app.get("external_id"), app.get("url"), entry["url"])
        ]
        if not hits:
            unlinked.append(app)
            continue

        applied_at = (app.get("applied_at") or "")[:10]
        prior = [hit for hit in hits if hit[0] <= applied_at] if applied_at else []
        date, entry = prior[-1] if prior else hits[0]
        scores = [e["score"] for e in digests[date]]
        below = sum(1 for s in scores if s < entry["score"])
        linked.append({
            **app,
            "digest_date": date,
            "digest_size": len(scores),
            "rank": entry["rank"],
            "score": entry["score"],
            "queue": entry["queue"],
            "percentile": below / (len(scores) - 1) if len(scores) > 1 else 1.0,
            "date_fallback": not prior,
        })
    return linked, unlinked


def build_pool(
    digests: dict[str, list[dict[str, Any]]],
    applications: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Every role that ever reached a digest, labelled applied or not.

    A role is represented by its most recent appearance: carried-forward entries
    are re-scored on every run, so the latest score is the live one.
    """
    latest: dict[str, dict[str, Any]] = {}
    for date, entries in digests.items():
        for entry in entries:
            latest[entry["url"]] = {**entry, "digest_date": date}

    apps = list(applications)
    for url, role in latest.items():
        role["applied"] = any(
            _matches(a.get("external_id"), a.get("url"), url) for a in apps)
    return list(latest.values())


def precision_at_k(
    linked: list[dict[str, Any]],
    ks: Iterable[int] = PRECISION_KS,
) -> list[dict[str, Any]]:
    """Observed top-k hit rate against the rate chance alone would produce.

    The chance baseline is computed per digest (k/n for that digest's size)
    rather than once globally, because digest sizes vary by a factor of ten.
    """
    out = []
    for k in ks:
        hits = sum(1 for a in linked if a["rank"] <= k)
        expected = sum(min(k, a["digest_size"]) / a["digest_size"] for a in linked)
        out.append({
            "k": k,
            "hits": hits,
            "n": len(linked),
            "rate": hits / len(linked) if linked else 0.0,
            "chance": expected / len(linked) if linked else 0.0,
            "lift": hits / expected if expected else 0.0,
        })
    return out


def score_bands(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for lo, hi in SCORE_BANDS:
        members = [
            r for r in pool
            if (lo is None or r["score"] >= lo) and (hi is None or r["score"] <= hi)
        ]
        applied = sum(1 for r in members if r["applied"])
        out.append({
            "band": _band_label(lo, hi),
            "n": len(members),
            "applied": applied,
            "rate": applied / len(members) if members else 0.0,
        })
    return out


def signal_lift(pool: list[dict[str, Any]], min_support: int = 5) -> list[dict[str, Any]]:
    """Apply rate per extracted signal, over the pool baseline."""
    signals: dict[str, list[dict[str, Any]]] = {}
    for role in pool:
        for tag in role["domain_tags"]:
            signals.setdefault(f"domain:{tag}", []).append(role)
        if role["stage"]:
            signals.setdefault(f"stage:{role['stage']}", []).append(role)
        signals.setdefault(
            "comp:posted" if role["comp_posted"] else "comp:not_posted", []).append(role)
        signals.setdefault(f"queue:{role['queue']}", []).append(role)

    total_applied = sum(1 for r in pool if r["applied"])
    baseline = total_applied / len(pool) if pool else 0.0

    out = []
    for name, members in signals.items():
        if len(members) < min_support:
            continue
        applied = sum(1 for r in members if r["applied"])
        rate = applied / len(members)
        out.append({
            "signal": name,
            "n": len(members),
            "applied": applied,
            "rate": rate,
            "lift": rate / baseline if baseline else 0.0,
        })
    return sorted(out, key=lambda s: s["lift"], reverse=True)


def evaluate(
    db_path: Path = state.DEFAULT_STATE_DB,
    min_support: int = 5,
) -> dict[str, Any]:
    with state.connect(db_path) as conn:
        digests = load_digests(conn)
        applications = load_applied(conn)

    linked, unlinked = link_applications(digests, applications)
    pool = build_pool(digests, applications)
    percentiles = [a["percentile"] for a in linked]
    median_pct = statistics.median(percentiles) if percentiles else 0.0

    return {
        "digests": len(digests),
        "digest_entries": sum(len(e) for e in digests.values()),
        "pool": len(pool),
        "applications": len(applications),
        "linked": linked,
        "unlinked": unlinked,
        "median_percentile": median_pct,
        "median_rank": statistics.median([a["rank"] for a in linked]) if linked else 0,
        "precision": precision_at_k(linked),
        "bands": score_bands(pool),
        "signals": signal_lift(pool, min_support),
        "reconstruction": reconstruction_check(digests),
        "grade": next(g for floor, g in GRADE_BANDS if median_pct >= floor),
    }


def print_report(result: dict[str, Any], verbose: bool = True) -> None:
    linked = result["linked"]
    unlinked = result["unlinked"]
    total = result["applications"]

    print(f"\n{'=' * 70}")
    print(f"SCORING CALIBRATION  -  grade {result['grade']}  "
          f"(median applied role sat at the {result['median_percentile']:.0%} "
          f"percentile of its digest)")
    print(f"  {result['digests']} digests, {result['digest_entries']} scored entries, "
          f"{result['pool']} unique roles, {total} applications")
    if total:
        print(f"  {len(linked)}/{total} applications traceable to a digest "
              f"({len(linked) / total:.0%})")

    recon = result["reconstruction"]
    if recon["drifted"]:
        print(f"\n  ! WEIGHTS CHANGED MID-ARCHIVE: {recon['drifted']}/{recon['total']} "
              f"archived entries ({1 - recon['rate']:.0%}) do not reproduce under "
              f"today's config/pipeline.toml, most recently {recon['last_drift_date']}.")
        print("    Digests either side of that edit are not directly comparable, so "
              "the ranks and lifts below are contaminated to that degree.")
        if recon["suspects"]:
            print("    Most affected: " + ", ".join(
                f"{name} ({n})" for name, n in recon["suspects"]))
        print("    A signal whose weight was raised in response to past behaviour "
              "will also show high lift here for that reason alone.")

    if not linked:
        print("\n  Nothing to grade: no application matched an archived digest.")
        return

    fallbacks = sum(1 for a in linked if a["date_fallback"])
    if fallbacks:
        print(f"  {fallbacks} matched only a digest published after the application "
              f"date (backfilled); their rank is indicative only")

    print(f"\n  PRECISION@K   median rank {result['median_rank']:.0f} "
          f"of {statistics.median([a['digest_size'] for a in linked]):.0f}")
    for p in result["precision"]:
        verdict = "beats chance" if p["lift"] > 1.15 else "no better than chance"
        print(f"    top {p['k']:>2}: {p['hits']:>2}/{p['n']} = {p['rate']:>5.0%}  "
              f"(chance {p['chance']:>5.0%}, lift {p['lift']:>4.2f}x)  {verdict}")

    print("\n  APPLY RATE BY SCORE BAND   (monotonic = the scorer works)")
    for b in result["bands"]:
        if not b["n"]:
            continue
        print(f"    {b['band']:>6}: {b['applied']:>3}/{b['n']:<4} = {b['rate']:>5.1%} "
              f"{'#' * round(b['rate'] * 40)}")

    if verbose and result["signals"]:
        print("\n  SIGNAL LIFT   (apply rate vs baseline; high lift + low weight in "
              "pipeline.toml = underweighted)")
        for s in result["signals"]:
            print(f"    {s['lift']:>5.2f}x  {s['signal']:<32} "
                  f"{s['applied']:>3}/{s['n']:<4} = {s['rate']:>5.1%}")

    if verbose and unlinked:
        print(f"\n  OUTSIDE THE PIPELINE   ({len(unlinked)} applications never matched "
              f"a digest entry)")
        by_source: dict[str, int] = {}
        for a in unlinked:
            key = (a.get("source") or "unrecorded")[:44]
            by_source[key] = by_source.get(key, 0) + 1
        for source, count in sorted(by_source.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>3}  {source}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=state.DEFAULT_STATE_DB,
                    help="path to state.db")
    ap.add_argument("--min-support", type=int, default=5,
                    help="minimum roles carrying a signal before its lift is reported")
    ap.add_argument("--quiet", action="store_true", help="headline metrics only")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="emit the raw result as JSON")
    args = ap.parse_args()

    if not args.db.exists():
        ap.error(f"no state database at {args.db}")

    result = evaluate(args.db, args.min_support)
    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print_report(result, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
