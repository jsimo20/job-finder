"""Render the Markdown digest from the DB state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import applied, db, seen, state
from . import filter as filter_mod
from .taxonomy import STALE_DAYS, YOE_MAIN_QUEUE_MAX

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
    # always accurate about it, so this is the user's call to make.
    commute = filter_mod.commute_warning(
        row["location"],
        row["onsite_days_per_week"],
        remote_us_ok=bool(row["remote_us_ok"]),
    )
    commute_line = f"- ⚠️ **Commute:** {commute}\n" if commute else ""
    return (
        f"### [Score {row['total_score']}] {row['company_name']} — [{row['title']}]({row['url']})\n"
        f"- {loc} ({workplace}) · YOE {yoe} · {comp}\n"
        f"- Domain: {domain} · Stage: {stage}{extras}\n"
        f"{commute_line}"
        f"- **[Apply →]({row['url']})**\n"
    )


_BASE_COLS = """
    p.id, p.external_id, p.title, p.location, p.workplace_type, p.url, p.posted_at,
    c.name AS company_name,
    e.yoe_required, e.comp_base_min, e.comp_base_max, e.comp_source,
    e.domain_tags, e.company_stage, e.stretch_reason,
    e.remote_us_ok, e.onsite_days_per_week,
    s.total_score
"""

# Staleness is measured against the digest's TARGET date (the ? param), not
# render time — julianday('now') made a back-dated re-render return nothing.
_BASE_JOIN_WHERE = f"""
    FROM scores s
    JOIN postings p ON p.id = s.posting_id
    JOIN companies c ON c.id = p.company_id
    JOIN extractions e ON e.posting_id = p.id
    WHERE p.closed_at IS NULL
      AND p.applied_at IS NULL
      AND p.dismissed_at IS NULL
      AND (julianday(?) - julianday(COALESCE(p.posted_at, p.first_seen_at))) <= {STALE_DAYS}
"""


def _pending_sql(queue: str) -> str:
    # One query per queue; the new-vs-carried split happens in Python against
    # the seen-ledger in state.db. The working DB is rebuilt every run, so
    # first_seen_at is always "now" and cannot make that distinction — before
    # the ledger existed, every digest labeled all rows "new" and carried
    # forward zero because of it.
    return f"""
        SELECT {_BASE_COLS}
        {_BASE_JOIN_WHERE}
          AND s.queue = '{queue}'
        ORDER BY s.total_score DESC
    """


def drop_stale_for_company(rows, overrides: dict[str, int], target: str):
    """Apply per-company staleness overrides tighter than the global STALE_DAYS.

    Fails closed: a posting from an override company with no posted_at is
    dropped rather than kept. first_seen_at is always "now" (the working DB is
    rebuilt every run), so it cannot stand in for a real post date here, and
    keeping undated rows would silently defeat the whole filter.
    """
    if not overrides:
        return list(rows)
    target_day = datetime.fromisoformat(target).date()
    kept = []
    for r in rows:
        limit = overrides.get((r["company_name"] or "").strip().lower())
        if limit is None:
            kept.append(r)
            continue
        posted = r["posted_at"]
        if not posted:
            continue
        try:
            posted_day = datetime.fromisoformat(str(posted).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if (target_day - posted_day).days <= limit:
            kept.append(r)
    return kept


def split_new_carry(rows, seen: dict[str, str], target: str):
    """(new, carried) by the seen-ledger. A row first seen on the target date
    itself counts as new, so re-rendering the same day is stable."""
    new_rows = [r for r in rows
                if seen.get(r["external_id"], target) == target]
    carry_rows = [r for r in rows
                  if seen.get(r["external_id"], target) != target][:CARRY_FORWARD_CAP]
    return new_rows, carry_rows


def render(target_date: str | None = None, db_path: Path = db.DEFAULT_DB_PATH,
           digest_dir: Path = DEFAULT_DIGEST_DIR,
           state_db: Path = state.DEFAULT_STATE_DB) -> Path:
    # first_seen_at is written as UTC, so the default target must also be UTC.
    target = target_date or datetime.now(timezone.utc).date().isoformat()
    # Durable suppression: the DB's applied_at is wiped every rebuild, so also
    # drop anything recorded in the committed applied-log (covers ad-hoc roles
    # the DB never saw). Keyed by external_id, plus company+title so a
    # reposted req (fresh external_id, same role) stays suppressed.
    applied_ids = applied.applied_external_ids(db_path=state_db)
    applied_pairs = applied.applied_company_titles(db_path=state_db)

    def _drop_applied(rows):
        return [
            r for r in rows
            if r["external_id"] not in applied_ids
            and ((r["company_name"] or "").strip().lower(),
                 applied._norm_title(r["title"])) not in applied_pairs
        ]

    seen_map = seen.load_seen(state_db)
    overrides = state.max_age_overrides(state_db)

    with db.connect(db_path) as conn:
        main_pending = drop_stale_for_company(
            _drop_applied(conn.execute(_pending_sql("main"), (target,)).fetchall()),
            overrides, target)
        stretch_pending = drop_stale_for_company(
            _drop_applied(conn.execute(_pending_sql("stretch"), (target,)).fetchall()),
            overrides, target)
        main_rows, main_carry = split_new_carry(main_pending, seen_map, target)
        stretch_rows, stretch_carry = split_new_carry(stretch_pending, seen_map, target)
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

    stretch_blurb = f"YOE above {YOE_MAIN_QUEUE_MAX}; review only."
    lines: list[str] = [f"# Job Digest — {target}", ""]
    _section("Main queue — new", "Sorted by score desc.", main_rows)
    _section(
        "Main queue — carried forward",
        f"Pending from prior digests (top {CARRY_FORWARD_CAP} by score). "
        "Mark applied or dismissed via `job-finder review`.",
        main_carry,
    )
    _section("Stretch queue — new", stretch_blurb, stretch_rows)
    _section("Stretch queue — carried forward", stretch_blurb, stretch_carry)

    # Companies the pipeline can't poll (no supported ATS API) still deserve a
    # weekly nudge — otherwise they exist only in whoever's memory added them.
    manual_companies = [c for c in state.list_companies(state_db)
                        if c["ats_provider"] == "manual"]
    lines.append(f"## Manual check ({len(manual_companies)})")
    lines.append("Tracked companies with no pollable board — open each careers "
                 "page by hand.\n")
    if manual_companies:
        for c in manual_companies:
            tags = ", ".join(c["sector_tags"]) if c["sector_tags"] else ""
            tag_str = f" · {tags}" if tags else ""
            lines.append(f"- **[{c['name']}]({c['careers_url']})**{tag_str}")
        lines.append("")
    else:
        lines.append("_(none tracked)_\n")

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

    # Every pending row this digest showed enters the ledger, so the next run
    # can tell new from carried. Idempotent: already-seen ids are skipped.
    seen.record_seen(
        [r["external_id"] for r in main_pending + stretch_pending],
        target, state_db,
    )
    # The durable archive lives in state.db; the md file above is the working
    # copy for humans and the digest-triager.
    state.save_digest(target, body, state_db)

    return out_path
