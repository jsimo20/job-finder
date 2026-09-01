"""Tests for the zero-token cover letter linter."""
from __future__ import annotations

import json

import pytest

from job_finder import letter_linter as L


CLEAN = {
    "closing": "Thanks,",
    "paragraphs": [
        "Most security companies make the trust case after someone is already a "
        "customer. The Directory makes it in public, first, which puts the weight "
        "on how the product feels before anyone has committed to anything. At "
        "Spectrum that weight lands on our consumer cybersecurity product.",
        "Neither of those is really a security problem. Both are onboarding "
        "problems, and onboarding is where most of my work has been.",
        "All of that is retention work under a different name. Analytiks is where "
        "I learned to see it that way.",
        "Getting to work on any of that means leaving Spectrum. I look forward "
        "to discussing this opportunity in greater detail with you.",
    ],
}


def severities(letter, check_name):
    return [f.severity for f in L.lint(letter) if f.check == check_name]


def test_the_reference_letter_has_no_critical_findings():
    assert [f for f in L.lint(CLEAN) if f.severity == L.CRITICAL] == []


def test_em_dash_is_critical():
    letter = {**CLEAN, "paragraphs": ["The move happened — and then the search."]}
    assert severities(letter, "em_dash") == [L.CRITICAL]


def test_paragraph_opening_on_i_is_critical():
    letter = {**CLEAN, "paragraphs": ["I led the launch of the platform."]}
    assert severities(letter, "paragraph_starts_with_i") == [L.CRITICAL]


def test_mid_paragraph_i_is_fine():
    """The rule bans "I" as the first word, not the pronoun."""
    letter = {**CLEAN, "paragraphs": ["At Spectrum I led the launch."]}
    assert severities(letter, "paragraph_starts_with_i") == []


def test_it_does_not_trip_on_words_beginning_with_i():
    letter = {**CLEAN, "paragraphs": ["Its onboarding is the interesting part."]}
    assert severities(letter, "paragraph_starts_with_i") == []


@pytest.mark.parametrize("opener", [
    "Your posting for the Experience role is what got my attention.",
    "I came across the Senior PM listing last week.",
    "The Directory is the part I keep coming back to.",
    "Chainguard's approach caught my eye immediately.",
])
def test_openings_that_announce_a_reaction_are_critical(opener):
    letter = {**CLEAN, "paragraphs": [opener + " The rest follows."]}
    assert severities(letter, "reaction_opener") == [L.CRITICAL]


def test_only_the_first_sentence_is_checked_for_the_opener():
    """A reaction mentioned later in the letter is not the defect."""
    letter = {**CLEAN, "paragraphs": [
        "Most security companies make the trust case late. What got my attention "
        "was the Directory doing it first."]}
    assert severities(letter, "reaction_opener") == []


@pytest.mark.parametrize("text", [
    "Excited to work on developer tooling.",
    "I am passionate about onboarding.",
    "What drew me to this was the platform work.",
])
def test_feeling_verbs_are_critical(text):
    letter = {**CLEAN, "paragraphs": [f"The Directory is public. {text}"]}
    assert L.CRITICAL in severities(letter, "feeling_verb")


def test_tropes_are_critical():
    letter = {**CLEAN, "paragraphs": ["My background is uniquely positioned for this."]}
    assert severities(letter, "ai_trope") == [L.CRITICAL]


def test_announcing_a_fact_up_front_is_critical():
    letter = {**CLEAN, "paragraphs": ["Worth saying up front that I haven't built one."]}
    assert severities(letter, "ai_trope") == [L.CRITICAL]


def test_a_banned_hedge_word_is_critical():
    letter = {**CLEAN, "paragraphs": ["I am mostly curious how you decide."]}
    assert severities(letter, "banned_word") == [L.CRITICAL]


def test_banned_words_match_whole_words_only():
    letter = {**CLEAN, "paragraphs": ["Most of my time goes to the platform."]}
    assert severities(letter, "banned_word") == []


def test_closing_must_be_thanks():
    assert severities({**CLEAN, "closing": "Best regards,"}, "wrong_closing") == [L.CRITICAL]
    assert severities({**CLEAN, "closing": "Thanks,"}, "wrong_closing") == []


def test_a_gloss_is_advisory_never_critical():
    """A relative clause carrying a new fact matches the same shape as a gloss."""
    letter = {**CLEAN, "paragraphs": [
        "Most companies do it late. Chainguard does it first, which is a harder "
        "place to earn it."]}
    assert severities(letter, "gloss_candidate") == [L.ADVISORY]


def test_a_legitimate_which_clause_still_reports_as_a_candidate():
    letter = {**CLEAN, "paragraphs": [
        "The Directory is public. Spectrum does not support remote work, which is "
        "what started my search."]}
    findings = [f for f in L.lint(letter) if f.check == "gloss_candidate"]
    assert findings and all(f.severity == L.ADVISORY for f in findings)


def test_a_paragraph_opening_on_a_fresh_topic_is_flagged():
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public.",
        "Skiing and cycling occupy most weekends now.",
    ]}
    assert severities(letter, "no_transition") == [L.ADVISORY]


def test_a_backward_reference_satisfies_the_chain():
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public.",
        "That is an onboarding problem more than a security one.",
    ]}
    assert severities(letter, "no_transition") == []


def test_a_shared_subject_also_satisfies_the_chain():
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public.",
        "That public trust case is unusual for the Directory before signup.",
    ]}
    assert severities(letter, "no_transition") == []


def test_one_word_in_common_is_not_a_transition():
    """"work" appeared in two adjacent paragraphs of a letter with no transition."""
    letter = {**CLEAN, "paragraphs": [
        "A vendor I work with directly powers the cybersecurity product.",
        "Most of my career has been onboarding and activation.",
        "A vendor powers the cybersecurity product, as noted.",
    ]}
    assert severities(letter, "no_transition") == [L.ADVISORY]


def test_the_fixed_final_line_passes():
    assert severities(CLEAN, "wrong_final_line") == []
    assert severities(CLEAN, "curiosity_close") == []


def test_any_other_final_line_blocks():
    letter = {**CLEAN, "paragraphs": [
        *CLEAN["paragraphs"][:-1],
        "Getting to work on any of that means leaving Spectrum. Happy to talk whenever.",
    ]}
    assert severities(letter, "wrong_final_line") == [L.CRITICAL]


def test_the_retired_curiosity_close_blocks():
    """The old rule asked for exactly this; it is now the violation."""
    letter = {**CLEAN, "paragraphs": [
        *CLEAN["paragraphs"][:-1],
        "Getting to work on any of that means leaving Spectrum. If we end up "
        "talking, I am curious how you are thinking about the Directory.",
    ]}
    found = severities(letter, "curiosity_close")
    assert found == [L.CRITICAL]


def test_a_curiosity_question_before_the_fixed_line_still_blocks():
    """Appending the required sentence must not launder the retired pattern."""
    letter = {**CLEAN, "paragraphs": [
        *CLEAN["paragraphs"][:-1],
        "I am curious how you are thinking about the Directory. I look forward to "
        "discussing this opportunity in greater detail with you.",
    ]}
    assert severities(letter, "wrong_final_line") == []
    assert severities(letter, "curiosity_close") == [L.CRITICAL]


def test_paragraph_chaining_never_blocks():
    """It encodes a young procedure, so it collects signal rather than gates."""
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public.",
        "Golf remains stubbornly difficult for me. I look forward to discussing "
        "this opportunity in greater detail with you.",
    ]}
    assert [f.code for f in L.lint(letter) if f.severity == L.CRITICAL] == []


def test_exit_codes(tmp_path, capsys):
    good = tmp_path / "2026-08-25_acme_pm"
    good.mkdir()
    (good / "cover_letter.json").write_text(json.dumps(CLEAN), encoding="utf-8")
    assert L.main(["--applications-dir", str(tmp_path), "--date", "2026-08-25"]) == L.EXIT_CLEAN

    bad = tmp_path / "2026-08-25_borealis_pm"
    bad.mkdir()
    (bad / "cover_letter.json").write_text(
        json.dumps({**CLEAN, "paragraphs": ["Your posting caught my eye."]}),
        encoding="utf-8")
    assert L.main(["--applications-dir", str(tmp_path), "--date", "2026-08-25"]) == L.EXIT_BLOCKED


def test_nothing_to_lint_is_not_a_pass(tmp_path):
    """An unattended caller cannot treat "no letter" the same as "letter is fine"."""
    assert L.main(["--applications-dir", str(tmp_path)]) == L.EXIT_NOTHING


def test_a_missing_folder_yields_nothing_rather_than_raising(tmp_path):
    assert L.main(["--applications-dir", str(tmp_path / "gone")]) == L.EXIT_NOTHING


def test_the_final_paragraph_may_reach_back_to_the_opening():
    """Its job is to return to the hook, not to continue from paragraph 3."""
    letter = {**CLEAN, "paragraphs": [
        "Meridian is turning carrier integrations into configuration.",
        "That configuration problem showed up at Cascade Freight first.",
        "If we end up talking, how far should configuration go for a partner?",
    ]}
    assert severities(letter, "no_transition") == []
