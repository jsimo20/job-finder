"""Rules every procedure must follow to run on Cowork as well as Claude Code."""
from __future__ import annotations

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
