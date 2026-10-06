"""The weekly pipeline, split so a Cowork session can do the extraction itself.

`job-finder run` does collect, extract, score and digest in one process with an
API key. This module exposes the same stages as subcommands with a gap in the
middle: `collect` writes the surviving job descriptions out as JSON lines, the
driving session (or its subagents) reads them against `prompt` and writes the
answers back, `import-extractions` stores them, and `finish` scores, renders
the digest and stamps the run. No API key, and nothing here imports `anthropic`
or `python-dotenv`, so it runs under `PYTHONPATH=".cowork-deps:src" python3`.

    python -m job_finder.weekly status
    python -m job_finder.weekly collect
    python -m job_finder.weekly prompt
    python -m job_finder.weekly import-extractions data/weekly/extractions.jsonl
    python -m job_finder.weekly finish

A run is due when the last stamped run is `INTERVAL_DAYS` or more days old, so a
daily trigger that calls `status` first is a no-op six days out of seven.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import collect, db, digest, extract, score, state

INTERVAL_DAYS = 7
LAST_RUN_KEY = "last_weekly_run"
WEEKLY_DIR = Path(__file__).resolve().parents[2] / "data" / "weekly"
PENDING_PATH = WEEKLY_DIR / "pending_extractions.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def status(state_db: Path = state.DEFAULT_STATE_DB) -> dict:
    last = state.get_meta(LAST_RUN_KEY, state_db)
    if last is None:
        return {"last_run": None, "days_since": None, "due": True}
    days = (_now() - datetime.fromisoformat(last)).total_seconds() / 86400
    return {"last_run": last, "days_since": round(days, 1), "due": days >= INTERVAL_DAYS}


def run_collect(db_path: Path = db.DEFAULT_DB_PATH, state_db: Path = state.DEFAULT_STATE_DB,
                pending_path: Path = PENDING_PATH) -> dict:
    db.init_db(db_path)
    stats = collect.run(state_db=state_db, db_path=db_path)
    stats["pending_extractions"] = extract.export_pending(pending_path, db_path)
    stats["pending_path"] = str(pending_path)
    return stats


def finish(db_path: Path = db.DEFAULT_DB_PATH, state_db: Path = state.DEFAULT_STATE_DB,
           digest_dir: Path = digest.DEFAULT_DIGEST_DIR, *, discover: bool = True) -> dict:
    out = {"score": score.run(db_path=db_path)}
    # Discovery only proposes companies for the digest; a failure here must not
    # cost the week's digest, so it is reported and the run continues.
    if discover:
        try:
            from . import builtin_discovery
            out["discover"] = builtin_discovery.run(state_db=state_db)
        except Exception as exc:
            out["discover_error"] = str(exc)
    from . import builtin_discovery
    out["tracked"] = builtin_discovery.track_specific(state_db)
    out["digest"] = str(digest.render(db_path=db_path, digest_dir=digest_dir, state_db=state_db))
    stamp = _now().isoformat(timespec="seconds")
    state.set_meta(LAST_RUN_KEY, stamp, state_db)
    out["stamped"] = stamp
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="when the last run finished and whether one is due")
    sub.add_parser("collect", help="poll every board, filter, write the pending JDs")
    sub.add_parser("prompt", help="print the extraction instructions, verbatim")
    imp = sub.add_parser("import-extractions", help="store answers written as JSON lines")
    imp.add_argument("path", type=Path)
    sub.add_parser("finish", help="score, render the digest, stamp the run")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(json.dumps(status(), indent=1))
    elif args.cmd == "collect":
        print(json.dumps(run_collect(), indent=1))
    elif args.cmd == "prompt":
        print(extract.SYSTEM_PROMPT)
    elif args.cmd == "import-extractions":
        stats = extract.import_results(args.path)
        print(json.dumps(stats, indent=1))
        return 1 if stats["imported"] == 0 and stats["lines"] else 0
    elif args.cmd == "finish":
        print(json.dumps(finish(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
