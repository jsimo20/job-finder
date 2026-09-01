"""Interactive picker over pending in-scope postings.

Pending = open, kept by Stage 1, scored to main/stretch, not stale, not yet
marked applied/dismissed. Sorted by score desc (highest-signal first).
"""
from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from . import applied, db
from .taxonomy import STALE_DAYS

PENDING_SQL = f"""
    SELECT p.id, p.external_id, p.title, p.location, p.workplace_type, p.url,
           c.name AS company_name,
           e.yoe_required, e.comp_base_min, e.comp_base_max, e.comp_source,
           e.domain_tags, e.company_stage,
           s.total_score, s.queue,
           CAST(julianday('now') - julianday(COALESCE(p.posted_at, p.first_seen_at)) AS INTEGER) AS age_days
    FROM scores s
    JOIN postings p ON p.id = s.posting_id
    JOIN companies c ON c.id = p.company_id
    JOIN extractions e ON e.posting_id = p.id
    WHERE p.closed_at IS NULL
      -- p.applied_at is jobs.db's own column and it is rebuilt to NULL every
      -- run, so it only catches applies made since the last one. The durable
      -- answer is applied.drop_applied(), applied to these rows by the caller.
      AND p.applied_at IS NULL
      AND p.dismissed_at IS NULL
      AND s.queue IN ('main','stretch')
      AND (julianday('now') - julianday(COALESCE(p.posted_at, p.first_seen_at))) <= {STALE_DAYS}
    ORDER BY s.total_score DESC, age_days ASC
"""

HELP = "  [a]pplied  [d]ismiss  [s]kip  [o]pen URL  [b]ack  [q]uit"


def _render(idx: int, total: int, row) -> None:
    tags = ", ".join(json.loads(row["domain_tags"] or "[]")) or "?"
    comp = "not posted"
    if row["comp_source"] == "posted" and row["comp_base_min"]:
        lo = row["comp_base_min"] // 1000
        hi = (row["comp_base_max"] or row["comp_base_min"]) // 1000
        comp = f"${lo}-{hi}K"
    print()
    print("=" * 78)
    print(f"  [{idx + 1}/{total}]  Score {row['total_score']}  Queue: {row['queue']}")
    print("=" * 78)
    print(f"  {row['company_name']} — {row['title']}")
    print(f"  Location: {row['location']} ({row['workplace_type'] or '-'})")
    print(f"  YOE: {row['yoe_required'] or '?'}  Comp: {comp}  Age: {row['age_days']}d")
    print(f"  Domain: {tags}  Stage: {row['company_stage'] or '?'}")
    print(f"  URL: {row['url']}")
    print()


def run(db_path: Path = db.DEFAULT_DB_PATH) -> dict:
    stats = {"applied": 0, "dismissed": 0, "skipped": 0}
    with db.connect(db_path) as conn:
        rows = applied.drop_applied(conn.execute(PENDING_SQL).fetchall())
    if not rows:
        print("No pending roles. Run `job-finder run` first or wait for the next digest.")
        return stats

    print(f"\n{len(rows)} pending role(s). {HELP}\n")
    i = 0
    while i < len(rows):
        row = rows[i]
        _render(i, len(rows), row)
        choice = input("> ").strip().lower()
        if not choice:
            continue
        action = choice[0]
        if action == "a":
            with db.connect(db_path) as conn:
                db.mark_applied(conn, external_id=row["external_id"])
            stats["applied"] += 1
            print("  ✓ marked applied")
            i += 1
        elif action == "d":
            with db.connect(db_path) as conn:
                db.mark_dismissed(conn, external_id=row["external_id"])
            stats["dismissed"] += 1
            print("  ✓ dismissed")
            i += 1
        elif action == "s":
            stats["skipped"] += 1
            i += 1
        elif action == "o":
            webbrowser.open(row["url"])
            print("  ↗ opened in browser; still pending — re-press a/d/s")
        elif action == "b":
            if i > 0:
                i -= 1
        elif action == "q":
            print("\n  quit — remaining items stay pending.")
            break
        else:
            print(f"  unknown: {choice!r}. {HELP}")

    print(f"\nDone. {stats}")
    return stats
