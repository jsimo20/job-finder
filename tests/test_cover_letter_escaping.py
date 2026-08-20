"""Ampersand handling in the cover letter renderer.

RESUME_DATA strings are pre-escaped for ReportLab ("AI &amp; Platforms").
Reusing one as the cover letter's title_subtitle used to double-escape it and
print a literal "&amp;" in the header.
"""
from __future__ import annotations

import re

import pytest

from job_finder.job_apply import esc_amp


def test_bare_ampersand_is_escaped():
    assert esc_amp("Growth & Platforms") == "Growth &amp; Platforms"


def test_existing_entity_is_left_alone():
    assert esc_amp("Growth &amp; Platforms") == "Growth &amp; Platforms"


def test_mixed_bare_and_escaped():
    assert esc_amp("A & B &amp; C") == "A &amp; B &amp; C"


@pytest.mark.parametrize("entity", ["&amp;", "&middot;", "&rarr;", "&times;", "&#8212;", "&#x2014;"])
def test_known_entities_survive_unchanged(entity):
    assert esc_amp(f"x {entity} y") == f"x {entity} y"


def test_ampersand_before_non_entity_text_is_escaped():
    # "& more" and "&123" are not entities; both must be escaped.
    assert esc_amp("R&D") == "R&amp;D"
    assert esc_amp("tom & jerry") == "tom &amp; jerry"
    assert esc_amp("&123") == "&amp;123"


def test_idempotent():
    once = esc_amp("Growth & Platforms")
    assert esc_amp(once) == once


def test_no_output_contains_double_escaped_entity():
    for src in ["A & B", "A &amp; B", "A &amp;amp; B"]:
        out = esc_amp(src)
        assert "&amp;amp;" not in out or src.count("&amp;amp;") == 1
        assert not re.search(r"&amp;(?=amp;)", esc_amp("A &amp; B"))
