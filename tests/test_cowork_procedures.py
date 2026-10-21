"""Rules every procedure must follow to run on Cowork as well as Claude Code."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCEDURES = sorted([*REPO_ROOT.glob(".claude/skills/*/SKILL.md"),
                     *REPO_ROOT.glob(".claude/commands/*.md"),
                     *REPO_ROOT.glob("cowork-plugin/skills/*/SKILL.md")])
REPO_AGENTS = {p.stem for p in REPO_ROOT.glob(".claude/agents/*.md")}


def test_no_procedure_dispatches_a_named_repo_agent():
    # Cowork does not load .claude/agents/, so a named subagent_type fails there.
    offenders = [f"{p.relative_to(REPO_ROOT)}: {m.group(0)}"
                 for p in PROCEDURES
                 for m in re.finditer(r"subagent_type[`:\s]+`?([\w-]+)", p.read_text(encoding="utf-8"))
                 if m.group(1) in REPO_AGENTS]
    assert offenders == []


def test_every_entry_point_exists():
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    section = claude_md.split("## Working in Cowork", 1)[1].split("\n## ", 1)[0]
    paths = {p for p in re.findall(r"`(\.claude/[^`]+\.md)`", section) if "<" not in p}
    assert paths, "the entry-point table names no procedures"
    assert sorted(p for p in paths if not (REPO_ROOT / p).exists()) == []


def test_no_procedure_names_a_profile_layout():
    # Profile paths resolve through profile.toml [paths]; a prompt that names
    # `profile/<dir>/` hard-codes one user's folders into everyone's run.
    offenders = [f"{p.relative_to(REPO_ROOT)}:{n}"
                 for p in PROCEDURES + sorted(REPO_ROOT.glob(".claude/agents/*.md"))
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 for m in re.finditer(r"profile/([A-Za-z_-]+)/", line)
                 if m.group(1) != "applications"]
    assert offenders == []


# A venv interpreter, a Cowork-only PYTHONPATH prefix or a drive-letter path
# runs on one surface or OS only; procedures call `sh scripts/py` instead. The
# lookahead admits the placeholder `C:\Users\<your name>` shown to users.
OS_SPECIFIC = re.compile(r"\.venv[/\\]|python\.exe|job-finder\.exe|PYTHONPATH=|System32"
                         r"|\b[A-Za-z]:\\(?!Users\\<)")


def test_no_procedure_names_an_os_specific_path():
    files = (PROCEDURES + sorted(REPO_ROOT.glob(".claude/agents/*.md"))
             + sorted(REPO_ROOT.glob(".claude/context/*.md")) + [REPO_ROOT / "CLAUDE.md"])
    offenders = [f"{p.relative_to(REPO_ROOT)}:{n}: {m.group(0)}"
                 for p in files
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 for m in OS_SPECIFIC.finditer(line)]
    assert offenders == []


def test_no_mcp_config_names_an_absolute_path():
    # One machine's absolute --output-dir breaks uploads on every other machine.
    offenders = [f"{path.relative_to(REPO_ROOT)}: {server}: {arg}"
                 for path in (REPO_ROOT / ".mcp.json", REPO_ROOT / "cowork-plugin/.mcp.json")
                 for server, cfg in json.loads(path.read_text(encoding="utf-8"))["mcpServers"].items()
                 for arg in cfg.get("args", [])
                 if re.match(r"[A-Za-z]:[\\/]|/", arg)]
    assert offenders == []
