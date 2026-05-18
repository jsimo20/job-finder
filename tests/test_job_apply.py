"""Tests for job_apply.render() and helpers.

tailor() is intentionally not unit-tested — it makes a real LLM call and
the deterministic /job-apply flow runs the tailoring conversationally
instead. We test the pure deterministic surface.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from boston_pm_tracker import job_apply


@pytest.fixture
def fixture_resume_data() -> dict:
    """Minimal but real RESUME_DATA matching the schema in generate_resume.py."""
    return {
        "name": "Sample User",
        "title": "Principal Product Manager  |  Test Subtitle",
        "contact": "555-555-0100",
        "experience": [
            {
                "company": "CONTOSO",
                "role": "PRINCIPAL PM",
                "dates": "JUL 2022 – PRESENT",
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
        "recipient": "Hiring Team\nTest Corp\nBoston, MA",
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
        "location": "Boston, MA",
        "url": "https://example.com/jobs/test-123",
        "total_score": 85,
        "queue": "main",
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

    return job_apply.Config(
        inputs_dir=inputs,
        applications_dir=apps,
        session_context_path=session_ctx,
        resume_skill=job_apply.DEFAULT_RESUME_SKILL,
        cover_skill=job_apply.DEFAULT_COVER_SKILL,
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


def test_load_config_falls_back_to_defaults_when_no_pyproject(tmp_path):
    cfg = job_apply.load_config(pyproject_path=tmp_path / "nonexistent.toml")
    assert cfg.inputs_dir == job_apply.DEFAULT_INPUTS
    assert cfg.applications_dir == job_apply.DEFAULT_APPLICATIONS


def test_load_config_reads_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.job_apply]\n'
        f'inputs_dir = "{tmp_path.as_posix()}/custom_inputs"\n'
        f'applications_dir = "{tmp_path.as_posix()}/custom_apps"\n',
        encoding="utf-8",
    )
    cfg = job_apply.load_config(pyproject_path=pyproject)
    assert cfg.inputs_dir == Path(f"{tmp_path.as_posix()}/custom_inputs")
    assert cfg.applications_dir == Path(f"{tmp_path.as_posix()}/custom_apps")


def test_render_creates_per_job_folder_with_expected_files(
    fixture_posting_row, fixture_resume_data, fixture_cover_letter, isolated_config
):
    if not isolated_config.resume_skill.exists():
        pytest.skip("resume_generator skill not installed locally")

    outdir = job_apply.render(
        posting_row=fixture_posting_row,
        resume_data=fixture_resume_data,
        cover_letter=fixture_cover_letter,
        why_this_matches=["Bullet one", "Bullet two", "Bullet three"],
        config=isolated_config,
        open_browser=False,
    )

    assert outdir.exists()
    assert (outdir / "Sample_User_Resume_test-corp.pdf").exists()
    assert (outdir / "Sample_User_CoverLetter_test-corp.pdf").exists()
    assert (outdir / "standard_answers.md").exists()
    assert (outdir / "apply.md").exists()

    apply_md = (outdir / "apply.md").read_text(encoding="utf-8")
    assert "test-123" in apply_md
    assert "Test Corp" in apply_md
    assert "Bullet one" in apply_md
    assert "boston-pm-tracker mark-applied test-123" in apply_md


def test_render_is_idempotent(
    fixture_posting_row, fixture_resume_data, fixture_cover_letter, isolated_config
):
    if not isolated_config.resume_skill.exists():
        pytest.skip("resume_generator skill not installed locally")

    out1 = job_apply.render(
        posting_row=fixture_posting_row,
        resume_data=fixture_resume_data,
        cover_letter=fixture_cover_letter,
        why_this_matches=["a"],
        config=isolated_config,
        open_browser=False,
    )
    out2 = job_apply.render(
        posting_row=fixture_posting_row,
        resume_data=fixture_resume_data,
        cover_letter=fixture_cover_letter,
        why_this_matches=["b"],
        config=isolated_config,
        open_browser=False,
    )
    assert out1 == out2
    apply_md = (out2 / "apply.md").read_text(encoding="utf-8")
    assert "- b" in apply_md  # second run's content


def test_render_handles_invalid_resume_data(
    fixture_posting_row, fixture_cover_letter, isolated_config
):
    """Malformed RESUME_DATA should preserve the dump for debugging."""
    if not isolated_config.resume_skill.exists():
        pytest.skip("resume_generator skill not installed locally")

    broken = {"name": "James"}  # missing required keys
    with pytest.raises(RuntimeError, match="Resume render failed"):
        job_apply.render(
            posting_row=fixture_posting_row,
            resume_data=broken,
            cover_letter=fixture_cover_letter,
            why_this_matches=[],
            config=isolated_config,
            open_browser=False,
        )

    outdir = job_apply.outdir_for(fixture_posting_row, isolated_config.applications_dir)
    raw = outdir / "_resume_call_raw.json"
    assert raw.exists()
    assert json.loads(raw.read_text(encoding="utf-8")) == broken
