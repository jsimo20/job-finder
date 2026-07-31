"""Tests for the first-seen ledger and the digest's new/carried split."""
from __future__ import annotations

from job_finder import seen
from job_finder.digest import split_new_carry


def test_record_and_load_roundtrip(tmp_path):
    p = tmp_path / "state.db"
    assert seen.record_seen(["a", "b"], "2026-07-01", p) == 2
    assert seen.record_seen(["b", "c", ""], "2026-07-08", p) == 1  # b dupe, "" skipped
    assert seen.load_seen(p) == {"a": "2026-07-01", "b": "2026-07-01", "c": "2026-07-08"}


def test_load_missing_db_is_empty(tmp_path):
    assert seen.load_seen(tmp_path / "nope.db") == {}


def _rows(*eids):
    return [{"external_id": e} for e in eids]


def test_split_unseen_rows_are_new():
    new, carry = split_new_carry(_rows("a", "b"), {}, "2026-08-03")
    assert [r["external_id"] for r in new] == ["a", "b"]
    assert carry == []


def test_split_previously_seen_rows_carry_forward():
    ledger = {"a": "2026-07-27"}
    new, carry = split_new_carry(_rows("a", "b"), ledger, "2026-08-03")
    assert [r["external_id"] for r in new] == ["b"]
    assert [r["external_id"] for r in carry] == ["a"]


def test_split_same_day_rerender_is_stable():
    """A row first recorded on the target date itself still counts as new, so
    rendering twice on the same day produces the same digest."""
    ledger = {"a": "2026-08-03"}
    new, carry = split_new_carry(_rows("a"), ledger, "2026-08-03")
    assert [r["external_id"] for r in new] == ["a"]
    assert carry == []


def test_split_caps_carry_forward():
    from job_finder.digest import CARRY_FORWARD_CAP
    ledger = {f"e{i}": "2026-07-01" for i in range(CARRY_FORWARD_CAP + 5)}
    new, carry = split_new_carry(_rows(*ledger), ledger, "2026-08-03")
    assert len(carry) == CARRY_FORWARD_CAP
