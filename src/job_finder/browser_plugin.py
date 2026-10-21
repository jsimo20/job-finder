"""Build a browser plugin whose upload folder is this folder.

The marketplace plugin's Playwright server accepts uploads only from
`job-finder/.playwright-mcp` in the user's home folder. A folder anywhere else,
or a machine where that path does not expand, gets this plugin instead: the
same server with `--output-dir` set to the folder's own `.playwright-mcp`.
The path is the folder's location on the user's computer, as the session
states it, never the path the VM mounts it at.

    sh scripts/py -m job_finder.browser_plugin --host-dir '<folder path on the computer>'

The user installs the zip it writes through Customize > Plugins > upload.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

from . import settings

# Keep in step with the version pinned in cowork-plugin/launch.js.
PLAYWRIGHT_MCP = "@playwright/mcp@0.0.79"
PLUGIN_NAME = "job-finder-browser"
ARCHIVE_NAME = f"{PLUGIN_NAME}.zip"

_ABSOLUTE = re.compile(r"^(/|[A-Za-z]:[\\/])")


def output_dir(host_dir: str) -> str:
    """The folder's `.playwright-mcp`, joined with the host path's own separator."""
    if not _ABSOLUTE.match(host_dir):
        raise ValueError(f"not an absolute path on the user's computer: {host_dir!r}")
    host = host_dir.rstrip("/\\")
    sep = "\\" if "\\" in host else "/"
    return f"{host}{sep}.playwright-mcp"


def build(host_dir: str, out: Path) -> Path:
    """Write the plugin zip to `out` and return it."""
    upload_dir = output_dir(host_dir)
    manifest = {
        "name": PLUGIN_NAME,
        "version": "1.0.0",
        "description": "job-finder's form-filling browser, set to attach files from one folder.",
        "author": {"name": "job-finder"},
    }
    mcp = {"mcpServers": {"playwright-folder": {
        "command": "npx", "args": [PLAYWRIGHT_MCP, "--output-dir", upload_dir]}}}
    skill = (f"---\nname: {PLUGIN_NAME}\ndescription: Says what the {PLUGIN_NAME} plugin "
             "is. Use only when asked about it.\n---\n\n"
             f"job-finder's form-filling browser. It attaches files from {upload_dir}.\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(".claude-plugin/plugin.json", json.dumps(manifest, indent=2))
        zf.writestr(".mcp.json", json.dumps(mcp, indent=2))
        zf.writestr(f"skills/{PLUGIN_NAME}/SKILL.md", skill)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host-dir", required=True,
                    help="the folder's path on the user's computer, as the session states it")
    ap.add_argument("--out", type=Path, default=settings.REPO_ROOT / ARCHIVE_NAME)
    args = ap.parse_args(argv)
    try:
        archive = build(args.host_dir, args.out)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"built {archive} (uploads from {output_dir(args.host_dir)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
