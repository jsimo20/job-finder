from __future__ import annotations

import httpx

from job_finder import ats_probe as discover


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_reports_every_provider_and_ranks_the_busier_board_first():
    """A company that moved ATS but left a stale board up must not report the stale one."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "greenhouse" in url and "/boards/exampleco/" in url:
            return httpx.Response(200, json={"jobs": [{"id": 1}]})
        if "ashbyhq" in url and b'"exampleco"' in request.content:
            posts = [{"id": str(i), "title": "t"} for i in range(40)]
            return httpx.Response(200, json={"data": {"jobBoard": {"jobPostings": posts}}})
        if "ashbyhq" in url:
            return httpx.Response(200, json={"data": {"jobBoard": None}})
        return httpx.Response(404)

    with _client(handler) as client:
        hits, errors = discover.probe_name(client, "ExampleCo", pause=0)

    assert errors == []
    assert [(h["provider"], h["count"]) for h in hits] == [("ashby", 40), ("greenhouse", 1)]


def test_a_failed_request_is_an_error_not_a_missing_board():
    def handler(request: httpx.Request) -> httpx.Response:
        if "greenhouse" in str(request.url):
            raise httpx.ConnectTimeout("timed out", request=request)
        if "ashbyhq" in str(request.url):
            return httpx.Response(200, json={"data": {"jobBoard": None}})
        return httpx.Response(404)

    with _client(handler) as client:
        hits, errors = discover.probe_name(client, "ExampleCo", pause=0)

    assert hits == []
    assert errors and all(e.startswith("greenhouse:") for e in errors)


def test_a_server_error_is_an_error_not_a_missing_board():
    def handler(request: httpx.Request) -> httpx.Response:
        if "lever" in str(request.url):
            return httpx.Response(503)
        if "ashbyhq" in str(request.url):
            return httpx.Response(200, json={"data": {"jobBoard": None}})
        return httpx.Response(404)

    with _client(handler) as client:
        hits, errors = discover.probe_name(client, "ExampleCo", pause=0)

    assert hits == []
    assert errors and all(e.startswith("lever:") for e in errors)
