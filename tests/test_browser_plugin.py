"""The per-folder browser plugin and the marketplace that ships the main one."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from job_finder import browser_plugin as B

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("host, expected", [
    (r"C:\Users\Alex Sample\Documents\job-finder",
     r"C:\Users\Alex Sample\Documents\job-finder\.playwright-mcp"),
    ("/Users/alex/Documents/job-finder/", "/Users/alex/Documents/job-finder/.playwright-mcp"),
])
def test_output_dir_keeps_the_host_separator(host, expected):
    assert B.output_dir(host) == expected


def test_a_relative_path_is_refused():
    with pytest.raises(ValueError, match="not an absolute path"):
        B.output_dir("job-finder")


def test_build_writes_an_installable_plugin(tmp_path):
    archive = B.build("/Users/alex/job-finder", tmp_path / B.ARCHIVE_NAME)
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read(".claude-plugin/plugin.json"))
        servers = json.loads(zf.read(".mcp.json"))["mcpServers"]
    assert names == {".claude-plugin/plugin.json", ".mcp.json",
                     f"skills/{B.PLUGIN_NAME}/SKILL.md"}
    assert manifest["name"] == B.PLUGIN_NAME
    [(name, server)] = servers.items()
    assert "playwright" in name
    assert server["args"] == [B.PLAYWRIGHT_MCP, "--output-dir",
                              "/Users/alex/job-finder/.playwright-mcp"]


def test_every_playwright_pin_matches():
    pins = {B.PLAYWRIGHT_MCP}
    for path in (REPO_ROOT / ".mcp.json", REPO_ROOT / "cowork-plugin/.mcp.json"):
        for server in json.loads(path.read_text(encoding="utf-8"))["mcpServers"].values():
            pins.add(server["args"][0])
    assert len(pins) == 1, pins


def test_marketplace_entry_matches_the_plugin():
    market = json.loads((REPO_ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    [entry] = market["plugins"]
    plugin_dir = REPO_ROOT / entry["source"]
    manifest = json.loads((plugin_dir / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert entry["name"] == manifest["name"]
    # Sync delivers a change only when this version moves, so it must exist.
    assert manifest.get("version")
    assert "version" not in entry
