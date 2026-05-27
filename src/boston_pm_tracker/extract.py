"""Stage 2: agentic extraction of structured signals from each surviving JD.

One Claude Haiku call per posting. System prompt is cached so per-call cost
is just the JD body.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import anthropic

from . import db
from .taxonomy import DOMAIN_DEFINITIONS, STAGE_DEFINITIONS

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

_DOMAIN_LIST = "\n".join(f"- {k}: {v}" for k, v in DOMAIN_DEFINITIONS.items())
_STAGE_LIST = "\n".join(f"- {k}: {v}" for k, v in STAGE_DEFINITIONS.items())

_BOM = chr(0xfeff)  # U+FEFF byte-order mark; escape avoids source-encoding ambiguity


SYSTEM_PROMPT = f"""You extract structured hiring signals from product manager job descriptions.

Return STRICT JSON only. No prose, no markdown fences. Schema:

{{
  "yoe_required": <int or null>,
  "yoe_confidence": "high" | "medium" | "low",
  "comp_base_min": <int USD or null>,
  "comp_base_max": <int USD or null>,
  "comp_source": "posted" | "inferred" | null,
  "domain": [<one or more domain tags>],
  "company_stage": <one stage tag or null>,
  "people_management": <true if JD requires directly managing PMs, else false>,
  "remote_us_ok": <true if role permits US remote work, else false>,
  "stretch_reason": <short string explaining why this is a stretch role, or null>
}}

Rules:
- yoe_required: minimum years of product management experience required. Null if not stated.
- comp: only set comp_source="posted" if the JD explicitly states a salary range. Otherwise null.
- domain: choose all that clearly apply from this list:
{_DOMAIN_LIST}
- company_stage: choose the single best fit from:
{_STAGE_LIST}
- If you cannot confidently determine a stage from the JD, use null.
- people_management: true only if the JD explicitly says the role manages other PMs/people.
- stretch_reason: set only if YOE >= 8 or other reason the role exceeds a typical Senior/Staff PM scope.

Output ONLY the JSON object."""


def _call_claude(client: anthropic.Anthropic, jd_text: str, title: str,
                 company_name: str) -> dict[str, Any]:
    jd_text = jd_text.replace(_BOM, "")
    title = title.replace(_BOM, "")
    user_msg = (
        f"Company: {company_name}\nTitle: {title}\n\nJob description:\n{jd_text[:12000]}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def run(db_path: Path = db.DEFAULT_DB_PATH, *, limit: int | None = None) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)
    stats = {"considered": 0, "extracted": 0, "skipped": 0, "errors": 0, "errors_detail": []}

    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.title, p.jd_text, c.name AS company_name
            FROM postings p
            JOIN companies c ON c.id = p.company_id
            LEFT JOIN extractions e ON e.posting_id = p.id
            WHERE p.hard_filter_verdict = 'keep'
              AND p.closed_at IS NULL
              AND e.posting_id IS NULL
            ORDER BY p.first_seen_at DESC
            """
        ).fetchall()
        if limit is not None:
            rows = rows[:limit]

        for row in rows:
            stats["considered"] += 1
            if not row["jd_text"]:
                stats["skipped"] += 1
                continue
            try:
                data = _call_claude(client, row["jd_text"], row["title"], row["company_name"])
            except Exception as e:
                logger.error("extract failed posting_id=%s err=%s", row["id"], e)
                stats["errors"] += 1
                stats["errors_detail"].append(f"posting_id={row['id']}: {e}")
                continue

            conn.execute(
                """
                INSERT OR REPLACE INTO extractions
                (posting_id, yoe_required, yoe_confidence, comp_base_min, comp_base_max,
                 comp_source, domain_tags, company_stage, people_management, remote_us_ok,
                 stretch_reason, extracted_at, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    data.get("yoe_required"),
                    data.get("yoe_confidence"),
                    data.get("comp_base_min"),
                    data.get("comp_base_max"),
                    data.get("comp_source"),
                    json.dumps(data.get("domain") or []),
                    data.get("company_stage"),
                    1 if data.get("people_management") else 0,
                    1 if data.get("remote_us_ok") else 0,
                    data.get("stretch_reason"),
                    db.now_iso(),
                    MODEL,
                ),
            )
            stats["extracted"] += 1
    return stats
