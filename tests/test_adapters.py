import json
import threading
import time
from pathlib import Path

import httpx

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


def test_ashby_normalize_is_the_brief_contract():
    """The board brief has no description or date; both come from fetch_detail."""
    from job_finder.adapters import ashby

    jobs = json.loads((FIXTURES / "ashby_sample.json").read_text())
    p = ashby.normalize(jobs[0], slug="exampleco")
    assert p.external_id == "abc-123"
    assert p.title == "Senior Product Manager, Platform"
    assert p.workplace_type == "hybrid"
    assert p.location == "Farport, EX"
    assert p.url == "https://jobs.ashbyhq.com/exampleco/abc-123"
    assert p.jd_text is None
    assert p.posted_at is None
    assert p.detail_ref == "abc-123"


def test_ashby_normalize_strips_utf8_bom_from_title():
    from job_finder.adapters import ashby

    bom = chr(0xfeff)
    p = ashby.normalize({
        "id": "bom-1",
        "title": f"{bom}Senior Product Manager,{bom} Payments",
        "locationName": "Farport, EX",
        "workplaceType": "Hybrid",
    }, slug="acme")
    assert p.title == "Senior Product Manager, Payments"
    assert bom not in p.title


def _ashby_client(monkeypatch, responder):
    """Route every Ashby GraphQL POST through responder(operationName, variables)."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["operationName"])
        return httpx.Response(200, json=responder(body["operationName"],
                                                  body["variables"]))

    monkeypatch.setattr("job_finder.adapters.ashby._MIN_INTERVAL", 0)
    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_ashby_fetch_costs_one_request_per_board(monkeypatch):
    """A 2-role board is one brief call, not one brief plus two details."""
    from job_finder.adapters import ashby

    jobs = json.loads((FIXTURES / "ashby_sample.json").read_text())
    briefs = [{k: j[k] for k in ("id", "title", "locationName", "workplaceType")}
              for j in jobs]
    client, calls = _ashby_client(
        monkeypatch,
        lambda op, v: {"data": {"jobBoard": {"jobPostings": briefs}}},
    )
    postings = ashby.fetch("exampleco", client=client)
    assert len(postings) == 2
    assert calls == ["ApiJobBoardWithTeams"]
    assert all(p.jd_text is None and p.detail_ref for p in postings)


def test_ashby_fetch_detail_returns_jd_and_date(monkeypatch):
    from job_finder.adapters import ashby

    bom = chr(0xfeff)
    job = json.loads((FIXTURES / "ashby_sample.json").read_text())[0]
    job = {**job, "descriptionHtml": f"{bom}<p>5+ years{bom} PM experience required.</p>",
           "compensationTierSummary": "$180K - $210K"}
    client, calls = _ashby_client(monkeypatch,
                                  lambda op, v: {"data": {"jobPosting": job}})
    detail = ashby.fetch_detail("exampleco", "abc-123", client=client)
    assert calls == ["JobPosting"]
    assert detail["posted_at"] == "2026-05-01"
    assert "Compensation: $180K - $210K" in detail["jd_text"]
    assert "5+ years" in detail["jd_text"]
    assert "<p>" not in detail["jd_text"]
    assert bom not in detail["jd_text"]


def test_ashby_fetch_detail_drops_a_posting_closed_between_passes(monkeypatch):
    from job_finder.adapters import ashby

    unlisted = json.loads((FIXTURES / "ashby_sample.json").read_text())[1]
    client, _ = _ashby_client(monkeypatch,
                              lambda op, v: {"data": {"jobPosting": unlisted}})
    assert ashby.fetch_detail("exampleco", "xyz-999", client=client) == {
        "jd_text": None, "posted_at": None}


def test_ashby_pacing_holds_across_threads(monkeypatch):
    """The floor is global. Unsynchronized, every worker read the same stamp,
    slept the same amount and fired together, which is what drew the 429s."""
    from job_finder.adapters import ashby

    interval = 0.05
    monkeypatch.setattr(ashby, "_MIN_INTERVAL", interval)
    monkeypatch.setattr(ashby, "_last_request_at", 0.0)

    starts: list[float] = []
    lock = threading.Lock()

    def worker():
        ashby._pace()
        with lock:
            starts.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    starts.sort()
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert len(gaps) == 7
    assert min(gaps) >= interval * 0.8, f"requests fired together: {gaps}"


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
