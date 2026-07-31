"""Export a sanitized copy of this repo for a new user.

Copies git-tracked files only, skips the owner's personal data, and inits a
fresh git repo in the target. A plain clone or fork is NOT safe to hand over:
git history contains the owner's applied log and generated digests.

What gets left behind:
- data/applied.jsonl, data/seen.jsonl — the owner's application/seen history
- seeds/no_auto_apply.json  — names the owner's inside contacts
- digests/                  — digests generated for the owner's profile
- data/*.json               — one-off seed-research artifacts for the owner's metro
- scripts/probe_*.py, scripts/_add_*.py, scripts/_check_dupes.py — ditto
- profile/                  — untracked already, but excluded belt-and-braces
- all git history

Usage:
    python scripts/export_clean_copy.py <target_dir>
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_EXACT = {
    "data/applied.jsonl",
    "data/seen.jsonl",
    "seeds/no_auto_apply.json",
}
EXCLUDE_PREFIXES = ("digests/", "profile/")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    target = Path(sys.argv[1]).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        print(f"refusing to export into non-empty directory: {target}")
        return 1
    target.mkdir(parents=True, exist_ok=True)

    copied, skipped = 0, []
    for rel in tracked_files():
        if rel in EXCLUDE_EXACT or rel.startswith(EXCLUDE_PREFIXES):
            skipped.append(rel)
            continue
        src = REPO_ROOT / rel
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    # Fresh, empty ledgers so the digest integration works from day one.
    (target / "data").mkdir(exist_ok=True)
    (target / "data" / "applied.jsonl").write_text("", encoding="utf-8")
    (target / "data" / "seen.jsonl").write_text("", encoding="utf-8")
    (target / "digests").mkdir(exist_ok=True)
    (target / "seeds").mkdir(exist_ok=True)
    (target / "seeds" / "no_auto_apply.json").write_text(
        json.dumps({
            "_comment": ("Companies that stay in the digest but must never be "
                         "auto-applied to (e.g. where you have an inside contact)."),
            "companies": [],
        }, indent=2) + "\n",
        encoding="utf-8")

    subprocess.run(["git", "init", "-b", "main"], cwd=target, check=True,
                   capture_output=True)

    print(f"exported {copied} files to {target}")
    print(f"excluded {len(skipped)} personal files:")
    for rel in skipped[:10]:
        print(f"  - {rel}")
    if len(skipped) > 10:
        print(f"  ... and {len(skipped) - 10} more (digests)")
    print("\nnext steps for the new owner: open SETUP.md and follow it top to bottom.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
