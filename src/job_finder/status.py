"""One answer to "did Monday work?", across both halves of the system.

The pipeline runs as a Windows Scheduled Task and reports into
data/logs/scheduled-run.log. The apply batch runs as a Claude session and
reports into a chat transcript. Nothing joined them, so checking on the system
meant grepping a log, opening Task Scheduler, and remembering what the batch
said. That is the "two separate processes" feeling; this is the seam.

Everything here is read-only and derived from artifacts the system already
writes. No network, no tokens.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import applied, state

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_LOG = REPO_ROOT / "data" / "logs" / "scheduled-run.log"
PLUGIN_MANIFEST = REPO_ROOT / "cowork-plugin" / ".claude-plugin" / "plugin.json"
APPLICATIONS_DIR = REPO_ROOT / "profile" / "applications"
TASK_NAME = "job-finder weekly"

_RUN_START = re.compile(r"=+ scheduled run started (\S+) =+")
_RUN_END = re.compile(r"=+ scheduled run finished, exit (\d+) =+")
# Ashby rate-limiting is the failure the 2026-08-31 run hid behind exit 0: 46
# boards contributed nothing and the run still reported success.
_RATE_LIMITED = re.compile(r"429 Too Many Requests")
_ERROR_COUNT = re.compile(r'"errors":\s*(\d+)')


def _last_run() -> dict[str, Any]:
    """The last scheduled-run block in the log, and what went wrong inside it."""
    if not RUN_LOG.exists():
        return {"found": False, "note": f"no log at {RUN_LOG}"}
    text = RUN_LOG.read_text(encoding="utf-8", errors="replace")
    starts = list(_RUN_START.finditer(text))
    if not starts:
        return {"found": False, "note": "log has no run blocks"}
    block = text[starts[-1].start():]
    end = _RUN_END.search(block)
    errors = [int(m.group(1)) for m in _ERROR_COUNT.finditer(block)]
    return {
        "found": True,
        "started": starts[-1].group(1),
        "exit_code": int(end.group(1)) if end else None,
        "finished": end is not None,
        "rate_limited": len(_RATE_LIMITED.findall(block)),
        "stage_errors": max(errors) if errors else None,
    }


def _scheduled_task() -> dict[str, Any]:
    """Task Scheduler state. Windows only; anywhere else this is not an error."""
    if sys.platform != "win32":
        return {"available": False, "note": "not Windows"}
    ps = (
        f"$t = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction Stop; "
        "$i = $t | Get-ScheduledTaskInfo; "
        "@{state=[string]$t.State; wake=[bool]$t.Settings.WakeToRun; "
        "last=[string]$i.LastRunTime; result=$i.LastTaskResult; "
        "next=[string]$i.NextRunTime; missed=$i.NumberOfMissedRuns} "
        "| ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return {"available": False, "note": f"could not query: {e}"}
    if out.returncode != 0 or not out.stdout.strip():
        return {"available": False, "note": f"task '{TASK_NAME}' not registered"}
    try:
        return {"available": True, **json.loads(out.stdout)}
    except json.JSONDecodeError:
        return {"available": False, "note": "unreadable task info"}


def _digest(state_db: Path) -> dict[str, Any]:
    dates = state.list_digests(state_db)
    if not dates:
        return {"found": False}
    latest = max(dates)
    try:
        age = (date.today() - date.fromisoformat(latest)).days
    except ValueError:
        age = None
    return {"found": True, "latest": latest, "age_days": age, "archived": len(dates)}


def _applications(state_db: Path) -> dict[str, Any]:
    records = applied.list_applied(db_path=state_db)
    folders = sorted(p.name for p in APPLICATIONS_DIR.glob("*")
                     if p.is_dir()) if APPLICATIONS_DIR.exists() else []
    # A folder whose external_id is not in the ledger was prepped but never
    # submitted - the account-walled handoffs live here, and so does anything
    # a batch filled and nobody finished.
    logged = {r["external_id"] for r in records}
    unfinished = []
    for name in folders:
        apply_md = APPLICATIONS_DIR / name / "apply.md"
        if not apply_md.exists():
            continue
        m = re.search(r"\*\*External ID:\*\* `([^`]+)`",
                      apply_md.read_text(encoding="utf-8", errors="replace"))
        if m and m.group(1) not in logged:
            unfinished.append((name, m.group(1)))
    return {
        "applied_total": len(records),
        "last_applied": max((r["applied_at"] for r in records), default=None),
        "folders": len(folders),
        "unfinished": unfinished,
    }


def _plugin_version() -> str | None:
    if not PLUGIN_MANIFEST.exists():
        return None
    try:
        return json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8")).get("version")
    except json.JSONDecodeError:
        return None


def collect_status(*, state_db: Path = state.DEFAULT_STATE_DB) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run": _last_run(),
        "task": _scheduled_task(),
        "digest": _digest(state_db),
        "applications": _applications(state_db),
        "companies": len(state.list_companies(state_db)),
        "plugin_version": _plugin_version(),
    }


def _run_lines(run: dict[str, Any]) -> list[str]:
    if not run["found"]:
        return [f"  no pipeline run recorded ({run['note']})"]
    if not run["finished"]:
        return [f"  started {run['started']} and never finished - still running, or it died"]
    out = [f"  {run['started']}  exit {run['exit_code']}"]
    # Exit 0 is not the same as a healthy run, which is the whole point of
    # surfacing these two numbers next to it.
    if run["rate_limited"]:
        out.append(f"  {run['rate_limited']} rate-limited requests - boards were skipped")
    if run["stage_errors"]:
        out.append(f"  {run['stage_errors']} collect errors")
    if not run["rate_limited"] and not run["stage_errors"] and run["exit_code"] == 0:
        out.append("  no rate limiting, no collect errors")
    return out


def format_status(s: dict[str, Any]) -> str:
    lines = [f"job-finder status - {s['generated_at']}", ""]

    lines.append("Last pipeline run")
    lines += _run_lines(s["run"])

    lines.append("")
    lines.append("Scheduled task")
    t = s["task"]
    if t.get("available"):
        wake = "wakes the machine" if t.get("wake") else "will NOT wake the machine"
        lines.append(f"  {t.get('state')} | next {t.get('next')} | {wake}")
        lines.append(f"  last {t.get('last')} | result {t.get('result')} | "
                     f"missed {t.get('missed')}")
    else:
        lines.append(f"  {t.get('note')}")

    lines.append("")
    lines.append("Digest")
    d = s["digest"]
    if d["found"]:
        age = "unknown age" if d["age_days"] is None else f"{d['age_days']}d old"
        lines.append(f"  latest {d['latest']} ({age}) | {d['archived']} archived")
    else:
        lines.append("  none archived - the pipeline has not produced one yet")

    lines.append("")
    lines.append("Applications")
    a = s["applications"]
    lines.append(f"  {a['applied_total']} applied | last {a['last_applied'] or 'never'}")
    if a["unfinished"]:
        lines.append(f"  {len(a['unfinished'])} prepped but not in the applied ledger:")
        for name, ext in a["unfinished"]:
            lines.append(f"    {name}  [{ext}]")

    lines.append("")
    lines.append("Setup")
    lines.append(f"  {s['companies']} tracked companies")
    lines.append(f"  cowork plugin {s['plugin_version'] or '(no manifest)'} in this repo - "
                 "compare against the version Cowork shows")
    return "\n".join(lines)
