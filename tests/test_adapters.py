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


def test_ashby_normalize():
    from boston_pm_tracker.adapters import ashby

    jobs = json.loads((FIXTURES / "ashby_sample.json").read_text())
    normalized = [ashby.normalize(j, slug="benchling") for j in jobs if j.get("isListed")]
    assert len(normalized) == 1
    p = normalized[0]
    assert p.title == "Senior Product Manager, Platform"
    assert p.level == "senior"
    assert p.workplace_type == "hybrid"
    assert p.location == "Boston, MA"
    assert "5+ years" in p.jd_text
    assert "<p>" not in p.jd_text
    assert p.posted_at == "2026-05-01"
    assert p.url == "https://jobs.ashbyhq.com/benchling/abc-123"


def test_ashby_normalize_strips_utf8_bom():
    from boston_pm_tracker.adapters import ashby

    bom = chr(0xfeff)
    job = {
        "id": "bom-1",
        "title": f"{bom}Senior Product Manager,{bom} Payments",
        "locationName": "Boston, MA",
        "workplaceType": "Hybrid",
        "descriptionHtml": f"{bom}<p>Lead{bom} our payments roadmap.</p>{bom}",
        "publishedDate": "2026-05-20",
        "isListed": True,
    }
    p = ashby.normalize(job, slug="acme")
    assert p.title == "Senior Product Manager, Payments"
    assert bom not in p.title
    assert p.level == "senior"
    assert p.jd_text is not None
    assert bom not in p.jd_text
    assert "Lead our payments roadmap." in p.jd_text
    p.jd_text.encode("ascii", errors="strict")


def test_lever_normalize_strips_utf8_bom():
    bom = chr(0xfeff)
    posting = {
        "id": "bom-1",
        "text": f"{bom}Staff Product Manager,{bom} Agents",
        "hostedUrl": "https://jobs.lever.co/acme/bom-1",
        "categories": {"location": "Remote - US"},
        "workplaceType": "remote",
        "descriptionPlain": f"{bom}Lead our agents roadmap.{bom}",
        "lists": [{"text": f"{bom}Requirements", "content": f"6+ years{bom} of PM experience"}],
        "additionalPlain": f"{bom}Equal opportunity employer.",
        "createdAt": 1735689600000,
    }
    p = lever.normalize(posting)
    assert p.title == "Staff Product Manager, Agents"
    assert p.level == "staff"
    assert bom not in p.title
    assert p.jd_text is not None
    assert bom not in p.jd_text
    p.jd_text.encode("ascii", errors="strict")
