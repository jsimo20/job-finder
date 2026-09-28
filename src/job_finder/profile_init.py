"""Write the starting profile/ files that SETUP.md §3 defines.

SETUP.md is the only place those files exist in the repo. Each one is a fenced
block whose info string names its destination, for example a block opened with
three backticks, `toml` and `profile/profile.toml`. This writes every such
block into profile/ and never overwrites a file that is already there, so
running it over a real profile changes nothing.

    python -m job_finder.profile_init
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from . import settings

SETUP_MD = settings.REPO_ROOT / "SETUP.md"

_OPEN = re.compile(r"^(`{3,})[\w.+-]*\s+profile/(\S+)\s*$")


def profile_blocks(text: str) -> dict[str, str]:
    """{file name under profile/: content} for every destination-tagged block."""
    blocks: dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _OPEN.match(lines[i])
        i += 1
        if not m:
            continue
        fence, name = m.group(1), m.group(2)
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"SETUP.md block names a path outside profile/: {name}")
        body: list[str] = []
        while i < len(lines) and not (lines[i].startswith(fence)
                                      and lines[i].strip("`") == ""):
            body.append(lines[i])
            i += 1
        if i == len(lines):
            raise ValueError(f"SETUP.md block for profile/{name} is never closed")
        i += 1
        blocks[name] = "\n".join(body) + "\n"
    return blocks


def write_profile(dest: Path | None = None, setup_md: Path = SETUP_MD
                  ) -> tuple[list[Path], list[Path]]:
    """Write every block into `dest`. Returns (written, left alone because present)."""
    dest = dest or settings.PROFILE_DIR
    written: list[Path] = []
    kept: list[Path] = []
    for name, content in profile_blocks(setup_md.read_text(encoding="utf-8")).items():
        path = dest / name
        if path.exists():
            kept.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written, kept


def main() -> int:
    written, kept = write_profile()
    for p in written:
        print(f"wrote   {p.relative_to(settings.REPO_ROOT).as_posix()}")
    for p in kept:
        print(f"kept    {p.relative_to(settings.REPO_ROOT).as_posix()} (already exists)")
    print("\nEvery written file still holds example values. Edit them in the order "
          "SETUP.md §3 lists, then run `python -m job_finder.profile_check`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
