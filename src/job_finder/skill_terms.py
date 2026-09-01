"""Deterministic guard on the resume's skills section. Zero tokens, no LLM.

The `skill-term-mapper` agent decides whether a JD's vocabulary can stand in for
a skill already in the source pool. That is a judgment call and it stays with the
agent. This file checks the structure around the judgment, so an unattended batch
cannot drift:

- every term on the resume traces to the source pool, or to a recorded swap
- every swap replaces a pool term, never another swap's output
- every swap carries evidence, a justification, and >= 0.9 confidence

The third rule is the cheap one and the second is the one that matters.
Figma -> Lovable is defensible. Lovable -> "production React delivery" is
defensible *from Lovable*, and composing the two puts a claim on the resume that
nothing in the pool supports. Anchoring every swap to the pool makes that
impossible rather than unlikely.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MIN_CONFIDENCE = 0.9

CRITICAL = "CRITICAL"

_POOL_LINE = re.compile(r"^-\s+\*\*(?P<category>[^:*]+):?\*\*:?\s*(?P<terms>.+)$",
                        re.MULTILINE)
_POOL_SECTION = re.compile(
    r"\*\*The source pool[^*]*\*\*\s*(?P<body>(?:^-.*\n?)+)", re.MULTILINE)
# Split on commas that are not inside parentheses, so "LLM workflows (Claude,
# ChatGPT)" stays one item instead of three.
_TOP_LEVEL_COMMA = re.compile(r",(?![^(]*\))")


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    detail: str


def normalize(term: str) -> str:
    """Lowercase, punctuation-free, whitespace-collapsed."""
    return re.sub(r"[^a-z0-9]+", " ", (term or "").lower()).strip()


def parse_source_pool(text: str) -> dict[str, list[str]]:
    """Category -> terms, read from the claims-ground-truth source pool block."""
    section = _POOL_SECTION.search(text)
    body = section.group("body") if section else text
    pool: dict[str, list[str]] = {}
    for m in _POOL_LINE.finditer(body):
        terms = [t.strip() for t in _TOP_LEVEL_COMMA.split(m.group("terms"))]
        pool[m.group("category").strip()] = [t for t in terms if t]
    return pool


def pool_text(pool: dict[str, list[str]]) -> str:
    """One normalized haystack. Matching against this rather than against exact
    terms tolerates the pool's own phrasing ("rapid prototyping with Cursor")
    while still catching a word the pool never mentions."""
    return normalize(" ".join(t for terms in pool.values() for t in terms))


def split_terms(body: str) -> list[str]:
    """The terms a rendered skills line asserts, parentheticals included.

    "LLM-based workflows (Claude, ChatGPT)" asserts three things, and a swap can
    hide inside the parenthetical as easily as outside it.
    """
    out: list[str] = []
    for chunk in _TOP_LEVEL_COMMA.split(body):
        chunk = chunk.strip().rstrip(".")
        if not chunk:
            continue
        inner = re.search(r"\((?P<inner>[^)]*)\)", chunk)
        if inner:
            out.append(chunk[:inner.start()].strip())
            out.extend(p.strip() for p in inner.group("inner").split(",") if p.strip())
        else:
            out.append(chunk)
    # "and X" / "with X" are joiners in the rendered prose, not part of the term.
    cleaned = []
    for t in out:
        t = re.sub(r"^(?:and|with|or)\s+", "", t.strip(), flags=re.I).strip()
        if t:
            cleaned.append(t)
    return cleaned


@dataclass(frozen=True)
class Substitution:
    replaces: str       # the source-pool term this stands in for
    term: str           # what goes on the resume
    evidence: str       # the pool entry or ground-truth fact behind it
    confidence: float
    justification: str


def load_substitutions(path: Path) -> list[Substitution]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("substitutions", raw) if isinstance(raw, dict) else raw
    return [Substitution(replaces=i.get("replaces", ""), term=i.get("term", ""),
                         evidence=i.get("evidence", ""),
                         confidence=float(i.get("confidence", 0)),
                         justification=i.get("justification", ""))
            for i in items]


def check_substitutions(subs: Iterable[Substitution],
                        pool: dict[str, list[str]]) -> list[Finding]:
    haystack = pool_text(pool)
    out: list[Finding] = []
    for s in subs:
        if not s.term or not s.replaces:
            out.append(Finding("incomplete_substitution", CRITICAL,
                               f"a substitution is missing term or replaces: {s}"))
            continue
        # The anchor rule. `replaces` has to name something the pool actually
        # contains, so a chain of individually-plausible swaps cannot walk the
        # resume away from the ground truth.
        if normalize(s.replaces) not in haystack:
            out.append(Finding("unanchored_substitution", CRITICAL,
                               f'"{s.term}" replaces "{s.replaces}", which is not in '
                               "the source pool - a swap may only stand in for a real skill"))
        if s.confidence < MIN_CONFIDENCE:
            out.append(Finding("low_confidence", CRITICAL,
                               f'"{s.term}" is {s.confidence:.2f} confident, below '
                               f"{MIN_CONFIDENCE}"))
        if not s.justification.strip() or not s.evidence.strip():
            out.append(Finding("unjustified_substitution", CRITICAL,
                               f'"{s.term}" carries no evidence or justification'))
    return out


# Joiners and articles the rendered prose adds; they carry no claim.
_STOPWORDS = frozenset(
    "a an and or with the of for to in on at by using via as is are our my".split())


def check_skills(skills: Iterable[tuple[str, str]],
                 subs: Iterable[Substitution],
                 pool: dict[str, list[str]]) -> list[Finding]:
    """Every rendered term traces to the pool or to a recorded swap.

    Matching is word-level rather than whole-phrase. The pool stores
    "rapid prototyping with Cursor" while a resume renders "rapid prototyping
    with Lovable, Cursor, and Figma", so phrase equality reports the honest line
    as unsourced. What actually needs catching is foreign vocabulary
    ("Databricks", "assembly line optimization"), and an unknown word is exactly
    what that looks like.
    """
    haystack_words = set(pool_text(pool).split())
    allowed_words: set[str] = set()
    for s in subs:
        allowed_words.update(normalize(s.term).split())
    out: list[Finding] = []
    for category, body in skills:
        for term in split_terms(body):
            unknown = [w for w in normalize(term).split()
                       if w not in _STOPWORDS
                       and w not in haystack_words
                       and w not in allowed_words]
            if not unknown:
                continue
            out.append(Finding("unsourced_term", CRITICAL,
                               f'"{term}" (in {category}) uses '
                               f"{', '.join(repr(w) for w in unknown)}, not in the "
                               "source pool and with no recorded substitution"))
    return out


def verify(skills: Iterable[tuple[str, str]], subs: Iterable[Substitution],
           pool: dict[str, list[str]]) -> list[Finding]:
    subs = list(subs)
    return check_substitutions(subs, pool) + check_skills(skills, subs, pool)


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "skills: every term traces to the source pool or a recorded swap"
    return "\n".join(f"{f.severity} {f.check}: {f.detail}" for f in findings)


def substitution_note(subs: list[Substitution]) -> str:
    """The interview-prep half. A swapped term is a question someone may ask, so
    the folder records what was written and what it actually stands on."""
    if not subs:
        return "No skill terms were swapped for this application.\n"
    lines = ["# Skill terms swapped for this application", "",
             "Each line is a JD word written onto the resume in place of a skill "
             "already in the source pool. If asked about one in an interview, the "
             "honest answer is the evidence column.", ""]
    for s in subs:
        lines.append(f"- **{s.term}** stands in for *{s.replaces}* "
                     f"({s.confidence:.0%}) - {s.justification}")
        lines.append(f"  - evidence: {s.evidence}")
    return "\n".join(lines) + "\n"


def _main(argv: list[str] | None = None) -> int:
    """Check one application folder's skills against the pool and its swaps.

        python -m job_finder.skill_terms --folder <per-app folder>

    Exit 0 clean, 4 a critical violation, 3 nothing to check. 3 and 4 are
    separate because an unattended caller cannot act on "no resume here" and
    "this resume claims things it should not" the same way.
    """
    import argparse

    from .settings import load_profile

    ap = argparse.ArgumentParser(description="verify swapped resume skill terms")
    ap.add_argument("--folder", type=Path, required=True)
    ap.add_argument("--ground-truth", type=Path, default=None,
                    help="claims_ground_truth.md (default: from profile [paths])")
    args = ap.parse_args(argv)

    gt = args.ground_truth
    if gt is None:
        paths = (load_profile() or {}).get("paths", {})
        gt = Path(paths.get("claims_ground_truth_path")
                  or "profile/ai_skills/claims_ground_truth.md")
    if not gt.exists():
        print(f"no ground truth at {gt}")
        return 3

    skills_path = args.folder / "resume_skills.json"
    if not skills_path.exists():
        print(f"no resume_skills.json in {args.folder} - nothing to check")
        return 3

    pool = parse_source_pool(gt.read_text(encoding="utf-8"))
    skills = [(c, b) for c, b in json.loads(skills_path.read_text(encoding="utf-8"))]
    subs = load_substitutions(args.folder / "skill_substitutions.json")
    findings = verify(skills, subs, pool)
    print(format_findings(findings))
    return 4 if findings else 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_main())
