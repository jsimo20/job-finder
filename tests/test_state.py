"""Tests for the local-first state store (state.py, emailer)."""
from __future__ import annotations

import json

import pytest

from job_finder import emailer, state


def test_company_crud_roundtrip(tmp_path):
    db = tmp_path / "state.db"
    state.upsert_company({"name": "Example Co", "ats_provider": "greenhouse",
                          "ats_slug": "exampleco", "sector_tags": ["saas"]}, db)
    state.upsert_company({"name": "Other Corp", "ats_provider": "ashby",
                          "ats_slug": "othercorp"}, db)
    rows = state.list_companies(db)
    assert [r["name"] for r in rows] == ["Example Co", "Other Corp"]
    assert rows[0]["sector_tags"] == ["saas"]
    # upsert updates in place, no duplicate
    state.upsert_company({"name": "Example Co", "ats_provider": "lever",
                          "ats_slug": "example-co"}, db)
    rows = state.list_companies(db)
    assert len(rows) == 2 and rows[0]["ats_provider"] == "lever"
    assert state.remove_company("EXAMPLE CO", db) is True
    assert len(state.list_companies(db)) == 1


def test_company_requires_core_fields(tmp_path):
    with pytest.raises(ValueError):
        state.upsert_company({"name": "X"}, tmp_path / "s.db")


def test_manual_company_needs_url_not_slug(tmp_path):
    db = tmp_path / "state.db"
    # No pollable board: a careers URL stands in for the slug.
    state.upsert_company({"name": "Handmade Widgets", "ats_provider": "manual",
                          "careers_url": "https://example.com/careers"}, db)
    row = state.list_companies(db)[0]
    assert row["ats_provider"] == "manual"
    assert row["ats_slug"] == ""
    assert row["careers_url"] == "https://example.com/careers"
    with pytest.raises(ValueError, match="careers_url"):
        state.upsert_company({"name": "No URL Co", "ats_provider": "manual"}, db)
    # Non-manual providers still require the slug.
    with pytest.raises(ValueError, match="ats_slug"):
        state.upsert_company({"name": "Slugless", "ats_provider": "greenhouse",
                              "careers_url": "https://example.com"}, db)


def test_import_and_export_companies(tmp_path):
    db = tmp_path / "state.db"
    src = tmp_path / "in.json"
    src.write_text(json.dumps({"companies": [
        {"name": "A", "ats_provider": "greenhouse", "ats_slug": "a",
         "_live_postings": 5},   # underscore keys from the prober are dropped
        {"name": "B", "ats_provider": "lever", "ats_slug": "b"},
    ]}), encoding="utf-8")
    assert state.import_companies(src, db) == 2
    out = tmp_path / "out.json"
    assert state.export_companies(out, db) == 2
    assert [r["name"] for r in json.loads(out.read_text(encoding="utf-8"))] == ["A", "B"]


def test_no_auto_apply_blocklist(tmp_path):
    db = tmp_path / "state.db"
    state.add_no_auto("Example Co", "inside contact", db_path=db)
    assert state.is_no_auto("example co", db)
    assert not state.is_no_auto("Other", db)
    assert state.remove_no_auto("EXAMPLE CO", db) is True
    assert state.list_no_auto(db) == []


def test_digest_archive_latest_and_by_date(tmp_path):
    db = tmp_path / "state.db"
    state.save_digest("2026-08-03", "first body", db)
    state.save_digest("2026-08-10", "second body", db)
    assert state.get_digest(db_path=db)["date"] == "2026-08-10"
    assert state.get_digest("2026-08-03", db)["body"] == "first body"
    state.save_digest("2026-08-10", "revised body", db)   # re-render same date
    assert state.get_digest("2026-08-10", db)["body"] == "revised body"
    assert state.list_digests(db) == ["2026-08-03", "2026-08-10"]


def test_emailer_refuses_without_credentials(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="GMAIL_USER"):
        emailer.send_digest("body", "2026-08-03")


def test_emailer_sends_when_configured(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def login(self, user, password):
            sent["login"] = user
        def send_message(self, msg):
            sent["subject"] = msg["Subject"]
            sent["to"] = msg["To"]

    monkeypatch.setenv("GMAIL_USER", "u@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x" * 16)
    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", FakeSMTP)
    emailer.send_digest("body", "2026-08-03")
    assert sent == {"host": "smtp.gmail.com", "login": "u@example.com",
                    "subject": "Job Digest — 2026-08-03", "to": "u@example.com"}
