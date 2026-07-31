"""Stage 4: deterministic scorer. Combines domain, stage, comp signals into a single score
and routes each extracted posting to main / stretch / discard queues via filter.stage3.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import db
from .filter import stage3
from .taxonomy import COMP_SCORE_THRESHOLDS, DOMAIN_WEIGHTS, STAGE_WEIGHTS


def domain_score(domain_tags: list[str]) -> int:
    return sum(DOMAIN_WEIGHTS.get(tag, 0) for tag in domain_tags)


def stage_score(stage: str | None) -> int:
    if not stage:
        return 0
    return STAGE_WEIGHTS.get(stage, 0)


def comp_score(comp_base_min: int | None, comp_source: str | None) -> int:
    if comp_base_min is None or comp_source != "posted":
        return 0
    return sum(1 for threshold in COMP_SCORE_THRESHOLDS if comp_base_min >= threshold)


def run(db_path: Path = db.DEFAULT_DB_PATH) -> dict:
    stats = {"scored": 0, "main": 0, "stretch": 0, "discard": 0}
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT e.posting_id, e.yoe_required, e.comp_base_min, e.comp_base_max,
                   e.comp_source, e.domain_tags, e.company_stage
            FROM extractions e
            JOIN postings p ON p.id = e.posting_id
            WHERE p.closed_at IS NULL
            """
        ).fetchall()

        for r in rows:
            tags = json.loads(r["domain_tags"] or "[]")
            ds = domain_score(tags)
            ss = stage_score(r["company_stage"])
            cs = comp_score(r["comp_base_min"], r["comp_source"])
            total = ds + ss + cs

            verdict = stage3(
                yoe_required=r["yoe_required"],
                comp_base_min=r["comp_base_min"],
                comp_base_max=r["comp_base_max"],
                comp_source=r["comp_source"],
            )
            queue = verdict.queue
            stats[queue] += 1
            stats["scored"] += 1

            conn.execute(
                """
                INSERT OR REPLACE INTO scores
                (posting_id, domain_score, stage_score, comp_score, total_score, queue, scored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (r["posting_id"], ds, ss, cs, total, queue, db.now_iso()),
            )
    return stats
