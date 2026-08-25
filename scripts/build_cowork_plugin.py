"""Package cowork-plugin/ as the .zip Cowork's plugin uploader accepts.

Cowork will not take a folder, and its picker hides dotfiles on some platforms,
which matters here because two of the three files this plugin needs start with a
dot. Building the archive in code avoids both problems.

The archive puts the plugin's contents at its root, so `.claude-plugin/plugin.json`
sits at the top level rather than under an extra directory.

    python scripts/build_cowork_plugin.py [--out DIR]

Then: Cowork tab -> Customize -> Plugins -> upload the .zip. Do not add the
folder as a context folder instead; a connected folder is just files on disk, so
.mcp.json never runs and the failure looks like a broken plugin.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "cowork-plugin"
ARCHIVE_NAME = "job-finder-cowork-plugin.zip"

REQUIRED = [
    Path(".claude-plugin/plugin.json"),
    Path(".mcp.json"),
]


def build(out_dir: Path) -> Path:
    missing = [p for p in REQUIRED if not (PLUGIN_DIR / p).exists()]
    if missing:
        raise SystemExit(
            f"cowork-plugin/ is incomplete, missing: {', '.join(map(str, missing))}")
    if not list(PLUGIN_DIR.glob("skills/*/SKILL.md")):
        raise SystemExit("cowork-plugin/skills/<name>/SKILL.md not found")

    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / ARCHIVE_NAME
    archive.unlink(missing_ok=True)

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PLUGIN_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(PLUGIN_DIR).as_posix())
    return archive


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path.home() / "Downloads",
                    help="where to write the .zip (default: ~/Downloads)")
    args = ap.parse_args()

    archive = build(args.out)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    print(f"built {archive}")
    for name in names:
        print(f"  {name}")
    print("\nUpload it: Cowork tab -> Customize -> Plugins -> upload.")
    print("Installing is not the same as adding the folder as context; only an "
          "installed plugin has its .mcp.json read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
