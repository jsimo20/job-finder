import json
from pathlib import Path

from job_finder.adapters import greenhouse, lever

FIXTURES = Path(__file__).parent / "fixtures"


def test_greenhouse_normalize_keeps_jd_text():
    payload = json.loads((FIXTURES / "greenhouse_sample.json").read_text())
    normalized = [greenhouse.normalize(j) for j in payload["jobs"]]
    assert len(normalized) == 2
    senior = normalized[0]
    assert senior.title == "Senior Product Manager, AI Platform"
    assert senior.workplace_type == "hybrid"
    assert senior.location == "Bigcity, EX (Hybrid)"
    assert "5+ years" in senior.jd_text
    assert "<p>" not in senior.jd_text
    assert senior.posted_at == "2026-05-10T12:00:00Z"


def test_lever_normalize():
    payload = json.loads((FIXTURES / "lever_sample.json").read_text())
    normalized = [lever.normalize(p) for p in payload]
    assert len(normalized) == 1
    staff = normalized[0]
    assert staff.title == "Staff Product Manager, Agents"
    assert staff.workplace_type == "remote"
    assert staff.location == "Remote - US"
    assert "6+ years" in staff.jd_text
    assert staff.posted_at and staff.posted_at.startswith("2025-")


def test_ashby_normalize():
    from job_finder.adapters import ashby

    jobs = json.loads((FIXTURES / "ashby_sample.json").read_text())
    normalized = [ashby.normalize(j, slug="exampleco") for j in jobs if j.get("isListed")]
    assert len(normalized) == 1
    p = normalized[0]
    assert p.title == "Senior Product Manager, Platform"
    assert p.workplace_type == "hybrid"
    assert p.location == "Farport, EX"
    assert "5+ years" in p.jd_text
    assert "<p>" not in p.jd_text
    assert p.posted_at == "2026-05-01"
    assert p.url == "https://jobs.ashbyhq.com/exampleco/abc-123"


def test_ashby_normalize_strips_utf8_bom():
    from job_finder.adapters import ashby

    bom = chr(0xfeff)
    job = {
        "id": "bom-1",
        "title": f"{bom}Senior Product Manager,{bom} Payments",
        "locationName": "Farport, EX",
        "workplaceType": "Hybrid",
        "descriptionHtml": f"{bom}<p>Lead{bom} our payments roadmap.</p>{bom}",
        "publishedDate": "2026-05-20",
        "isListed": True,
    }
    p = ashby.normalize(job, slug="acme")
    assert p.title == "Senior Product Manager, Payments"
    assert bom not in p.title
    assert p.jd_text is not None
    assert bom not in p.jd_text
    assert "Lead our payments roadmap." in p.jd_text
    p.jd_text.encode("ascii", errors="strict")


def test_workday_normalize():
    from job_finder.adapters import workday

    payload = json.loads((FIXTURES / "workday_list_sample.json").read_text())
    normalized = [workday.normalize(j, slug="exampleco/wd1/External")
                  for j in payload["jobPostings"]]
    assert len(normalized) == 3
    senior = normalized[0]
    assert senior.external_id == "R100001"
    assert senior.title == "Senior Product Manager, Connected Devices"
    assert senior.location == "Bigcity, EX"
    assert senior.url == ("https://exampleco.wd1.myworkdayjobs.com/External"
                          "/job/EX-Bigcity/Senior-Product-Manager--Connected-Devices_R100001")
    # The list payload has no JD; the detail_ref is what fetch_detail needs.
    assert senior.jd_text is None
    assert senior.detail_ref == "/job/EX-Bigcity/Senior-Product-Manager--Connected-Devices_R100001"
    assert normalized[1].workplace_type == "remote"
    # Empty bulletFields falls back to the req id in the path.
    assert normalized[2].external_id == "R100003"


def test_workday_slug_must_have_three_parts():
    import pytest

    from job_finder.adapters import workday

    with pytest.raises(ValueError, match="tenant/wdN/site"):
        workday.fetch("exampleco")


def test_workday_fetch_paginates(monkeypatch):
    import httpx

    from job_finder.adapters import workday

    payload = json.loads((FIXTURES / "workday_list_sample.json").read_text())
    monkeypatch.setattr(workday, "_PAGE_LIMIT", 2)
    pages = {0: {"total": 3, "jobPostings": payload["jobPostings"][:2]},
             2: {"total": 3, "jobPostings": payload["jobPostings"][2:]}}
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body["offset"])
        return httpx.Response(200, json=pages[body["offset"]])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    postings = workday.fetch("exampleco/wd1/External", client=client)
    assert calls == [0, 2]
    assert [p.external_id for p in postings] == ["R100001", "R100002", "R100003"]


def test_workday_fetch_detail():
    import httpx

    from job_finder.adapters import workday

    detail_payload = json.loads((FIXTURES / "workday_detail_sample.json").read_text())
    seen_urls = []

    def handler(request):
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=detail_payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ref = "/job/EX-Bigcity/Senior-Product-Manager--Connected-Devices_R100001"
    detail = workday.fetch_detail("exampleco/wd1/External", ref, client=client)
    assert seen_urls == [
        "https://exampleco.wd1.myworkdayjobs.com/wday/cxs/exampleco/External" + ref]
    assert "5+ years" in detail["jd_text"]
    assert "<p>" not in detail["jd_text"]
    assert detail["posted_at"] == "2026-08-01"


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
    assert bom not in p.title
    assert p.jd_text is not None
    assert bom not in p.jd_text
    p.jd_text.encode("ascii", errors="strict")
