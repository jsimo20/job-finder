"""One-shot migration: legacy committed files -> data/state.db.

Run once after upgrading to the local-first layout:

    python -m job_finder.migrate_state

Tolerant of missing sources (a fresh clone has none). Never deletes the
legacy files; remove them yourself once the counts look right.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import state

REPO_ROOT = Path(__file__).resolve().parents[2]

LEGACY_COMPANIES = REPO_ROOT / "data" / "companies.json"
LEGACY_NO_AUTO = REPO_ROOT / "data" / "no_auto_apply.json"
LEGACY_APPLIED = REPO_ROOT / "data" / "applied.jsonl"
LEGACY_SEEN = REPO_ROOT / "data" / "seen.jsonl"
LEGACY_DIGESTS = REPO_ROOT / "digests"


def main() -> int:
    db = state.DEFAULT_STATE_DB
    report: list[str] = []

    if LEGACY_COMPANIES.exists():
        report.append(f"companies: {state.import_companies(LEGACY_COMPANIES, db)} imported")

    if LEGACY_NO_AUTO.exists():
        data = json.loads(LEGACY_NO_AUTO.read_text(encoding="utf-8"))
        rows = data.get("companies", []) if isinstance(data, dict) else data
        for r in rows:
            state.add_no_auto(r["name"], r.get("reason", ""), r.get("added", ""), db)
        report.append(f"no_auto_apply: {len(rows)} imported")

    if LEGACY_APPLIED.exists():
        n = 0
        with state.connect(db) as conn:
            for line in LEGACY_APPLIED.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                cur = conn.execute(
                    "INSERT OR IGNORE INTO applied (external_id, company, title, url, applied_at, source) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (r.get("external_id"), r.get("company"), r.get("title"),
                     r.get("url"), r.get("applied_at"), r.get("source")))
                n += cur.rowcount
        report.append(f"applied: {n} imported")

    if LEGACY_SEEN.exists():
        n = 0
        with state.connect(db) as conn:
            for line in LEGACY_SEEN.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                cur = conn.execute(
                    "INSERT OR IGNORE INTO seen (external_id, first_seen) VALUES (?, ?)",
                    (r.get("external_id"), r.get("first_seen")))
                n += cur.rowcount
        report.append(f"seen: {n} imported")

    if LEGACY_DIGESTS.is_dir():
        n = 0
        for md in sorted(LEGACY_DIGESTS.glob("????-??-??.md")):
            state.save_digest(md.stem, md.read_text(encoding="utf-8"), db)
            n += 1
        report.append(f"digests: {n} archived")

    if not report:
        print(f"nothing to migrate; state db at {db}")
        return 0
    print(f"migrated into {db}:")
    for line in report:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
