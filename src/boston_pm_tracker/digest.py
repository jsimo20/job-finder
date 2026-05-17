"""Render the daily Markdown digest from the DB state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .taxonomy import STALE_DAYS

DEFAULT_DIGEST_DIR = Path(__file__).resolve().parents[2] / "digests"


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
    return (
        f"### [Score {row['total_score']}] {row['company_name']} — [{row['title']}]({row['url']})\n"
        f"- {loc} ({workplace}) · YOE {yoe} · {comp}\n"
        f"- Domain: {domain} · Stage: {stage}{extras}\n"
        f"- **[Apply →]({row['url']})**\n"
    )


def _new_today_sql(queue: str) -> str:
    # Exclude resume-fishing reqs: anything where the source-side posted_at
    # (or our first_seen_at if posted_at is missing) is older than STALE_DAYS.
    return f"""
        SELECT p.id, p.title, p.location, p.workplace_type, p.url,
               c.name AS company_name,
               e.yoe_required, e.comp_base_min, e.comp_base_max, e.comp_source,
               e.domain_tags, e.company_stage, e.stretch_reason,
               s.total_score
        FROM scores s
        JOIN postings p ON p.id = s.posting_id
        JOIN companies c ON c.id = p.company_id
        JOIN extractions e ON e.posting_id = p.id
        WHERE s.queue = '{queue}'
          AND p.closed_at IS NULL
          AND date(p.first_seen_at) = ?
          AND (julianday('now') - julianday(COALESCE(p.posted_at, p.first_seen_at))) <= {STALE_DAYS}
        ORDER BY s.total_score DESC
    """


def render(target_date: str | None = None, db_path: Path = db.DEFAULT_DB_PATH,
           digest_dir: Path = DEFAULT_DIGEST_DIR) -> Path:
    # first_seen_at is written as UTC, so the default target must also be UTC.
    target = target_date or datetime.now(timezone.utc).date().isoformat()
    with db.connect(db_path) as conn:
        main_rows = conn.execute(_new_today_sql("main"), (target,)).fetchall()
        stretch_rows = conn.execute(_new_today_sql("stretch"), (target,)).fetchall()
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
              (SELECT COUNT(*) FROM scores WHERE queue = 'stretch') AS stretch_total
            """
        ).fetchone()

    lines: list[str] = [f"# PM Jobs — {target}", ""]
    lines.append(f"## Main queue — new ({len(main_rows)})")
    lines.append("Sorted by score desc.\n")
    if main_rows:
        for r in main_rows:
            lines.append(_row_md(r))
    else:
        lines.append("_(none today)_\n")

    lines.append(f"## Stretch queue — new ({len(stretch_rows)})")
    lines.append("YOE ≥ 8; review only.\n")
    if stretch_rows:
        for r in stretch_rows:
            lines.append(_row_md(r))
    else:
        lines.append("_(none today)_\n")

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
        f"· Stretch total: {totals['stretch_total']}"
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
