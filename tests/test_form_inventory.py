"""Tests for the ATS-agnostic field inventory (form_inventory.py).

Browser-free: these cover the manifest plumbing that the graders read. The DOM
walk in INVENTORY_JS is exercised against live forms during a fill.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from job_finder import form_inventory as fi

SAMPLE = [
    {"field_id": "#first_name", "label": "First Name *", "type": "text",
     "required": True, "value": "James", "options": None},
    {"field_id": "#gender", "label": "Gender", "type": "react-select",
     "required": False, "value": "Male", "options": None},
    {"field_id": "#salary", "label": "Desired salary *", "type": "text",
     "required": True, "value": "", "options": None},
]


def test_audit_path_shape(tmp_path):
    p = fi.audit_path("datadog-senior-pm-fleet", "pre", when=date(2026, 7, 27), base=tmp_path)
    assert p.name == "2026-07-27_datadog-senior-pm-fleet.pre.json"


def test_audit_path_rejects_unknown_phase(tmp_path):
    with pytest.raises(ValueError):
        fi.audit_path("x", "during", base=tmp_path)


def test_two_reqs_at_one_company_do_not_collide(tmp_path):
    # The Datadog resumes once overwrote each other on a shared filename; the
    # slug carries the role so manifests can't repeat it.
    a = fi.audit_path("mavenagi-senior-pm-integrations", "post", base=tmp_path)
    b = fi.audit_path("mavenagi-senior-pm-voice-agent", "post", base=tmp_path)
    assert a != b


def test_write_audit_roundtrip(tmp_path):
    path = fi.write_audit(SAMPLE, slug="acme-pm", phase="pre",
                          url="https://example.test/apply",
                          when=date(2026, 7, 27), base=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["slug"] == "acme-pm"
    assert payload["phase"] == "pre"
    assert payload["field_count"] == 3
    assert payload["fields"] == SAMPLE


def test_write_audit_accepts_extra_meta(tmp_path):
    path = fi.write_audit([], slug="acme-pm", phase="post", url="u",
                          base=tmp_path, ats="greenhouse", snapshots=7)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ats"] == "greenhouse" and payload["snapshots"] == 7


def test_merge_options_backfills_only_unknown_lists():
    inv = [
        {"label": "Gender", "options": None},
        {"label": "Country", "options": ["United States"]},  # native select, known
    ]
    fi.merge_options(inv, {"Gender": ["Male", "Female", "Decline"],
                           "Country": ["SHOULD NOT OVERWRITE"]})
    assert inv[0]["options"] == ["Male", "Female", "Decline"]
    assert inv[1]["options"] == ["United States"]


def test_redact_keeps_structure_drops_values():
    out = fi.redact(SAMPLE)
    assert [f["value"] for f in out] == ["<filled>", "<filled>", ""]
    # everything Layer 1 asserts on survives
    for before, after in zip(SAMPLE, out):
        for key in ("field_id", "label", "type", "required", "options"):
            assert before[key] == after[key]
    assert "James" not in json.dumps(out)


def test_inventory_js_is_a_bare_arrow_function():
    # Playwright rejects a page function that isn't a single expression.
    js = fi.INVENTORY_JS.strip()
    assert js.startswith("() =>") and js.endswith("}")
