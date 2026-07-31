"""Tests for the durable applied-log (applied.py)."""
from __future__ import annotations

from job_finder import applied, cli


def test_record_and_list(tmp_path):
    p = tmp_path / "applied.jsonl"
    rec = applied.record_applied("1234567", company="Example Co", title="Senior PM - Integrations",
                                 url="https://careers.example.com/detail/1234567/?gh_jid=1234567",
                                 applied_on="2026-07-08", path=p)
    assert rec is not None
    rows = applied.list_applied(path=p)
    assert len(rows) == 1
    assert rows[0]["external_id"] == "1234567"
    assert rows[0]["company"] == "Example Co"
    assert rows[0]["applied_at"] == "2026-07-08"


def test_dedupe_by_external_id(tmp_path):
    p = tmp_path / "applied.jsonl"
    first = applied.record_applied("abc-123", company="Other Corp", title="Senior PM, Growth", path=p)
    second = applied.record_applied("abc-123", company="Other Corp", title="Senior PM, Growth (dupe)", path=p)
    assert first is not None
    assert second is None  # already logged
    assert len(applied.list_applied(path=p)) == 1


def test_is_applied_by_external_id(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("5250000000", company="Example Co", title="Senior PM - IAM", path=p)
    assert applied.is_applied(external_id="5250000000", path=p) is True
    assert applied.is_applied(external_id="nope", path=p) is False


def test_is_applied_by_url_normalization(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("x1", company="Example Co", title="Senior PM",
                           url="https://jobs.ashbyhq.com/exampleco/526d0177", path=p)
    # Same role, different scheme + an /application suffix + tracking query — still matches.
    assert applied.is_applied(url="http://jobs.ashbyhq.com/exampleco/526d0177/application?lever-source=x", path=p) is True
    assert applied.is_applied(url="https://jobs.ashbyhq.com/other/999", path=p) is False


def test_applied_external_ids_set(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("a", company="C1", title="T1", path=p)
    applied.record_applied("b", company="C2", title="T2", path=p)
    assert applied.applied_external_ids(path=p) == {"a", "b"}


def test_list_filter_by_company(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("a", company="Example Co", title="T1", path=p)
    applied.record_applied("b", company="Other Corp", title="T2", path=p)
    rows = applied.list_applied(company="example", path=p)
    assert len(rows) == 1 and rows[0]["company"] == "Example Co"


def test_missing_required_fields(tmp_path):
    p = tmp_path / "applied.jsonl"
    for bad in (("", "C", "T"), ("id", "", "T"), ("id", "C", "")):
        try:
            applied.record_applied(bad[0], company=bad[1], title=bad[2], path=p)
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_remove_applied(tmp_path):
    p = tmp_path / "applied.jsonl"
    applied.record_applied("a", company="C1", title="T1", path=p)
    applied.record_applied("b", company="C2", title="T2", path=p)
    removed = applied.remove_applied("a", path=p)
    assert removed is not None and removed["external_id"] == "a"
    assert applied.applied_external_ids(path=p) == {"b"}
    assert applied.remove_applied("nope", path=p) is None  # no match
    assert applied.remove_applied("b", path=p) is not None
    assert applied.list_applied(path=p) == []  # file emptied


def test_cli_applied_remove_is_reachable(tmp_path, monkeypatch):
    # remove_applied() worked for 19 days; the bug was that no argparse
    # subcommand reached it. Goes through cli.main so it fails on wiring.
    p = tmp_path / "applied.jsonl"
    applied.record_applied("a", company="C1", title="T1", path=p)
    real_remove = applied.remove_applied
    monkeypatch.setattr(cli.applied, "remove_applied",
                        lambda external_id, path=p: real_remove(external_id, path=path))
    assert cli.main(["applied", "remove", "--external-id", "a"]) == 0
    assert applied.applied_external_ids(path=p) == set()
    assert cli.main(["applied", "remove", "--external-id", "nope"]) == 1


def test_empty_log(tmp_path):
    p = tmp_path / "applied.jsonl"
    assert applied.list_applied(path=p) == []
    assert applied.applied_external_ids(path=p) == set()
    assert applied.is_applied(external_id="x", path=p) is False
    assert applied.format_applied([]) == "No applications logged yet."


def test_applied_company_titles_normalizes_punctuation(tmp_path):
    path = tmp_path / "applied.jsonl"
    applied.record_applied("9000001", company="Example Co",
                           title="Senior Product Manager - AI Data Foundation",
                           path=path)
    pairs = applied.applied_company_titles(path=path)
    assert ("example co", "senior product manager ai data foundation") in pairs
    # the repost's comma-phrased title normalizes to the same pair
    assert applied._norm_title("Senior Product Manager, AI Data Foundation") == \
        "senior product manager ai data foundation"


def test_norm_title_handles_empty():
    assert applied._norm_title(None) is None
    assert applied._norm_title("  --  ") is None
