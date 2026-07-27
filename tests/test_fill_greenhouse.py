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


def test_bare_no_is_ambiguous_against_agero_sponsorship():
    # Must refuse rather than guess: picking wrong here is unrecoverable.
    assert fg.match_option(AGERO_SPONSORSHIP, "no") is None


def test_specific_candidate_resolves_agero_sponsorship():
    idx = fg.match_option(AGERO_SPONSORSHIP, "do not require sponsorship")
    assert idx == 1


def test_sponsorship_candidates_are_ordered_specific_first():
    # Ordering is load-bearing: "no" first would hit the ambiguous path and the
    # field would be left blank on every sentence-phrased form.
    cands = next(c for pat, c in fg.COMBO_FIELDS if pat == r"sponsor")
    assert cands[0] == "do not require sponsorship"
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
