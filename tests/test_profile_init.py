"""SETUP.md §3 is the only definition of a new user's profile/, so it is tested here."""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import pytest

from job_finder import job_apply, profile_init, settings
from job_finder.fill_greenhouse import build_combo_fields

BLOCKS = profile_init.profile_blocks(profile_init.SETUP_MD.read_text(encoding="utf-8"))


def test_setup_md_defines_the_whole_starting_profile():
    assert set(BLOCKS) == {
        "profile.toml", "resume_master.md", "personal_statement.md", "writing-style.md",
        "standard_answers.md", "fit_profile.md", "generate_resume.py", "qa_checklist.md",
        "claims_ground_truth.md",
    }


def test_setup_md_defines_every_file_the_default_paths_resolve():
    """A profile built from SETUP.md with no [paths] table must give the apply loop
    every ground-truth file it reads, at the path load_config resolves."""
    cfg = job_apply.load_config(profile={})
    base = settings.profile_dir()
    for path in (cfg.resume_master_md, cfg.personal_statement_md, cfg.standard_answers_md,
                 cfg.qa_checklist_md, cfg.claims_ground_truth, cfg.writing_style,
                 cfg.resume_skill):
        assert path.relative_to(base).as_posix() in BLOCKS


def test_starting_profile_toml_loads_and_sets_no_eeo_answers():
    profile = tomllib.loads(BLOCKS["profile.toml"])
    assert profile["identity"]["name"]
    # Starting values must never answer EEO questions on someone's behalf.
    assert all(v == "" for v in profile["eeo"].values())


def test_starting_profile_combo_fields_have_no_eeo_rows():
    patterns = [p for p, _ in build_combo_fields(tomllib.loads(BLOCKS["profile.toml"]))]
    assert r"sponsor" in patterns
    assert r"gender" not in patterns
    assert r"disabilit" not in patterns
    assert r"pronoun" not in patterns


def test_starting_generator_compiles_with_the_markers_render_swaps():
    source = BLOCKS["generate_resume.py"]
    compile(source, "generate_resume.py", "exec")
    assert "# ---------- RESUME DATA (EDIT ONLY THIS BLOCK) ----------" in source
    assert "# ---------- STYLES (LOCKED) ----------" in source


def test_write_profile_creates_files_and_never_overwrites(tmp_path):
    dest = tmp_path / "profile"
    written, kept = profile_init.write_profile(dest)
    assert {p.name for p in written} == set(BLOCKS) and kept == []

    (dest / "profile.toml").write_text("# mine\n", encoding="utf-8")
    written, kept = profile_init.write_profile(dest)
    assert written == [] and len(kept) == len(BLOCKS)
    assert (dest / "profile.toml").read_text(encoding="utf-8") == "# mine\n"


def test_parser_honours_a_longer_fence_and_ignores_untagged_blocks():
    text = "\n".join([
        "```sh", "python -m job_finder.profile_init", "```",
        "````markdown profile/notes.md", "# Notes", "```", "inner", "```", "````",
    ])
    assert profile_init.profile_blocks(text) == {"notes.md": "# Notes\n```\ninner\n```\n"}


@pytest.mark.parametrize("text", [
    "```toml profile/../escape.toml\nx = 1\n```",
    "```toml profile/open.toml\nx = 1\n",
])
def test_parser_refuses_escaping_paths_and_unclosed_blocks(text):
    with pytest.raises(ValueError):
        profile_init.profile_blocks(text)


def test_no_profile_reads_as_empty_and_acting_on_it_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROFILE_DIR", tmp_path / "profile")
    assert settings.load_profile() == {}
    with pytest.raises(FileNotFoundError):
        settings.require_profile()
