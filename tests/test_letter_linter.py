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
        "Sample Co that weight lands on our consumer cybersecurity product.",
        "Neither of those is really a security problem. Both are onboarding "
        "problems, and onboarding is where most of my work has been.",
        "All of that is retention work under a different name. Northwind is where "
        "I learned to see it that way.",
        "Getting to work on any of that means leaving Sample Co. I look forward "
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


def test_opening_a_paragraph_on_i_is_allowed():
    """The ban was removed 2026-09-28 at the user's instruction.

    It had been pushing every opener onto an abstraction or a demonstrative
    pronoun: 100% of the repo's 176 paragraph openers had a non-human subject,
    against 73% of his own reaching first person within six words.
    check_paragraph_opening_i was deleted with the rule. This test stands in its
    place so a later pass does not quietly reinstate either.
    """
    letter = {**CLEAN, "paragraphs": [
        "I built the smart home line from nothing.",
        "My requirements drove the platform and the portal partners log into.",
        "Following that, I took on the router firmware backlog.",
        "I look forward to discussing this opportunity in greater detail with you.",
    ]}
    assert [f for f in L.lint(letter) if f.severity == L.CRITICAL] == []
    assert not any(f.check == "paragraph_starts_with_i" for f in L.lint(letter))
    assert not hasattr(L, "check_paragraph_opening_i")


def test_first_person_openers_satisfy_the_narrator_check():
    """What replaced the ban: a floor, not a ceiling."""
    letter = {**CLEAN, "paragraphs": [
        "I built the smart home line from nothing.",
        "My requirements drove the platform and the portal partners log into.",
        "Following that, I took on the router firmware backlog.",
        "I look forward to discussing this opportunity in greater detail with you.",
    ]}
    assert severities(letter, "absent_narrator") == []


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
        "The Directory is public. Sample Co does not support remote work, which is "
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
        "Getting to work on any of that means leaving Sample Co. Happy to talk whenever.",
    ]}
    assert severities(letter, "wrong_final_line") == [L.CRITICAL]


def test_the_retired_curiosity_close_blocks():
    """The old rule asked for exactly this; it is now the violation."""
    letter = {**CLEAN, "paragraphs": [
        *CLEAN["paragraphs"][:-1],
        "Getting to work on any of that means leaving Sample Co. If we end up "
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


# --------------------------------------------------------------------------
# Guide §15: never name the gap.
#
# Every quoted string below went out in a real letter on 2026-09-27, under the
# rule this one replaced. They are the regression set: if the check stops
# catching one of these, the batch starts shipping it again.


@pytest.mark.parametrize("sentence", [
    "Trust and safety is not my background, though.",
    "Documents are not my domain, though.",
    "Consoles for infrastructure companies are not my background.",
    "I have not worked on content workflows, data rooms or e-signature.",
    "Live sport itself I have never worked on, and it matters here.",
    "Detection, enforcement, adversaries: none of those are things I have worked on.",
    "Verification is the gap in all of that.",
    "Proving who someone is is a different problem and I would be learning it.",
    "The nearest thing I have built is a portal, not a control plane.",
    "Eight years of product management is what the posting prefers.",
    "Live sport I have not done, and the posting asks for it directly.",
    "I have no background in detection systems.",
    "Red-teaming is not something I have done.",
])
def test_naming_the_gap_is_critical(sentence):
    """A sentence may trip more than one pattern; every hit must be CRITICAL."""
    letter = {**CLEAN, "paragraphs": [sentence]}
    found = severities(letter, "gap_disclaimer")
    assert found and set(found) == {L.CRITICAL}


@pytest.mark.parametrize("sentence", [
    "I have only about five years of product management.",
    "Most of what I know I know as a reader rather than a practitioner.",
    "I would rather say that plainly than pad it.",
])
def test_conceding_without_declaring_is_advisory(sentence):
    letter = {**CLEAN, "paragraphs": [sentence]}
    assert severities(letter, "gap_softener") == [L.ADVISORY]


@pytest.mark.parametrize("sentence", [
    # The standard logistics line. An early version of the check flagged this,
    # which would have blocked every letter that explains the move to Farport.
    "None of that is why we are in Farport.",
    "None of it explains Farport.",
    # Stating what he did do, in the shapes nearest the banned ones.
    "Device onboarding ran on OAuth 2.0 and OIDC, and the calls were mine.",
    "The product auto-enables, so an activation rate would have meant nothing.",
    "It is still Phase 1, so there are no results to point at yet.",
    "There was not much appetite for taking on Google, Apple and Amazon.",
    "I have never been more specific about scopes than on that flow.",
])
def test_honest_prose_is_not_flagged(sentence):
    letter = {**CLEAN, "paragraphs": [sentence]}
    assert severities(letter, "gap_disclaimer") == []
    assert severities(letter, "gap_softener") == []


def test_the_reference_letter_names_no_gap():
    assert severities(CLEAN, "gap_disclaimer") == []


def test_gap_disclaimer_reports_the_paragraph_it_found():
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public.",
        "Trust and safety is not my background, though.",
    ]}
    found = [f for f in L.lint(letter) if f.check == "gap_disclaimer"]
    assert len(found) == 1
    assert found[0].where == "para 2"


# --------------------------------------------------------------------------
# §14, positional half. The fixtures below are the gold pair from the HBR
# transitions guidance: the same claim, transitioned badly and well. They are
# here as an external standard rather than one drawn from the user's own letters,
# so the check is measured against someone else's judgement of good and bad.

HBR_FIRST = (
    "Some experts argue that focusing on individual actions to combat climate "
    "change takes the focus away from the collective action required to keep "
    "carbon levels from rising."
)
HBR_INEFFECTIVE = (
    "Change will not be effected, say some others, unless individual actions "
    "raise the necessary awareness."
)
HBR_EFFECTIVE = (
    "Other experts argue that individual actions are key to raising the "
    "awareness necessary to effect change."
)


def test_hbr_effective_transition_passes_both_chain_checks():
    letter = {**CLEAN, "paragraphs": [HBR_FIRST, HBR_EFFECTIVE]}
    assert severities(letter, "no_transition") == []
    assert severities(letter, "buried_link") == []


def test_hbr_ineffective_transition_is_caught():
    """The defect HBR names: old information buried behind new."""
    letter = {**CLEAN, "paragraphs": [HBR_FIRST, HBR_INEFFECTIVE]}
    assert severities(letter, "buried_link") == [L.ADVISORY]


def test_word_overlap_alone_cannot_tell_the_hbr_pair_apart():
    """Why check_known_new exists.

    Both HBR openers repeat "individual", "actions" and "change" from the
    sentence before, so check_paragraph_chain passes both. Position is the only
    thing separating them. If this test ever fails, the bag-of-words check got
    stricter and this one may be redundant.
    """
    for second in (HBR_INEFFECTIVE, HBR_EFFECTIVE):
        letter = {**CLEAN, "paragraphs": [HBR_FIRST, second]}
        assert severities(letter, "no_transition") == []


def test_repeating_a_key_noun_up_front_is_a_transition():
    """HBR's paragraph-level example: "household" carries across the break."""
    letter = {**CLEAN, "paragraphs": [
        "According to Annie Lowery, individual actions matter because household "
        "trends can shift values and bring more people into the fight.",
        "So what is an individual household supposed to do? I look forward to "
        "discussing this opportunity in greater detail with you.",
    ]}
    assert severities(letter, "no_transition") == []
    assert severities(letter, "buried_link") == []


def test_buried_link_never_blocks():
    """Like paragraph chaining, it collects signal rather than gating.

    Scoped to this check: the HBR fixture is not one of the user's letters, so it
    trips the fixed-final-line rule on its own account.
    """
    letter = {**CLEAN, "paragraphs": [HBR_FIRST, HBR_INEFFECTIVE]}
    assert set(severities(letter, "buried_link")) == {L.ADVISORY}


def test_buried_link_does_not_double_report_a_missing_transition():
    """An opener with no link at all is check_paragraph_chain's finding alone."""
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public.",
        "Golf remains stubbornly difficult for me.",
    ]}
    assert severities(letter, "no_transition") == [L.ADVISORY]
    assert severities(letter, "buried_link") == []


# --------------------------------------------------------------------------
# §16: no dramatic pivot, plus the narrator check that shares its root cause.
# The banned strings are ones Claude actually wrote in the 2026-09-27 batch and
# The user rejected on sight; the passing ones are the near-misses that must not be
# caught with them.


@pytest.mark.parametrize("opener", [
    "None of that is why I am writing.",
    "That work is not the reason I am applying.",
    "Nothing about that is why I am here.",
])
def test_disowning_the_writing_is_critical(opener):
    assert severities({**CLEAN, "paragraphs": [opener]}, "dramatic_pivot") == [L.CRITICAL]


@pytest.mark.parametrize("opener", [
    "That weight was never about speed.",
    "What changed was not speed.",
])
def test_negative_first_definition_is_advisory(opener):
    assert severities({**CLEAN, "paragraphs": [opener]}, "negative_first") == [L.ADVISORY]


@pytest.mark.parametrize("opener", [
    # §14's reinterpretation: the negation re-files the previous paragraph, so it
    # is load-bearing and stays. It is also the CLEAN fixture's own second opener.
    "Neither of those is really a security problem.",
    "None of it explains Farport.",
    "None of that arrived as a spec.",
    # The shapes the rule wants instead.
    "My degree was biochemistry.",
    "Following my time at Northwind, I transitioned to a small startup.",
    "By October of senior year I had worked out what I wanted.",
])
def test_legitimate_openers_are_not_pivots(opener):
    letter = {**CLEAN, "paragraphs": [opener]}
    assert severities(letter, "dramatic_pivot") == []
    assert severities(letter, "negative_first") == []


def test_the_reference_letter_has_no_pivot():
    assert severities(CLEAN, "dramatic_pivot") == []


def test_semantic_pivots_are_a_known_blind_spot():
    """The regex is lexical; these are not, and all five shipped in real letters.

    Every one of these opened paragraph 4 of a 2026-09-27 letter, ahead of the
    relocation line, and every one failed §16's delete test: strike it and the
    logistics sentence says everything the pair said. An earlier version of this
    file whitelisted the first as legitimate, which was wrong. They are recorded
    here so the blind spot is documented rather than mistaken for a clean pass;
    catching them needs the fact-checker or a human, not this file.
    """
    blind_spots = [
        "None of that is why we are in Farport.",
        "We did not move to Farport for any of it.",
        "We ended up here for a different reason entirely.",
        "Farport had nothing to do with any of that.",
        "Onboarding was not the only place.",
        "Recommendations are not the only thing I put in front of someone.",
    ]
    for opener in blind_spots:
        letter = {**CLEAN, "paragraphs": [opener]}
        assert severities(letter, "dramatic_pivot") == [], (
            f"{opener!r} now caught; move it into the CRITICAL parametrize above")


def test_narrator_absent_when_no_opener_reaches_first_person():
    """The measured failure: 176 of 176 openers had a non-human subject."""
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public.",
        "That weight lands on the consumer cybersecurity product.",
        "Those are onboarding problems at heart.",
        "Getting to work on any of that means leaving Sample Co. I look forward "
        "to discussing this opportunity in greater detail with you.",
    ]}
    assert severities(letter, "absent_narrator") == [L.ADVISORY]


def test_narrator_present_when_he_opens_his_own_paragraphs():
    """His own shapes: "My ...", and a short phrase that reaches him at once."""
    letter = {**CLEAN, "paragraphs": [
        "My name is Alex Sample, and the smart home line is where I started.",
        "Following that, I transitioned to the developer platform.",
        "Unfortunately, that left me arguing the case twice.",
        "Getting to work on any of that means leaving Sample Co. I look forward "
        "to discussing this opportunity in greater detail with you.",
    ]}
    assert severities(letter, "absent_narrator") == []


def test_narrator_check_never_blocks():
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public.",
        "That weight lands on the product.",
        "Those are onboarding problems.",
        "Getting to work on any of that means leaving Sample Co. I look forward "
        "to discussing this opportunity in greater detail with you.",
    ]}
    assert set(severities(letter, "absent_narrator")) == {L.ADVISORY}


# --------------------------------------------------------------------------
# §17. Only the length-variety half is machine-checkable; the rest (dangling
# modifiers, colon and semicolon structure) needs a human, and §17 says so.


def test_a_paragraph_of_uniformly_long_sentences_is_flagged():
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public before anyone has "
        "committed to anything at all, which puts the weight on how it feels. "
        "At Sample Co that weight lands on our consumer cybersecurity product, "
        "built with a third-party vendor I work with directly every week. Most "
        "of my time on it goes to how much security you can put in front of "
        "someone before they stop using the thing you are protecting entirely.",
    ]}
    assert severities(letter, "no_short_sentence") == [L.ADVISORY]


def test_one_short_sentence_satisfies_the_variety_check():
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public before anyone has committed "
        "to anything at all, which puts the weight on how it feels. At Sample Co "
        "that weight lands on our cybersecurity product. Most of my time goes to "
        "how much security you can put in front of someone before they stop using it.",
    ]}
    assert severities(letter, "no_short_sentence") == []


def test_variety_check_ignores_very_short_paragraphs():
    """Two sentences is not a rhythm problem worth reporting."""
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public before anyone has committed "
        "to anything, which puts the weight on how the product feels early on.",
        "At Sample Co that weight lands on the consumer cybersecurity product we "
        "built with a third-party vendor I work with directly every single week.",
    ]}
    assert severities(letter, "no_short_sentence") == []


def test_variety_check_never_blocks():
    letter = {**CLEAN, "paragraphs": [
        "The Directory makes the trust case in public before anyone has "
        "committed to anything at all, which puts the weight on how it feels. "
        "At Sample Co that weight lands on our consumer cybersecurity product, "
        "built with a third-party vendor I work with directly every week. Most "
        "of my time on it goes to how much security you can put in front of "
        "someone before they stop using the thing you are protecting entirely.",
    ]}
    assert set(severities(letter, "no_short_sentence")) == {L.ADVISORY}


def test_the_short_sentence_test_is_not_machine_checkable():
    """§17: logic stays, feeling goes. The linter cannot tell these apart.

    Both paragraphs end on a five-word sentence after a long one. The first adds
    a limiting fact and is correct; the second only makes its predecessor land
    harder and is a §3 violation. check_sentence_variety is silent on both,
    which is the intended behaviour, not a gap to close with a regex.
    """
    adds_logic = {**CLEAN, "paragraphs": [
        "Our traffic manager measures latency session by session on the router and "
        "recommends actions back to our operations teams, with output guardrails in "
        "front of the queue. It is still in beta."]}
    adds_feeling = {**CLEAN, "paragraphs": [
        "Our traffic manager measures latency session by session on the router and "
        "recommends actions back to our operations teams, with output guardrails in "
        "front of the queue. That is the work."]}
    for letter in (adds_logic, adds_feeling):
        assert severities(letter, "no_short_sentence") == []
