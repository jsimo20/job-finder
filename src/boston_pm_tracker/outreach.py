"""Outreach log: track people contacted on LinkedIn during the search.

Separate from the pipeline DB on purpose. `data/jobs.db` is rebuilt every run,
so it can't hold durable state; this log is an append-only JSONL file that the
pipeline never touches. Each line is one outreach record. Not every contact is
tied to a role application (James often reaches out for an internal referral),
so this is deliberately decoupled from the postings table and the digest.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

DEFAULT_OUTREACH_PATH = Path(__file__).resolve().parents[2] / "data" / "outreach.jsonl"

MESSAGE_TYPES = ("connection-request", "message", "hm-message")


def add_contact(
    name: str,
    company: str,
    *,
    role_context: str | None = None,
    message_type: str = "connection-request",
    notes: str | None = None,
    on_date: str | None = None,
    path: Path = DEFAULT_OUTREACH_PATH,
) -> dict[str, Any]:
    """Append one outreach record and return it.

    Args:
        name: The person contacted (required).
        company: Where they work (required) — the key we group and recall by.
        role_context: Role or reason for the outreach, if any (often none — the
            point is a warm referral, not a specific application).
        message_type: One of MESSAGE_TYPES.
        notes: Freeform context.
        on_date: ISO date; defaults to today.
        path: Log file; defaults to data/outreach.jsonl.
    """
    name = name.strip()
    company = company.strip()
    if not name or not company:
        raise ValueError("both name and company are required")
    if message_type not in MESSAGE_TYPES:
        raise ValueError(f"message_type must be one of {MESSAGE_TYPES}, got {message_type!r}")

    record = {
        "name": name,
        "company": company,
        "date": on_date or date.today().isoformat(),
        "role_context": role_context.strip() if role_context else None,
        "message_type": message_type,
        "notes": notes.strip() if notes else None,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_contacts(
    *,
    company: str | None = None,
    path: Path = DEFAULT_OUTREACH_PATH,
) -> list[dict[str, Any]]:
    """Return logged contacts, oldest first. Filter by company (case-insensitive substring)."""
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))

    if company:
        needle = company.strip().lower()
        records = [r for r in records if needle in r.get("company", "").lower()]

    records.sort(key=lambda r: r.get("date", ""))
    return records


def remove_contact(
    name: str,
    company: str,
    *,
    path: Path = DEFAULT_OUTREACH_PATH,
) -> list[dict[str, Any]]:
    """Remove every record matching name + company (both case-insensitive, exact).

    Returns the removed records (empty if none matched). Rewrites the file only
    when something is removed. Use `list_contacts` first to get the exact logged
    name (e.g. a truncated "Tina Spalten O'...").
    """
    if not path.exists():
        return []

    name_l = name.strip().lower()
    company_l = company.strip().lower()
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if record.get("name", "").lower() == name_l and record.get("company", "").lower() == company_l:
            removed.append(record)
        else:
            kept.append(record)

    if removed:
        with path.open("w", encoding="utf-8") as f:
            for record in kept:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return removed


def format_contacts(records: Iterable[dict[str, Any]]) -> str:
    """Render contacts grouped by company for terminal display."""
    records = list(records)
    if not records:
        return "No outreach logged yet."

    by_company: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_company.setdefault(r.get("company", "?"), []).append(r)

    lines: list[str] = []
    for company in sorted(by_company):
        lines.append(f"\n{company}")
        for r in sorted(by_company[company], key=lambda x: x.get("date", "")):
            bits = [f"  {r.get('date', '?')}  {r.get('name', '?')}"]
            if r.get("role_context"):
                bits.append(f"re: {r['role_context']}")
            bits.append(f"[{r.get('message_type', '?')}]")
            line = "  ".join(bits)
            if r.get("notes"):
                line += f"\n      note: {r['notes']}"
            lines.append(line)

    total = len(records)
    lines.append(f"\n{total} contact{'s' if total != 1 else ''} across {len(by_company)} company(ies).")
    return "\n".join(lines).lstrip("\n")
