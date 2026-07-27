"""Render the daily Markdown digest from the DB state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import applied, db
from . import filter as filter_mod
from .taxonomy import STALE_DAYS

DEFAULT_DIGEST_DIR = Path(__file__).resolve().parents[2] / "digests"
CARRY_FORWARD_CAP = 20


def _fmt_comp(lo: int | None, hi: int | None, source: str | None) -> str:
    if not lo and not hi:
        return "Comp not posted"
    if source != "posted":
        return "Comp not posted"
    if lo and hi:
        return f"Comp ${lo // 1000}–{hi // 1000}K"
    if lo:
        return f"Comp ≥${lo // 1000}K"
    return f"Comp ≤${hi // 1000}K"


def _row_md(row) -> str:
    domain_tags = json.loads(row["domain_tags"] or "[]")
    yoe = row["yoe_required"] if row["yoe_required"] is not None else "?"
    loc = row["location"] or "?"
    workplace = row["workplace_type"] or "?"
    comp = _fmt_comp(row["comp_base_min"], row["comp_base_max"], row["comp_source"])
    stage = row["company_stage"] or "stage:?"
    domain = ", ".join(domain_tags) if domain_tags else "domain:?"
    extras = ""
    if row["stretch_reason"]:
        extras = f" · _stretch: {row['stretch_reason']}_"
    # Warn, never drop: days-per-week is often negotiable and postings are not
    # always accurate about it, so this is James's call to make.
    commute = filter_mod.commute_warning(
        row["location"],
        _row_get(row, "onsite_days_per_week"),
        remote_us_ok=bool(_row_get(row, "remote_us_ok")),
    )
    commute_line = f"- ⚠️ **Commute:** {commute}\n" if commute else ""
    return (
        f"### [Score {row['total_score']}] {row['company_name']} — [{row['title']}]({row['url']})\n"
        f"- {loc} ({workplace}) · YOE {yoe} · {comp}\n"
        f"- Domain: {domain} · Stage: {stage}{extras}\n"
        f"{commute_line}"
        f"- **[Apply →]({row['url']})**\n"
    )


def _row_get(row, key):
    """sqlite3.Row raises on a missing key rather than returning None, and a DB
    written before onsite_days_per_week existed will not have the column."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


_BASE_COLS = """
    p.id, p.external_id, p.title, p.location, p.workplace_type, p.url,
    c.name AS company_name,
    e.yoe_required, e.comp_base_min, e.comp_base_max, e.comp_source,
    e.domain_tags, e.company_stage, e.stretch_reason,
    e.remote_us_ok, e.onsite_days_per_week,
    s.total_score
"""

_BASE_JOIN_WHERE = f"""
    FROM scores s
    JOIN postings p ON p.id = s.posting_id
    JOIN companies c ON c.id = p.company_id
    JOIN extractions e ON e.posting_id = p.id
    WHERE p.closed_at IS NULL
      AND p.applied_at IS NULL
      AND p.dismissed_at IS NULL
      AND (julianday('now') - julianday(COALESCE(p.posted_at, p.first_seen_at))) <= {STALE_DAYS}
"""


def _new_today_sql(queue: str) -> str:
    # New = first seen on the digest's target date.
    return f"""
        SELECT {_BASE_COLS}
        {_BASE_JOIN_WHERE}
          AND s.queue = '{queue}'
          AND date(p.first_seen_at) = ?
        ORDER BY s.total_score DESC
    """


def _carry_forward_sql(queue: str) -> str:
    # Carry forward = seen earlier, still open, in-scope, not stale, neither
    # applied nor dismissed. Capped to keep the digest readable.
    return f"""
        SELECT {_BASE_COLS}
        {_BASE_JOIN_WHERE}
          AND s.queue = '{queue}'
          AND date(p.first_seen_at) < ?
        ORDER BY s.total_score DESC, p.first_seen_at DESC
        LIMIT {CARRY_FORWARD_CAP}
    """


def render(target_date: str | None = None, db_path: Path = db.DEFAULT_DB_PATH,
           digest_dir: Path = DEFAULT_DIGEST_DIR) -> Path:
    # first_seen_at is written as UTC, so the default target must also be UTC.
    target = target_date or datetime.now(timezone.utc).date().isoformat()
    # Durable suppression: the DB's applied_at is wiped every rebuild, so also
    # drop anything recorded in the committed applied-log (covers ad-hoc roles
    # the DB never saw). Keyed by external_id.
    applied_ids = applied.applied_external_ids()

    def _drop_applied(rows):
        return [r for r in rows if r["external_id"] not in applied_ids]

    with db.connect(db_path) as conn:
        main_rows = _drop_applied(conn.execute(_new_today_sql("main"), (target,)).fetchall())
        main_carry = _drop_applied(conn.execute(_carry_forward_sql("main"), (target,)).fetchall())
        stretch_rows = _drop_applied(conn.execute(_new_today_sql("stretch"), (target,)).fetchall())
        stretch_carry = _drop_applied(conn.execute(_carry_forward_sql("stretch"), (target,)).fetchall())
        closed_rows = conn.execute(
            """
            SELECT c.name AS company_name, p.title, p.url, p.last_seen_at
            FROM postings p
            JOIN companies c ON c.id = p.company_id
            WHERE date(p.closed_at) = ?
            ORDER BY c.name
            """,
            (target,),
        ).fetchall()
        totals = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM companies) AS companies,
              (SELECT COUNT(*) FROM postings WHERE closed_at IS NULL) AS open_postings,
              (SELECT COUNT(*) FROM postings WHERE hard_filter_verdict = 'keep' AND closed_at IS NULL) AS survived,
              (SELECT COUNT(*) FROM scores WHERE queue = 'main') AS main_total,
              (SELECT COUNT(*) FROM scores WHERE queue = 'stretch') AS stretch_total,
              (SELECT COUNT(*) FROM postings WHERE applied_at IS NOT NULL) AS applied_total,
              (SELECT COUNT(*) FROM postings p JOIN scores s ON s.posting_id = p.id
                 WHERE p.closed_at IS NULL AND p.applied_at IS NULL AND p.dismissed_at IS NULL
                 AND s.queue IN ('main','stretch')) AS pending_total
            """
        ).fetchone()

    def _section(header: str, blurb: str, rows) -> None:
        lines.append(f"## {header} ({len(rows)})")
        lines.append(blurb + "\n")
        if rows:
            for r in rows:
                lines.append(_row_md(r))
        else:
            lines.append("_(none)_\n")

    lines: list[str] = [f"# PM Jobs — {target}", ""]
    _section("Main queue — new", "Sorted by score desc.", main_rows)
    _section(
        "Main queue — carried forward",
        f"Pending from prior digests (top {CARRY_FORWARD_CAP} by score). "
        "Mark applied or dismissed via `python -m boston_pm_tracker.cli review`.",
        main_carry,
    )
    _section("Stretch queue — new", "YOE ≥ 8; review only.", stretch_rows)
    _section("Stretch queue — carried forward", "YOE ≥ 8; review only.", stretch_carry)

    lines.append(f"## Closed ({len(closed_rows)})")
    if closed_rows:
        for r in closed_rows:
            # Link the title even though the role is gone — the URL often still
            # resolves to an "archived" or "no longer accepting applications" page
            # that's useful for verification or to see the cached JD.
            lines.append(
                f"- **{r['company_name']}** — [{r['title']}]({r['url']}) · "
                f"last seen {r['last_seen_at']}"
            )
    else:
        lines.append("_(none today)_")
    lines.append("")

    lines.append("## Stats")
    lines.append(
        f"- Companies: {totals['companies']} · Open postings: {totals['open_postings']} "
        f"· Survived Stage 1: {totals['survived']} · Main total: {totals['main_total']} "
        f"· Stretch total: {totals['stretch_total']} "
        f"· Pending unapplied: {totals['pending_total']} "
        f"· Applied lifetime: {totals['applied_total']}"
    )

    body = "\n".join(lines).rstrip() + "\n"
    digest_dir.mkdir(parents=True, exist_ok=True)
    out_path = digest_dir / f"{target}.md"
    out_path.write_text(body, encoding="utf-8")

    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO daily_log (date, new_count, closed_count, changed_count, digest_md) VALUES (?, ?, ?, ?, ?)",
            (target, len(main_rows) + len(stretch_rows), len(closed_rows), 0, body),
        )

    return out_path
