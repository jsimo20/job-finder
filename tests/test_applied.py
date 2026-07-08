"""Tests for the durable applied-log (applied.py)."""
from __future__ import annotations

from boston_pm_tracker import applied


def test_record_and_list(tmp_path):
    p = tmp_path / "applied.jsonl"
    rec = applied.record_applied("8030599", company="Datadog", title="Senior PM - Agent Integrations",
                                 url="https://careers.datadoghq.com/detail/8030599/?gh_jid=8030599",
                                 applied_on="2026-07-08", path=p)
    assert rec is not None
    rows = applied.list_applied(path=p)
    assert len(rows) == 1
    assert rows[0]["external_id"] == "8030599"
    assert rows[0]["company"] == "Datadog"
    assert rows[0]["applied_at"] == "2026-07-08"


def test_dedupe_by_external_id(tmp_path):
    p = tmp_path / "applied.jsonl"
    first = applied.record_applied("abc-123", company="WHOOP", title="Senior PM, Growth", path=p)
    second = applied.record_applied("abc-123", company="WHOOP", title="Senior PM, Growth (dupe)", path=p)
    assert first is not None
    assert second is None  # already logged
    assert len(applied.list_applied(path=p)) == 1


def test_is_applied_by_external_id(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("5252943008", company="Starburst", title="Senior PM - IAM", path=p)
    assert applied.is_applied(external_id="5252943008", path=p) is True
    assert applied.is_applied(external_id="nope", path=p) is False


def test_is_applied_by_url_normalization(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("x1", company="Assembled", title="Senior PM",
                           url="https://jobs.ashbyhq.com/assembledhq/526d0177", path=p)
    # Same role, different scheme + an /application suffix + tracking query — still matches.
    assert applied.is_applied(url="http://jobs.ashbyhq.com/assembledhq/526d0177/application?lever-source=x", path=p) is True
    assert applied.is_applied(url="https://jobs.ashbyhq.com/other/999", path=p) is False


def test_applied_external_ids_set(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("a", company="C1", title="T1", path=p)
    applied.record_applied("b", company="C2", title="T2", path=p)
    assert applied.applied_external_ids(path=p) == {"a", "b"}


def test_list_filter_by_company(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("a", company="Datadog", title="T1", path=p)
    applied.record_applied("b", company="WHOOP", title="T2", path=p)
    rows = applied.list_applied(company="datadog", path=p)
    assert len(rows) == 1 and rows[0]["company"] == "Datadog"


def test_missing_required_fields(tmp_path):
    p = tmp_path / "applied.jsonl"
    for bad in (("", "C", "T"), ("id", "", "T"), ("id", "C", "")):
        try:
            applied.record_applied(bad[0], company=bad[1], title=bad[2], path=p)
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_empty_log(tmp_path):
    p = tmp_path / "applied.jsonl"
    assert applied.list_applied(path=p) == []
    assert applied.applied_external_ids(path=p) == set()
    assert applied.is_applied(external_id="x", path=p) is False
    assert applied.format_applied([]) == "No applications logged yet."
