"""Tests for the cross-half status report. No network, no Task Scheduler."""
from __future__ import annotations

import json

import pytest

from job_finder import applied, state, status as S


def _log(tmp_path, body: str):
    p = tmp_path / "scheduled-run.log"
    p.write_text(body, encoding="utf-8")
    return p


CLEAN_RUN = """
===== scheduled run started 2026-09-07T09:00:01 =====
== collect ==
{
  "companies": 705,
  "errors": 0
}
===== scheduled run finished, exit 0 =====
"""

SICK_RUN = """
===== scheduled run started 2026-08-31T10:23:24 =====
Client error '429 Too Many Requests' for url 'https://jobs.ashbyhq.com/api/non-user-graphql'
Client error '429 Too Many Requests' for url 'https://jobs.ashbyhq.com/api/non-user-graphql'
{
  "errors": 50
}
===== scheduled run finished, exit 0 =====
"""


def test_a_healthy_run_reports_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "RUN_LOG", _log(tmp_path, CLEAN_RUN))
    run = S._last_run()
    assert run["exit_code"] == 0
    assert run["rate_limited"] == 0
    assert "no rate limiting" in " ".join(S._run_lines(run))


def test_exit_zero_does_not_hide_rate_limiting(tmp_path, monkeypatch):
    """The 2026-08-31 failure: exit 0, and 46 boards contributed nothing."""
    monkeypatch.setattr(S, "RUN_LOG", _log(tmp_path, SICK_RUN))
    run = S._last_run()
    assert run["exit_code"] == 0
    assert run["rate_limited"] == 2
    assert run["stage_errors"] == 50
    text = " ".join(S._run_lines(run))
    assert "rate-limited" in text and "50 collect errors" in text


def test_only_the_most_recent_run_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "RUN_LOG", _log(tmp_path, SICK_RUN + CLEAN_RUN))
    run = S._last_run()
    assert run["started"] == "2026-09-07T09:00:01"
    assert run["rate_limited"] == 0


def test_an_unfinished_run_is_not_reported_as_a_result(tmp_path, monkeypatch):
    """A run that died mid-stage has no exit line; that is not exit 0."""
    monkeypatch.setattr(S, "RUN_LOG",
                        _log(tmp_path, "===== scheduled run started 2026-09-07T09:00:01 ====="))
    run = S._last_run()
    assert run["finished"] is False
    assert run["exit_code"] is None
    assert "never finished" in " ".join(S._run_lines(run))


def test_a_missing_log_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "RUN_LOG", tmp_path / "absent.log")
    assert S._last_run()["found"] is False


def test_a_prepped_folder_missing_from_the_ledger_is_surfaced(tmp_path, monkeypatch):
    """Account-walled handoffs and anything a batch filled but nobody finished."""
    apps = tmp_path / "applications"
    for name, ext in (("2026-09-07_acme_pm", "111"), ("2026-09-07_borealis_pm", "222")):
        d = apps / name
        d.mkdir(parents=True)
        (d / "apply.md").write_text(f"- **External ID:** `{ext}` (use ...)\n", encoding="utf-8")
    monkeypatch.setattr(S, "APPLICATIONS_DIR", apps)

    db = tmp_path / "state.db"
    applied.record_applied("111", company="Acme", title="PM", db_path=db)

    out = S._applications(db)
    assert out["applied_total"] == 1
    assert [ext for _, ext in out["unfinished"]] == ["222"]


def test_a_folder_without_apply_md_is_skipped(tmp_path, monkeypatch):
    apps = tmp_path / "applications"
    (apps / "2026-09-07_stray").mkdir(parents=True)
    monkeypatch.setattr(S, "APPLICATIONS_DIR", apps)
    assert S._applications(tmp_path / "state.db")["unfinished"] == []


def test_the_plugin_version_comes_from_the_manifest(tmp_path, monkeypatch):
    m = tmp_path / "plugin.json"
    m.write_text(json.dumps({"name": "job-finder", "version": "0.2.0"}), encoding="utf-8")
    monkeypatch.setattr(S, "PLUGIN_MANIFEST", m)
    assert S._plugin_version() == "0.2.0"


def test_a_missing_manifest_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "PLUGIN_MANIFEST", tmp_path / "absent.json")
    assert S._plugin_version() is None


def test_digest_age_from_the_archive(tmp_path):
    db = tmp_path / "state.db"
    state.save_digest("2026-09-01", "# body", db)
    state.save_digest("2026-08-25", "# older", db)
    d = S._digest(db)
    assert d["latest"] == "2026-09-01"
    assert d["archived"] == 2


def test_no_digest_yet_is_stated_plainly(tmp_path):
    assert S._digest(tmp_path / "state.db")["found"] is False


def test_the_report_is_ascii_so_a_cp1252_console_can_print_it(tmp_path, monkeypatch):
    """Windows consoles default to cp1252; the digest is a file and can carry
    Unicode, terminal output cannot."""
    monkeypatch.setattr(S, "RUN_LOG", _log(tmp_path, CLEAN_RUN))
    monkeypatch.setattr(S, "APPLICATIONS_DIR", tmp_path / "none")
    monkeypatch.setattr(S, "PLUGIN_MANIFEST", tmp_path / "absent.json")
    db = tmp_path / "state.db"
    state.save_digest("2026-09-01", "# body", db)
    text = S.format_status(S.collect_status(state_db=db))
    text.encode("cp1252")  # raises if a separator sneaks back in
    assert "Last pipeline run" in text
