"""Tests for the outreach log."""
from __future__ import annotations

import pytest

from boston_pm_tracker import outreach


def test_add_and_list_roundtrip(tmp_path):
    log = tmp_path / "outreach.jsonl"
    outreach.add_contact("Contact-A", "ZoomInfo", role_context="Agentic Tools PM",
                         message_type="hm-message", on_date="2026-07-07", path=log)
    outreach.add_contact("Contact-B", "WHOOP", on_date="2026-07-08", path=log)

    records = outreach.list_contacts(path=log)
    assert [r["name"] for r in records] == ["Contact-A", "Contact-B"]  # sorted oldest first
    assert records[0]["company"] == "ZoomInfo"
    assert records[0]["role_context"] == "Agentic Tools PM"
    assert records[0]["message_type"] == "hm-message"
    assert records[1]["message_type"] == "connection-request"  # default
    assert records[1]["role_context"] is None


def test_list_missing_file_returns_empty(tmp_path):
    assert outreach.list_contacts(path=tmp_path / "nope.jsonl") == []


def test_company_filter_is_case_insensitive_substring(tmp_path):
    log = tmp_path / "outreach.jsonl"
    outreach.add_contact("A", "ZoomInfo", on_date="2026-07-01", path=log)
    outreach.add_contact("B", "WHOOP", on_date="2026-07-02", path=log)

    hits = outreach.list_contacts(company="zoom", path=log)
    assert [r["name"] for r in hits] == ["A"]


def test_add_requires_name_and_company(tmp_path):
    log = tmp_path / "outreach.jsonl"
    with pytest.raises(ValueError):
        outreach.add_contact("", "ZoomInfo", path=log)
    with pytest.raises(ValueError):
        outreach.add_contact("Contact-A", "   ", path=log)


def test_add_rejects_unknown_message_type(tmp_path):
    with pytest.raises(ValueError):
        outreach.add_contact("Contact-A", "ZoomInfo", message_type="dm", path=tmp_path / "o.jsonl")


def test_remove_contact_is_case_insensitive(tmp_path):
    log = tmp_path / "outreach.jsonl"
    outreach.add_contact("Contact-C", "Axon", on_date="2026-07-08", path=log)
    outreach.add_contact("Contact-D", "Axon", on_date="2026-07-08", path=log)

    removed = outreach.remove_contact("contact-c", "AXON", path=log)
    assert [r["name"] for r in removed] == ["Contact-C"]
    assert [r["name"] for r in outreach.list_contacts(path=log)] == ["Contact-D"]


def test_remove_no_match_leaves_file_unchanged(tmp_path):
    log = tmp_path / "outreach.jsonl"
    outreach.add_contact("A", "Axon", on_date="2026-07-01", path=log)
    assert outreach.remove_contact("B", "Axon", path=log) == []
    assert len(outreach.list_contacts(path=log)) == 1


def test_remove_missing_file_returns_empty(tmp_path):
    assert outreach.remove_contact("A", "Axon", path=tmp_path / "nope.jsonl") == []


def test_format_contacts_empty():
    assert outreach.format_contacts([]) == "No outreach logged yet."
