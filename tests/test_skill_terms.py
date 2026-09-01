"""Tests for the deterministic guard on swapped resume skill terms.

Ground truth is the synthetic pool in fixtures/skill_pool_sample.md; the real
profile is never read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_finder import skill_terms as S

FIXTURES = Path(__file__).parent / "fixtures"
POOL = S.parse_source_pool((FIXTURES / "skill_pool_sample.md").read_text(encoding="utf-8"))


def sub(term, replaces, *, confidence=0.95, evidence="pool: AI/LLM",
        justification="same capability under a different name"):
    return S.Substitution(replaces=replaces, term=term, evidence=evidence,
                          confidence=confidence, justification=justification)


def codes(findings):
    return sorted(f.check for f in findings)


def test_the_pool_parses_into_categories():
    assert set(POOL) == {"AI/LLM", "Strategy", "Analytics & data", "Platform"}
    assert "SQL" in POOL["Analytics & data"]
    # A parenthetical must not split into separate pool entries.
    assert "RAG (retrieval-augmented generation)" in POOL["AI/LLM"]


def test_terms_split_out_of_a_rendered_line_including_parentheticals():
    got = S.split_terms("LLM-based workflows (Claude, ChatGPT), SQL, and Tableau")
    assert got == ["LLM-based workflows", "Claude", "ChatGPT", "SQL", "Tableau"]


def test_pool_terms_pass_untouched():
    skills = [("Analytics & Data", "SQL, Python, Tableau, product experimentation")]
    assert S.verify(skills, [], POOL) == []


def test_a_foreign_skill_is_caught():
    """The failure the whole guard exists for."""
    skills = [("Operations", "assembly line optimization, factory throughput")]
    found = S.verify(skills, [], POOL)
    assert codes(found) == ["unsourced_term", "unsourced_term"]
    assert "assembly line optimization" in found[0].detail


def test_a_foreign_tool_hiding_in_a_parenthetical_is_caught():
    skills = [("Analytics", "product analytics (Tableau, Databricks)")]
    assert codes(S.verify(skills, [], POOL)) == ["unsourced_term"]


def test_a_recorded_swap_lets_the_jd_word_through():
    """Figma -> Lovable: a named tool the candidate has not used, standing in for
    one they have, which is the decision this system implements."""
    skills = [("AI Product", "rapid prototyping with Lovable, Cursor, and Figma")]
    subs = [sub("Lovable", "Figma", evidence="pool: rapid prototyping with Cursor, Kiro, Figma",
                justification="AI-driven UI design and prototyping tool of the same class")]
    assert S.verify(skills, subs, POOL) == []


def test_a_capability_phrase_swap_passes():
    skills = [("Strategy", "creating PRDs, roadmap creation, product vision")]
    subs = [sub("creating PRDs", "writing requirements", evidence="pool: writing requirements")]
    assert S.verify(skills, subs, POOL) == []


def test_a_swap_below_the_confidence_bar_blocks():
    subs = [sub("Databricks", "SQL", confidence=0.7)]
    assert "low_confidence" in codes(S.check_substitutions(subs, POOL))


def test_a_swap_with_no_evidence_or_justification_blocks():
    assert "unjustified_substitution" in codes(
        S.check_substitutions([sub("Amplitude", "Tableau", evidence="")], POOL))
    assert "unjustified_substitution" in codes(
        S.check_substitutions([sub("Amplitude", "Tableau", justification="  ")], POOL))


def test_a_swap_must_replace_a_pool_term_not_another_swap():
    """The anti-drift rule. Figma -> Lovable is defensible; Lovable -> 'production
    React delivery' is defensible from Lovable, and the chain lands somewhere the
    pool never supported."""
    subs = [
        sub("Lovable", "Figma"),
        sub("production React delivery", "Lovable"),
    ]
    found = S.check_substitutions(subs, POOL)
    assert codes(found) == ["unanchored_substitution"]
    assert "production React delivery" in found[0].detail


def test_an_incomplete_substitution_record_blocks():
    subs = [S.Substitution(replaces="", term="Lovable", evidence="e",
                           confidence=0.95, justification="j")]
    assert codes(S.check_substitutions(subs, POOL)) == ["incomplete_substitution"]


def test_load_substitutions_accepts_both_shapes(tmp_path):
    payload = [{"replaces": "Figma", "term": "Lovable", "evidence": "e",
                "confidence": 0.95, "justification": "j"}]
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"substitutions": payload}), encoding="utf-8")
    b = tmp_path / "b.json"
    b.write_text(json.dumps(payload), encoding="utf-8")
    assert S.load_substitutions(a) == S.load_substitutions(b)
    assert S.load_substitutions(tmp_path / "absent.json") == []


def test_the_note_names_what_each_swap_stands_on():
    """A swapped tool is a question someone may ask, so the folder answers it."""
    note = S.substitution_note([sub("Lovable", "Figma",
                                    evidence="pool: rapid prototyping with Cursor, Kiro, Figma",
                                    justification="same class of AI UI prototyping tool")])
    assert "Lovable" in note and "Figma" in note
    assert "same class of AI UI prototyping tool" in note
    assert "evidence:" in note


def test_the_note_is_explicit_when_nothing_was_swapped():
    assert "No skill terms were swapped" in S.substitution_note([])
