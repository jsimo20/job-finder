"""Tests for the scoring calibration eval (eval_calibration.py).

Every digest body here is synthetic: fictional companies, fictional geography,
fictional posting ids.
"""
from __future__ import annotations

from job_finder import eval_calibration as ec
from job_finder import state

DIGEST_A = """# Job Digest — 2026-06-01

## Main queue — new (2)
Sorted by score desc.

### [Score 15] Acme Robotics — [Senior Product Manager](https://example-ats.test/acme/jobs/111111)
- Fairview, ST (hybrid) · YOE 5 · Comp $200–240K
- Domain: ai_agentic, developer_platform · Stage: series_b_d_ai_native
- **[Apply →](https://example-ats.test/acme/jobs/111111)**

### [Score 9] Borealis Labs — [Product Manager, Platform](https://example-ats.test/borealis/jobs/222222)
- Remote (remote) · YOE 7 · Comp not posted
- Domain: developer_platform · Stage: public_new_ai_line
- **[Apply →](https://example-ats.test/borealis/jobs/222222)**

## Stretch queue — new (1)

### [Score 6] Cyngus Systems — [Group Product Manager](https://example-ats.test/cyngus/jobs/333333)
- Northport, ST (onsite) · YOE 10 · Comp not posted
- Domain: iot_edge · Stage: mega_corp_10k
- **[Apply →](https://example-ats.test/cyngus/jobs/333333)**

## Closed (1)

### [Score 20] Ghost Corp — [Should Not Be Parsed](https://example-ats.test/ghost/jobs/999999)
- Nowhere (remote) · YOE 5 · Comp not posted
- Domain: ai_agentic · Stage: seed_series_a

## Manual check (1)
- Dunder Industries — https://careers.dunder.test/

## Stats
- postings seen: 42
"""

DIGEST_B = """# Job Digest — 2026-06-08

## Main queue — carried forward (2)

### [Score 16] Acme Robotics — [Senior Product Manager](https://example-ats.test/acme/jobs/111111)
- Fairview, ST (hybrid) · YOE 5 · Comp $200–240K
- Domain: ai_agentic, developer_platform · Stage: series_b_d_ai_native
- **[Apply →](https://example-ats.test/acme/jobs/111111)**

### [Score 9] Borealis Labs — [Product Manager, Platform](https://example-ats.test/borealis/jobs/222222)
- Remote (remote) · YOE 7 · Comp not posted
- Domain: developer_platform · Stage: public_new_ai_line
- **[Apply →](https://example-ats.test/borealis/jobs/222222)**
"""


def _seed(tmp_path, digests, applications):
    db = tmp_path / "state.db"
    with state.connect(db) as conn:
        for date, body in digests:
            conn.execute("INSERT INTO digests (date, body, created_at) VALUES (?,?,?)",
                         (date, body, date))
        for app in applications:
            conn.execute(
                "INSERT INTO applied (external_id, company, title, url, applied_at, "
                "source) VALUES (?,?,?,?,?,?)",
                (app["external_id"], app["company"], app["title"], app.get("url"),
                 app["applied_at"], app.get("source", "test")))
    return db


def test_parse_digest_reads_queues_in_order_and_skips_non_queue_sections():
    entries = ec.parse_digest(DIGEST_A)
    assert [e["url"].rsplit("/", 1)[-1] for e in entries] == ["111111", "222222", "333333"]
    assert [e["rank"] for e in entries] == [1, 2, 3]
    assert [e["queue"] for e in entries] == ["main", "main", "stretch"]
    # Closed and Manual check entries carry no live score and must not be ranked.
    assert all("999999" not in e["url"] for e in entries)


def test_parse_digest_extracts_signals():
    first, second, third = ec.parse_digest(DIGEST_A)
    assert first["domain_tags"] == ["ai_agentic", "developer_platform"]
    assert first["stage"] == "series_b_d_ai_native"
    assert first["comp_posted"] is True
    assert second["comp_posted"] is False
    assert third["domain_tags"] == ["iot_edge"]
    # Stage slugs carry digits; a letters-only pattern silently truncated this.
    assert third["stage"] == "mega_corp_10k"


def test_parsed_stages_stay_inside_the_configured_vocabulary():
    from job_finder.taxonomy import STAGE_WEIGHTS
    stages = {e["stage"] for e in ec.parse_digest(DIGEST_A) if e["stage"]}
    assert stages and stages <= set(STAGE_WEIGHTS)


def test_parse_digest_tolerates_empty_digest():
    assert ec.parse_digest("# Job Digest — 2026-05-14\n\n## Stats\n") == []


def test_short_external_ids_never_match():
    """A 2-char id substring-matches most URLs, which would inflate every metric."""
    assert ec._matches("11", None, "https://example-ats.test/acme/jobs/111111") is False
    assert ec._matches("111111", None, "https://example-ats.test/acme/jobs/111111") is True


def test_url_match_ignores_trailing_slash():
    assert ec._matches(None, "https://example-ats.test/acme/jobs/111111/",
                       "https://example-ats.test/acme/jobs/111111") is True


def test_link_applications_picks_the_digest_that_triggered_the_application():
    digests = {"2026-06-01": ec.parse_digest(DIGEST_A),
               "2026-06-08": ec.parse_digest(DIGEST_B)}
    apps = [{"external_id": "111111", "company": "Acme Robotics", "title": "SPM",
             "url": None, "applied_at": "2026-06-09"}]
    linked, unlinked = ec.link_applications(digests, apps)
    assert not unlinked
    assert linked[0]["digest_date"] == "2026-06-08"
    assert linked[0]["score"] == 16
    assert linked[0]["date_fallback"] is False


def test_link_applications_flags_backfilled_dates():
    digests = {"2026-06-08": ec.parse_digest(DIGEST_B)}
    apps = [{"external_id": "111111", "company": "Acme Robotics", "title": "SPM",
             "url": None, "applied_at": "2026-05-01"}]
    linked, _ = ec.link_applications(digests, apps)
    assert linked[0]["date_fallback"] is True


def test_link_applications_separates_off_pipeline_applications():
    digests = {"2026-06-01": ec.parse_digest(DIGEST_A)}
    apps = [{"external_id": "444444", "company": "Elsewhere Inc", "title": "PM",
             "url": None, "applied_at": "2026-06-02"}]
    linked, unlinked = ec.link_applications(digests, apps)
    assert not linked and len(unlinked) == 1


def test_percentile_ranks_top_role_highest():
    digests = {"2026-06-01": ec.parse_digest(DIGEST_A)}
    apps = [{"external_id": "111111", "company": "Acme", "title": "SPM",
             "url": None, "applied_at": "2026-06-02"},
            {"external_id": "333333", "company": "Cyngus", "title": "GPM",
             "url": None, "applied_at": "2026-06-02"}]
    linked, _ = ec.link_applications(digests, apps)
    by_id = {a["external_id"]: a for a in linked}
    assert by_id["111111"]["percentile"] == 1.0
    assert by_id["333333"]["percentile"] == 0.0


def test_precision_at_k_uses_a_per_digest_chance_baseline():
    linked = [{"rank": 1, "digest_size": 10}, {"rank": 8, "digest_size": 10}]
    at_five = next(p for p in ec.precision_at_k(linked, ks=[5]) if p["k"] == 5)
    assert at_five["hits"] == 1
    assert at_five["chance"] == 0.5
    assert at_five["lift"] == 1.0


def test_precision_at_k_handles_k_larger_than_the_digest():
    linked = [{"rank": 2, "digest_size": 3}]
    at_ten = ec.precision_at_k(linked, ks=[10])[0]
    assert at_ten["chance"] == 1.0
    assert at_ten["lift"] == 1.0


def test_build_pool_keeps_the_latest_score_for_carried_roles():
    digests = {"2026-06-01": ec.parse_digest(DIGEST_A),
               "2026-06-08": ec.parse_digest(DIGEST_B)}
    pool = ec.build_pool(digests, [])
    acme = next(r for r in pool if "111111" in r["url"])
    assert acme["score"] == 16
    assert len(pool) == 3


def test_score_bands_and_signal_lift(tmp_path):
    db = _seed(tmp_path, [("2026-06-01", DIGEST_A), ("2026-06-08", DIGEST_B)],
               [{"external_id": "111111", "company": "Acme Robotics",
                 "title": "Senior Product Manager", "applied_at": "2026-06-09"}])
    result = ec.evaluate(db, min_support=1)
    assert result["pool"] == 3
    assert result["applications"] == 1

    bands = {b["band"]: b for b in result["bands"]}
    assert bands["13-16"]["applied"] == 1 and bands["13-16"]["n"] == 1
    assert bands["5-8"]["applied"] == 0

    signals = {s["signal"]: s for s in result["signals"]}
    # One of three pool roles applied to, so baseline is 1/3; ai_agentic is
    # carried only by that role, so it lifts to 3x.
    assert signals["domain:ai_agentic"]["lift"] == 3.0
    assert signals["domain:iot_edge"]["applied"] == 0


def test_signal_lift_respects_min_support():
    pool = [{"domain_tags": ["rare_tag"], "stage": None, "comp_posted": False,
             "queue": "main", "applied": True}]
    assert not [s for s in ec.signal_lift(pool, min_support=5)
                if s["signal"] == "domain:rare_tag"]
    assert [s for s in ec.signal_lift(pool, min_support=1)
            if s["signal"] == "domain:rare_tag"]


def test_parse_digest_recovers_the_comp_floor():
    first, second, _ = ec.parse_digest(DIGEST_A)
    assert first["comp_min"] == 200000
    assert second["comp_min"] is None


def test_bare_maximum_comp_is_not_read_as_a_floor():
    body = ("## Main queue — new (1)\n\n"
            "### [Score 5] Delta Works — [PM](https://example-ats.test/delta/jobs/555555)\n"
            "- Remote (remote) · YOE 5 · Comp ≤$190K\n")
    assert ec.parse_digest(body)[0]["comp_min"] is None


def _rescored(body):
    """Parse a digest, then restate each score as today's weights would compute it.

    The fixture bodies carry illustrative scores; pinning them to real weights
    would make these tests fail whenever config/pipeline.toml is reweighted,
    which is the very event under test.
    """
    entries = ec.parse_digest(body)
    for entry in entries:
        entry["score"] = ec.reconstruct_score(entry)
    return entries


def test_reconstruction_check_is_clean_when_weights_match():
    check = ec.reconstruction_check({"2026-06-01": _rescored(DIGEST_A)})
    assert check["drifted"] == 0 and check["rate"] == 1.0


def test_reconstruction_check_flags_a_stale_archived_score():
    """An archived score today's weights cannot reproduce means a reweight happened."""
    entries = _rescored(DIGEST_A)
    entries[0]["score"] += 3
    check = ec.reconstruction_check({"2026-06-01": entries})
    assert check["drifted"] == 1
    assert check["rate"] == 2 / 3
    assert check["last_drift_date"] == "2026-06-01"
    assert ("domain:ai_agentic", 1) in check["suspects"]


def test_evaluate_grades_an_empty_archive(tmp_path):
    db = _seed(tmp_path, [], [])
    result = ec.evaluate(db)
    assert result["grade"] == "F"
    assert result["linked"] == [] and result["pool"] == 0


def test_evaluate_grade_bands(tmp_path):
    db = _seed(tmp_path, [("2026-06-01", DIGEST_A)],
               [{"external_id": "111111", "company": "Acme Robotics",
                 "title": "Senior Product Manager", "applied_at": "2026-06-02"}])
    result = ec.evaluate(db, min_support=1)
    assert result["median_percentile"] == 1.0
    assert result["grade"] == "A"
