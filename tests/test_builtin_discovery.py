"""Built In discovery: propose untracked companies, and only with a board that lists the role."""
from __future__ import annotations

import httpx
import pytest

from job_finder import builtin_discovery as bd
from job_finder import db, digest, eval_calibration, state

SITE = "https://www.builtinexample.com"
CONFIG = {"sites": [SITE], "category": "product-management", "max_age_days": 7, "max_pages": 5}


def _card(n: int, company: str, title: str, age: str) -> str:
    return f"""
    <div data-id="job-card" id="job-card-{n}">
      <a data-id="company-title" href="/company/x-{n}"><span>{company}</span></a>
      <h2><a data-id="job-card-title" href="/job/role/{n}">{title}</a></h2>
      <span class="fs-xs fw-bold bg-gray-01">{age}</span>
    </div>"""


PAGE_1 = "<html><body>" + "".join([
    _card(1, "Nimbus Freight", "Senior Product Manager, Routing", "2 Days Ago"),
    _card(2, "Relay", "Senior Product Manager, Payments", "Yesterday"),
    _card(3, "Tracked Widgets, Inc.", "Senior Product Manager", "3 Hours Ago"),
    _card(4, "Loomcraft", "Senior Product Designer", "1 Day Ago"),
]) + "</body></html>"

BOARDS = {
    "nimbusfreight": ["Senior Product Manager, Routing", "Dispatcher"],
    # A slug collision: a different company answers for "relay".
    "relay": ["Warehouse Associate", "Forklift Operator"],
}


def _handler(pages: dict[int, str], boards: dict[str, list[str]], fail_site: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.host == "www.builtinexample.com":
            if fail_site:
                return httpx.Response(503)
            return httpx.Response(200, text=pages.get(int(url.params.get("page", 1)), "<html></html>"))
        if url.host == "api.greenhouse.io":
            slug = url.path.split("/")[3]
            if slug in boards:
                return httpx.Response(200, json={"jobs": [{"title": t} for t in boards[slug]]})
            return httpx.Response(404)
        if url.host == "jobs.ashbyhq.com":
            return httpx.Response(200, json={"data": {"jobBoard": None}})
        return httpx.Response(404)
    return handler


def _run(tmp_path, **kw):
    state_db = tmp_path / "state.db"
    state.upsert_company({"name": "Tracked Widgets", "ats_provider": "greenhouse",
                          "ats_slug": "trackedwidgets"}, state_db)
    client = httpx.Client(transport=httpx.MockTransport(_handler({1: PAGE_1}, BOARDS, **kw)))
    stats = bd.run(state_db=state_db, client=client, today="2026-09-28", config=CONFIG,
                   page_pause=0, probe_pause=0)
    return state_db, client, stats


@pytest.mark.parametrize("label, days", [
    ("3 Hours Ago", 0), ("Reposted 12 Minutes Ago", 0), ("Yesterday", 1),
    ("Reposted Yesterday", 1), ("5 Days Ago", 5), ("One Month Ago", 30),
    ("Reposted 2 Months Ago", 60), ("Featured", None),
])
def test_parse_age_days(label, days):
    assert bd.parse_age_days(label) == days


def test_parse_listing_page_reads_company_title_url_and_age():
    rows = bd.parse_listing_page(PAGE_1, SITE)
    assert rows[0].company == "Nimbus Freight"
    assert rows[0].title == "Senior Product Manager, Routing"
    assert rows[0].url == f"{SITE}/job/role/1"
    assert rows[0].age_days == 2


def test_candidates_skip_tracked_companies_and_off_target_titles():
    rows = bd.parse_listing_page(PAGE_1, SITE)
    found = bd.candidates(rows, {bd.normalize_company("Tracked Widgets")})
    assert sorted(found) == ["Nimbus Freight", "Relay"]


def test_board_match_requires_the_role_seen_on_built_in():
    assert bd.board_match(["Senior Product Manager, Routing"],
                          ["Senior Product Manager, Routing"]) == "specific"
    assert bd.board_match(["Senior Product Manager, Routing (Remote)"],
                          ["Senior Product Manager, Routing"]) == "specific"
    assert bd.board_match(["Warehouse Associate"], ["Senior Product Manager, Payments"]) is None


def test_a_bare_level_and_role_noun_match_is_generic():
    assert bd.board_match(["Senior Product Manager"], ["Senior Product Manager"]) == "generic"
    assert bd.board_match(["Staff Product Manager", "Senior Product Manager, Routing"],
                          ["Staff Product Manager", "Senior Product Manager, Routing"]) == "specific"


def test_run_records_a_matching_board_as_pending_and_a_collision_as_no_board(tmp_path):
    state_db, client, stats = _run(tmp_path)
    rows = {d["name"]: d for d in state.list_discovered(db_path=state_db)}
    assert rows["Nimbus Freight"]["status"] == "pending"
    assert (rows["Nimbus Freight"]["ats_provider"], rows["Nimbus Freight"]["ats_slug"]) == (
        "greenhouse", "nimbusfreight")
    assert rows["Nimbus Freight"]["title_match"] == "specific"
    assert rows["Relay"]["status"] == "no_board"
    assert "Tracked Widgets, Inc." not in rows
    assert stats["pending"] == 1 and stats["no_board"] == 1 and stats["errors"] == []


def test_run_never_proposes_the_same_company_twice(tmp_path):
    state_db, client, _ = _run(tmp_path)
    again = bd.run(state_db=state_db, client=client, today="2026-10-05", config=CONFIG,
                   page_pause=0, probe_pause=0)
    assert again["candidates"] == 0


def test_run_reports_a_site_failure_without_recording_anything(tmp_path):
    state_db, _, stats = _run(tmp_path, fail_site=True)
    assert stats["errors"] and state.list_discovered(db_path=state_db) == []


def test_run_is_off_when_no_sites_are_configured(tmp_path):
    stats = bd.run(state_db=tmp_path / "state.db", config={**CONFIG, "sites": []})
    assert stats["sites"] == 0 and stats["candidates"] == 0


def test_promote_tracks_the_company_and_the_digest_stops_listing_it(tmp_path):
    state_db, _, _ = _run(tmp_path)
    jobs_db = tmp_path / "jobs.db"
    db.init_db(jobs_db)

    def render() -> str:
        return digest.render(target_date="2026-09-28", db_path=jobs_db,
                             digest_dir=tmp_path / "digests", state_db=state_db
                             ).read_text(encoding="utf-8")

    body = render()
    assert "## New companies to review (1)" in body
    assert "**Nimbus Freight** · greenhouse · 2 open roles" in body

    bd.promote("nimbus freight", db_path=state_db)
    tracked = {c["name"]: c for c in state.list_companies(state_db)}
    assert tracked["Nimbus Freight"]["ats_slug"] == "nimbusfreight"
    assert "## New companies to review (0)" in render()


def test_calibration_parser_does_not_read_the_new_section_as_queue_entries():
    body = "\n".join([
        "# Job Digest — 2026-09-28",
        "## Stretch queue — new (1)",
        "### [Score 9] Example Co — [Senior Product Manager](https://example.com/jobs/12345)",
        "- Domain: ai_agentic · Stage: growth · Comp $180K–$220K (posted)",
        "## New companies to review (1)",
        "- **Nimbus Freight** · greenhouse · 2 open roles · [Senior PM](https://example.com/j/9)",
        "- Domain: iot_edge · Stage: growth",
    ])
    entries = eval_calibration.parse_digest(body)
    assert len(entries) == 1
    assert entries[0]["domain_tags"] == ["ai_agentic"]
    assert entries[0]["stage"] == "growth"


def test_fetch_uses_built_ins_posted_date_filter_and_reads_to_an_empty_page():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        page = int(request.url.params["page"])
        return httpx.Response(200, text=PAGE_1 if page <= 2 else "<html></html>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = bd.fetch_listings(client, SITE, "product-management", max_age_days=5,
                                 max_pages=10, pause=0)
    assert [p["page"] for p in seen] == ["1", "2", "3"]
    assert all(p["daysSinceUpdated"] == "7" for p in seen)
    assert len(rows) == 8
