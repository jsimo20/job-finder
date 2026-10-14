"""The plugin build refuses what Cowork's uploader would reject."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "build_cowork_plugin", REPO_ROOT / "scripts" / "build_cowork_plugin.py")
build_cowork_plugin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_cowork_plugin)


def _plugin(tmp_path: Path, *, description: str, skill_description: str) -> Path:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin/plugin.json").write_text(
        json.dumps({"name": "x", "version": "0.0.1", "description": description}),
        encoding="utf-8")
    (tmp_path / "skills/demo").mkdir(parents=True)
    (tmp_path / "skills/demo/SKILL.md").write_text(
        f"---\nname: demo\ndescription: {skill_description}\n---\n\n# demo\n",
        encoding="utf-8")
    return tmp_path


def test_shipped_plugin_passes():
    assert build_cowork_plugin.validation_errors() == []


def test_long_plugin_description_is_rejected(tmp_path):
    plugin = _plugin(tmp_path, description="a" * 501, skill_description="Fine.")
    assert build_cowork_plugin.validation_errors(plugin) == [
        "plugin description must be at most 500 characters"]


def test_angle_brackets_in_skill_description_are_rejected(tmp_path):
    plugin = _plugin(tmp_path, description="Fine.",
                     skill_description='Use for "add companies: <names>".')
    assert build_cowork_plugin.validation_errors(plugin) == [
        "skill 'demo': SKILL.md description cannot contain XML tags"]
