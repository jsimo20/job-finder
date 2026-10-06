import json
from datetime import datetime, timedelta, timezone

import pytest

from job_finder import db, extract, state, weekly


@pytest.fixture
def jobs_db(tmp_path):
    path = tmp_path / "jobs.db"
    db.init_db(path)
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO companies (id, name, ats_provider, ats_slug, added_at) "
            "VALUES (1, 'Example Co', 'greenhouse', 'exampleco', ?)", (db.now_iso(),))
        for pid, verdict, jd in ((10, "keep", "Senior role. 6+ years. $180,000-$220,000."),
                                 (11, "keep", None),
                                 (12, "discard:wrong_location", "Any text")):
            conn.execute(
                "INSERT INTO postings (id, company_id, external_id, title, url, jd_text, "
                "first_seen_at, last_seen_at, hard_filter_verdict) "
                "VALUES (?, 1, ?, 'Senior Product Manager', 'https://x/' || ?, ?, ?, ?, ?)",
                (pid, str(pid), str(pid), jd, db.now_iso(), db.now_iso(), verdict))
    return path


def test_export_writes_only_kept_postings_with_a_jd(jobs_db, tmp_path):
    out = tmp_path / "pending.jsonl"
    assert extract.export_pending(out, jobs_db) == 1
    task = json.loads(out.read_text(encoding="utf-8"))
    assert task["posting_id"] == 10
    assert task["company"] == "Example Co"
    assert "6+ years" in task["jd_text"]


def test_export_trims_the_jd_to_the_same_length_the_api_path_sends(jobs_db, tmp_path):
    with db.connect(jobs_db) as conn:
        conn.execute("UPDATE postings SET jd_text = ? WHERE id = 10", ("x" * 20000,))
    out = tmp_path / "pending.jsonl"
    extract.export_pending(out, jobs_db)
    assert len(json.loads(out.read_text())["jd_text"]) == extract.JD_CHARS


def test_import_stores_valid_lines_and_names_the_rest(jobs_db, tmp_path):
    answers = tmp_path / "answers.jsonl"
    answers.write_text("\n".join([
        json.dumps({"posting_id": 10, "yoe_required": 6, "comp_base_min": 180000,
                    "comp_base_max": 220000, "comp_source": "posted", "domain": ["ai_agentic"],
                    "company_stage": None, "people_management": False, "remote_ok": True,
                    "onsite_days_per_week": 9, "stretch_reason": None}),
        json.dumps({"posting_id": 12, "yoe_required": 1}),
        json.dumps({"posting_id": "10"}),
        "{not json",
        "",
    ]), encoding="utf-8")
    stats = extract.import_results(answers, jobs_db, model="session:test")
    assert stats["lines"] == 4
    assert stats["imported"] == 1
    assert stats["skipped"] == 3
    assert any("12 is not awaiting" in e for e in stats["errors_detail"])
    assert any("no integer posting_id" in e for e in stats["errors_detail"])
    assert any("not JSON" in e for e in stats["errors_detail"])
    with db.connect(jobs_db) as conn:
        row = conn.execute("SELECT * FROM extractions WHERE posting_id = 10").fetchone()
    assert row["remote_ok"] == 1
    assert row["onsite_days_per_week"] is None, "9 days is clamped like the API path"
    assert row["model"] == "session:test"
    assert json.loads(row["domain_tags"]) == ["ai_agentic"]


def test_import_refuses_a_second_answer_for_the_same_posting(jobs_db, tmp_path):
    answers = tmp_path / "answers.jsonl"
    answers.write_text(json.dumps({"posting_id": 10}) + "\n" + json.dumps({"posting_id": 10}),
                       encoding="utf-8")
    stats = extract.import_results(answers, jobs_db)
    assert stats["imported"] == 1 and stats["skipped"] == 1


def test_after_import_the_posting_is_no_longer_pending(jobs_db, tmp_path):
    answers = tmp_path / "answers.jsonl"
    answers.write_text(json.dumps({"posting_id": 10}), encoding="utf-8")
    extract.import_results(answers, jobs_db)
    assert extract.export_pending(tmp_path / "again.jsonl", jobs_db) == 0


def test_status_is_due_with_no_stamp_and_after_the_interval(tmp_path):
    sdb = tmp_path / "state.db"
    assert weekly.status(sdb)["due"] is True
    fresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state.set_meta(weekly.LAST_RUN_KEY, fresh, sdb)
    assert weekly.status(sdb)["due"] is False
    old = (datetime.now(timezone.utc) - timedelta(days=weekly.INTERVAL_DAYS)).isoformat(
        timespec="seconds")
    state.set_meta(weekly.LAST_RUN_KEY, old, sdb)
    assert weekly.status(sdb)["due"] is True


def test_finish_renders_a_digest_and_stamps_the_run(jobs_db, tmp_path):
    sdb = tmp_path / "state.db"
    # discover=False: the default scans the configured Built In sites over the network.
    out = weekly.finish(db_path=jobs_db, state_db=sdb, digest_dir=tmp_path / "digests",
                        discover=False)
    assert (tmp_path / "digests").exists()
    assert state.get_meta(weekly.LAST_RUN_KEY, sdb) == out["stamped"]
    assert weekly.status(sdb)["due"] is False


def test_prompt_subcommand_prints_the_extraction_instructions(capsys):
    assert weekly.main(["prompt"]) == 0
    assert "Return STRICT JSON only" in capsys.readouterr().out
