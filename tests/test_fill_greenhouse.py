"""Tests for the deterministic Greenhouse filler.

Browser-free: these cover argument pairing in batch mode. The fill itself is
exercised against live forms.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright", reason="fill_greenhouse needs the [apply] extra")

from boston_pm_tracker import fill_greenhouse as fg  # noqa: E402


# The two options Agero's sponsorship dropdown actually offers. Both contain
# "no" as a substring — in "not" and in "now" — which is what made the old
# first-substring-wins matcher answer that James requires visa sponsorship.
AGERO_SPONSORSHIP = [
    "i require sponsorship now or in the future.",
    "i do not require sponsorship.",
]


# The options Agero's sponsorship dropdown ACTUALLY offers, read out of the
# captured audit manifest. Note there is no "I do not require sponsorship"
# option at all: the correct answer is phrased as a positive authorization
# statement, which is why every negation candidate missed and a bare "no"
# resolved cleanly and uniquely to the wrong option through "now".
AGERO_REAL = [
    "i am legally authorized to work in this country for any employer.",
    "i require sponsorship now or in the future.",
]


def test_bare_no_matches_the_wrong_agero_option_uniquely():
    # Documents WHY the ambiguity guard alone was not enough: this is a clean,
    # unambiguous match onto the answer that must never be given.
    assert fg.match_option(AGERO_REAL, "no") == 1


def test_sponsorship_veto_covers_the_wrong_agero_option():
    veto = fg.veto_for("Will you now or in the future require sponsorship for employment VISA status")
    assert veto is not None
    import re as _re
    assert _re.search(veto, AGERO_REAL[1], _re.I), "must veto the requires-sponsorship option"
    assert not _re.search(veto, AGERO_REAL[0], _re.I), "must not veto the authorized option"


def test_sponsorship_veto_allows_a_plain_negation():
    veto = fg.veto_for("Do you require sponsorship?")
    import re as _re
    assert not _re.search(veto, "i do not require sponsorship.", _re.I)


def test_authorized_candidate_resolves_the_real_agero_options():
    cands = next(c for pat, c in fg.COMBO_FIELDS if pat == r"sponsor")
    assert fg.match_option(AGERO_REAL, cands[0]) == 0


def test_bare_no_is_ambiguous_against_agero_sponsorship():
    # Must refuse rather than guess: picking wrong here is unrecoverable.
    assert fg.match_option(AGERO_SPONSORSHIP, "no") is None


def test_specific_candidate_resolves_agero_sponsorship():
    idx = fg.match_option(AGERO_SPONSORSHIP, "do not require sponsorship")
    assert idx == 1


def test_sponsorship_candidates_are_ordered_specific_first():
    # Ordering is load-bearing. "no" must stay last: on Agero's real options it
    # matches uniquely and wrongly, so anything specific has to be tried first.
    cands = next(c for pat, c in fg.COMBO_FIELDS if pat == r"sponsor")
    assert cands[0] == "legally authorized to work"
    assert "do not require sponsorship" in cands
    assert cands[-1] == "no"


def test_exact_match_beats_substring():
    assert fg.match_option(["male", "female"], "male") == 0


def test_whole_word_beats_substring():
    # "no" should not reach the substring tier when a whole-word option exists.
    assert fg.match_option(["no", "i know the founder"], "no") == 0


def test_duplicate_matches_at_same_tier_refuse():
    assert fg.match_option(["yes, remote", "yes, hybrid"], "yes") is None


def test_no_match_returns_none():
    assert fg.match_option(["alpha", "beta"], "gamma") is None


@pytest.mark.parametrize("label", [
    "If Referred by an Agero Employee, please indicate their first and last name.",
    "Emergency contact last name",
    "Referred by (first and last name)",
    "Your manager's name",
])
def test_name_traps_are_not_autofilled(label):
    assert fg.NAME_TRAP_PATTERN.search(label)


@pytest.mark.parametrize("label", ["First Name*", "Last Name", "Preferred First Name"])
def test_real_name_fields_are_not_trapped(label):
    assert fg.NAME_TRAP_PATTERN.search(label) is None


def _main(argv, monkeypatch):
    monkeypatch.setattr("sys.argv", ["fill_greenhouse", *argv])
    return fg.main()


def test_mismatched_url_and_folder_counts_exit(monkeypatch, capsys):
    # Silent misalignment here would fill one role's form with another's PDFs.
    with pytest.raises(SystemExit):
        _main(["--url", "a", "--url", "b", "--folder", "x"], monkeypatch)
    assert "one --folder per --url" in capsys.readouterr().err


def test_slug_must_be_repeated_per_url(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        _main(["--url", "a", "--url", "b", "--folder", "x", "--folder", "y",
               "--slug", "only-one"], monkeypatch)
    assert "repeated once per --url" in capsys.readouterr().err


def test_shot_rejected_in_batch_mode(monkeypatch, capsys):
    # --shot is a single file path, so it cannot mean anything for N tabs.
    with pytest.raises(SystemExit):
        _main(["--url", "a", "--url", "b", "--folder", "x", "--folder", "y",
               "--shot", "out.png"], monkeypatch)
    assert "omit it in batch mode" in capsys.readouterr().err


class _FakeEl:
    """Minimal stand-in for a Playwright file input."""
    def __init__(self, *, accepts=True, keeps=True):
        self.accepts, self.keeps, self.calls = accepts, keeps, 0

    def set_input_files(self, path, timeout=None):
        self.calls += 1
        if not self.accepts:
            raise RuntimeError("Timeout")

    def evaluate(self, _js):
        return self.keeps


def _blank_report():
    return {"filled": [], "skipped": [], "unmapped": [], "required_empty": [], "audits": []}


def test_upload_reported_only_when_it_actually_attached(tmp_path):
    pdf = tmp_path / "Sample_User_Resume_x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    r = _blank_report()
    assert fg._try_upload(_FakeEl(), pdf, "Resume", r) is True
    assert any("Resume upload" in line for line in r["filled"])


def test_upload_that_does_not_stick_is_not_reported_as_filled(tmp_path):
    # The 2026-07-27 failure: set_input_files returned cleanly, the file never
    # attached, and four applications reported a resume they did not have.
    pdf = tmp_path / "Sample_User_Resume_x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    r = _blank_report()
    assert fg._try_upload(_FakeEl(keeps=False), pdf, "Resume", r) is False
    assert r["filled"] == []
    assert any("did not stick" in line for line in r["unmapped"])


def test_upload_that_raises_is_caught_and_reported(tmp_path):
    pdf = tmp_path / "Sample_User_Resume_x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    r = _blank_report()
    assert fg._try_upload(_FakeEl(accepts=False), pdf, "Resume", r) is False
    assert r["filled"] == []
    assert any("failed" in line for line in r["unmapped"])
