"""Windowless entry point for the scheduled weekly run.

Task Scheduler launches this with pythonw.exe, which has no console, so a
Monday run never pops a terminal over whatever the user is doing. With no
console there is also no visible output — everything (logging, stage stats,
the email failure message) goes to data/logs/scheduled-run.log instead.
Redirection happens before job_finder imports so logging.basicConfig binds
to the log file, not a nonexistent stderr.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs" / "scheduled-run.log"


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_PATH, "a", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = log
    sys.stderr = log
    from datetime import datetime
    print(f"\n===== scheduled run started {datetime.now().isoformat(timespec='seconds')} =====")
    from job_finder.cli import main as cli_main
    code = cli_main(["run", "--email"])
    print(f"===== scheduled run finished, exit {code} =====")
    return code


if __name__ == "__main__":
    sys.exit(main())
