"""Tests for job_apply.render() and helpers.

tailor() is intentionally not unit-tested — it makes a real LLM call and
the deterministic /job-apply flow runs the tailoring conversationally
instead. We test the pure deterministic surface.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_finder import job_apply


@pytest.fixture
def fixture_resume_data() -> dict:
    """Minimal but real RESUME_DATA matching the schema in generate_resume.py."""
    return {
        "name": "Test Person",
        "title": "Principal Product Manager  |  Test Subtitle",
        "contact": "555-555-0100",
        "experience": [
            {
                "company": "TEST CORP",
                "role": "PRINCIPAL PM",
                "dates": "JAN 2020 – PRESENT",
                "bullets": ["Test bullet about something."],
            },
        ],
        "skills": [
            ("Test Cat 1", "test body 1"),
            ("Test Cat 2", "test body 2"),
            ("Test Cat 3", "test body 3"),
            ("Test Cat 4", "test body 4"),
        ],
        "education": {
            "degree": "BS Test",
            "minor": "Minor: testing",
            "school": "Test University",
            "dates": "2016 - 2020",
        },
        "certifications": ["Test cert", "Test cert 2"],
    }


@pytest.fixture
def fixture_cover_letter() -> dict:
    return {
        "date": "May 17, 2026",
        "recipient": "Hiring Team\nTest Corp\nFarport, EX",
        "salutation": "To the Hiring Team,",
        "paragraphs": [
            "First paragraph of the cover letter.",
            "Second paragraph with substance.",
        ],
        "closing": "Looking forward,",
        "title_subtitle": "Principal Product Manager | Test Subtitle",
    }


@pytest.fixture
def fixture_posting_row() -> dict:
    return {
        "external_id": "test-123",
        "title": "Senior Product Manager, Platform",
        "company_name": "Test Corp",
        "location": "Farport, EX",
        "url": "https://example.com/jobs/test-123",
        "total_score": 85,
        "queue": "main",
    }


@pytest.fixture
def fixture_profile() -> dict:
    return {
        "identity": {
            "name": "Test Person",
            "title_subtitle": "Senior PM | Test Positioning",
            "email": "test.person@example.com",
            "phone": "555-555-0100",
            "linkedin": "https://www.linkedin.com/in/test-person/",
        },
    }


@pytest.fixture
def isolated_config(tmp_path: Path) -> job_apply.Config:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "resume_master.md").write_text("# master resume\n", encoding="utf-8")
    (inputs / "personal_statement.md").write_text("# statement\n", encoding="utf-8")
    (inputs / "standard_answers.md").write_text("# standard answers\n- pronoun: he/him\n", encoding="utf-8")

    apps = tmp_path / "applications"
    session_ctx = tmp_path / "session_ctx.md"
    session_ctx.write_text("# anti-overstatement rules\n", encoding="utf-8")

    # The vendored template ships with the repo, so render tests never skip.
    return job_apply.Config(
        inputs_dir=inputs,
        applications_dir=apps,
        claims_ground_truth=session_ctx,
        resume_skill=job_apply.REPO_ROOT / "profile.example" / "generate_resume.py",
    )


# ─────────────────────────────────────────────────────────────────────────────


def test_slugify_strips_special_chars():
    assert job_apply.slugify("Test Corp, Inc.") == "test-corp-inc"
    assert job_apply.slugify("Senior PM — Platform & API") == "senior-pm-platform-api"
    assert job_apply.slugify("") == "untitled"


def test_slugify_respects_max_len():
    long = "a" * 100
    assert len(job_apply.slugify(long, max_len=20)) == 20


def test_outdir_for_format(fixture_posting_row, tmp_path):
    out = job_apply.outdir_for(fixture_posting_row, tmp_path)
    parts = out.name.split("_", 2)
    assert len(parts) == 3
    assert parts[1] == "test-corp"
    assert parts[2] == "senior-product-manager-platform"


def test_load_config_defaults_into_profile_dir():
    """Without a [paths] table every path resolves inside the profile dir."""
    from job_finder import settings

    cfg = job_apply.load_config(profile={})
    base = settings.profile_dir()
    assert cfg.inputs_dir == base
    assert cfg.applications_dir == base / "applications"
    assert cfg.resume_skill == base / "generate_resume.py"


def test_load_config_reads_profile_paths(tmp_path):
    profile = {
        "paths": {
            "inputs_dir": f"{tmp_path.as_posix()}/custom_inputs",
            "applications_dir": f"{tmp_path.as_posix()}/custom_apps",
        }
    }
    cfg = job_apply.load_config(profile=profile)
    assert cfg.inputs_dir == Path(f"{tmp_path.as_posix()}/custom_inputs")
    assert cfg.applications_dir == Path(f"{tmp_path.as_posix()}/custom_apps")


def test_render_creates_per_job_folder_with_expected_files(
    fixture_posting_row, fixture_resume_data, fixture_cover_letter,
    isolated_config, fixture_profile
):
    outdir = job_apply.render(
        posting_row=fixture_posting_row,
        resume_data=fixture_resume_data,
        cover_letter=fixture_cover_letter,
        why_this_matches=["Bullet one", "Bullet two", "Bullet three"],
        config=isolated_config,
        profile=fixture_profile,
        open_browser=False,
    )

    assert outdir.exists()
    assert (outdir / "Test_Person_Resume_test-corp.pdf").exists()
    assert (outdir / "Test_Person_CoverLetter_test-corp.pdf").exists()
    assert (outdir / "standard_answers.md").exists()
    assert (outdir / "apply.md").exists()

    apply_md = (outdir / "apply.md").read_text(encoding="utf-8")
    assert "test-123" in apply_md
    assert "Test Corp" in apply_md
    assert "Bullet one" in apply_md
    assert "job-finder mark-applied test-123" in apply_md


def test_render_is_idempotent(
    fixture_posting_row, fixture_resume_data, fixture_cover_letter,
    isolated_config, fixture_profile
):
    out1 = job_apply.render(
        posting_row=fixture_posting_row,
        resume_data=fixture_resume_data,
        cover_letter=fixture_cover_letter,
        why_this_matches=["a"],
        config=isolated_config,
        profile=fixture_profile,
        open_browser=False,
    )
    out2 = job_apply.render(
        posting_row=fixture_posting_row,
        resume_data=fixture_resume_data,
        cover_letter=fixture_cover_letter,
        why_this_matches=["b"],
        config=isolated_config,
        profile=fixture_profile,
        open_browser=False,
    )
    assert out1 == out2
    apply_md = (out2 / "apply.md").read_text(encoding="utf-8")
    assert "- b" in apply_md  # second run's content


def test_render_handles_invalid_resume_data(
    fixture_posting_row, fixture_cover_letter, isolated_config, fixture_profile
):
    """Malformed RESUME_DATA should preserve the dump for debugging."""
    broken = {"name": "Test Person"}  # missing required keys
    with pytest.raises(RuntimeError, match="Resume render failed"):
        job_apply.render(
            posting_row=fixture_posting_row,
            resume_data=broken,
            cover_letter=fixture_cover_letter,
            why_this_matches=[],
            config=isolated_config,
            profile=fixture_profile,
            open_browser=False,
        )

    outdir = job_apply.outdir_for(fixture_posting_row, isolated_config.applications_dir)
    raw = outdir / "_resume_call_raw.json"
    assert raw.exists()
    assert json.loads(raw.read_text(encoding="utf-8")) == broken


def test_relative_profile_paths_resolve_against_the_repo_not_the_cwd(monkeypatch, tmp_path):
    """The profile may point at junctions inside the workspace; those are relative.

    Resolving them against the working directory would break the scheduled task
    and any session started elsewhere.
    """
    monkeypatch.chdir(tmp_path)
    config = job_apply.load_config({"paths": {
        "inputs_dir": "profile/inputs",
        "claims_ground_truth_path": "profile/ai_skills/claims_ground_truth.md",
    }})
    repo_root = Path(job_apply.__file__).resolve().parents[2]
    assert config.inputs_dir == repo_root / "profile" / "inputs"
    assert config.claims_ground_truth == repo_root / "profile" / "ai_skills" / "claims_ground_truth.md"


def test_absolute_profile_paths_are_left_alone(tmp_path):
    config = job_apply.load_config({"paths": {"inputs_dir": str(tmp_path)}})
    assert config.inputs_dir == tmp_path


def test_tilde_profile_paths_still_expand():
    config = job_apply.load_config({"paths": {"inputs_dir": "~/some-inputs"}})
    assert config.inputs_dir == Path.home() / "some-inputs"
