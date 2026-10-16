"""Package cowork-plugin/ as the .zip Cowork's plugin uploader accepts.

Cowork will not take a folder, and its picker hides dotfiles on some platforms,
which matters here because two of the three files this plugin needs start with a
dot. Building the archive in code avoids both problems.

The archive puts the plugin's contents at its root, so `.claude-plugin/plugin.json`
sits at the top level rather than under an extra directory.

    sh scripts/py scripts/build_cowork_plugin.py [--out DIR]

Then: the + next to the message box in a new chat, or Customize -> Plugins -> upload the .zip. Do not add the
folder as a context folder instead; a connected folder is just files on disk, so
.mcp.json never runs and the failure looks like a broken plugin.
"""
from __future__ import annotations

import argparse
import json
import re
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


MAX_PLUGIN_DESCRIPTION = 500
_TAG = re.compile(r"<[^>]*>")
_DESCRIPTION = re.compile(r"^description:\s*(.*)$", re.MULTILINE)
_NAME = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


def skill_errors(skills_dir: Path) -> list[str]:
    """Frontmatter checks for every <skills_dir>/<name>/SKILL.md.

    Applied to the repo's .claude/skills too: Cowork lists a connected folder's
    skills to the model, so a malformed one there fails for every user.
    """
    errors = []
    for skill in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill.read_text(encoding="utf-8")
        name = skill.parent.name
        declared = _NAME.search(text)
        if not declared or declared.group(1) != name:
            errors.append(f"skill {name!r}: SKILL.md name must match its folder")
        match = _DESCRIPTION.search(text)
        if not match:
            errors.append(f"skill {name!r}: SKILL.md has no description")
        elif _TAG.search(match.group(1)):
            errors.append(f"skill {name!r}: SKILL.md description cannot contain XML tags")
    return errors


def validation_errors(plugin_dir: Path = PLUGIN_DIR) -> list[str]:
    """The checks Cowork's uploader rejects a plugin for, run before zipping.

    The uploader only reports them after the user has downloaded the zip, so a
    failure here is a release nobody can install.
    """
    errors = []
    manifest = json.loads((plugin_dir / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    if len(manifest.get("description", "")) > MAX_PLUGIN_DESCRIPTION:
        errors.append(f"plugin description must be at most {MAX_PLUGIN_DESCRIPTION} characters")
    return errors + skill_errors(plugin_dir / "skills")


def build(out_dir: Path) -> Path:
    missing = [p for p in REQUIRED if not (PLUGIN_DIR / p).exists()]
    if missing:
        raise SystemExit(
            f"cowork-plugin/ is incomplete, missing: {', '.join(map(str, missing))}")
    if not list(PLUGIN_DIR.glob("skills/*/SKILL.md")):
        raise SystemExit("cowork-plugin/skills/<name>/SKILL.md not found")
    errors = validation_errors() + skill_errors(REPO_ROOT / ".claude/skills")
    if errors:
        raise SystemExit("Cowork would reject this plugin:\n  " + "\n  ".join(errors))

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
    print("\nUpload it: the + next to the message box in a new chat, or Customize -> Plugins -> upload.")
    print("Installing is not the same as adding the folder as context; only an "
          "installed plugin has its .mcp.json read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
