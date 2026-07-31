"""Durable first-seen ledger: which postings any prior digest has shown.

data/jobs.db is rebuilt from scratch every CI run, so first_seen_at is always
"now" and can never distinguish a brand-new posting from one that has been
sitting in the digest for weeks — which is why every digest since the DB
went ephemeral labeled everything "new" and carried forward nothing. This
append-only JSONL is committed (like data/applied.jsonl) so the distinction
survives the rebuild.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_SEEN_PATH = Path(__file__).resolve().parents[2] / "data" / "seen.jsonl"


def load_seen(path: Path = DEFAULT_SEEN_PATH) -> dict[str, str]:
    """{external_id: first date a digest showed it}. Earliest date wins."""
    seen: dict[str, str] = {}
    if not path.exists():
        return seen
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        eid = record.get("external_id")
        first = record.get("first_seen", "")
        if eid and (eid not in seen or first < seen[eid]):
            seen[eid] = first
    return seen


def record_seen(external_ids: list[str], first_seen: str,
                path: Path = DEFAULT_SEEN_PATH) -> int:
    """Append ids not already in the ledger. Returns how many were added."""
    seen = load_seen(path)
    fresh = [eid for eid in external_ids if eid and eid not in seen]
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for eid in fresh:
                f.write(json.dumps({"external_id": eid, "first_seen": first_seen},
                                   ensure_ascii=False) + "\n")
    return len(fresh)
