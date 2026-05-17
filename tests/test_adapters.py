import json
from pathlib import Path

from boston_pm_tracker.adapters import greenhouse, lever

FIXTURES = Path(__file__).parent / "fixtures"


def test_greenhouse_normalize_keeps_jd_text():
    payload = json.loads((FIXTURES / "greenhouse_sample.json").read_text())
    normalized = [greenhouse.normalize(j) for j in payload["jobs"]]
    assert len(normalized) == 2
    senior = normalized[0]
    assert senior.title == "Senior Product Manager, AI Platform"
    assert senior.level == "senior"
    assert senior.workplace_type == "hybrid"
    assert senior.location == "Cambridge, MA (Hybrid)"
    assert "5+ years" in senior.jd_text
    assert "<p>" not in senior.jd_text
    assert senior.posted_at == "2026-05-10T12:00:00Z"


def test_lever_normalize():
    payload = json.loads((FIXTURES / "lever_sample.json").read_text())
    normalized = [lever.normalize(p) for p in payload]
    assert len(normalized) == 1
    staff = normalized[0]
    assert staff.title == "Staff Product Manager, Agents"
    assert staff.level == "staff"
    assert staff.workplace_type == "remote"
    assert staff.location == "Remote - US"
    assert "6+ years" in staff.jd_text
    assert staff.posted_at and staff.posted_at.startswith("2025-")
