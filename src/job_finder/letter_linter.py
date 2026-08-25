"""Deterministic checks on a drafted cover letter. Zero tokens, no LLM.

The `materials-fact-checker` reads the whole style guide and judges. This reads
a short list of patterns and cannot judge anything. Both exist because the
checker's measured failure mode is filing a real violation as NIT, and a pattern
match cannot reason its way down to NIT.

**This carries a subset of the style guide, never the whole of it.** The guide
named by `[paths].writing_style_path` is the authority; what is here is the part
that survives being written as a regex. A rule that needs judgment belongs to
the checker, not to this file.

Two severities:

- **CRITICAL** blocks. A flat ban with no legitimate exception: em-dashes, a
  paragraph opening on "I", an opening that announces a reaction, a feeling verb,
  a trope from the guide's §2, a closing that is not "Thanks,".
- **ADVISORY** never blocks. Patterns with real exceptions, where the value is a
  human glance rather than a verdict. Trailing-gloss candidates live here because
  "which is what started my search" is correct and matches the same shape.

The structural checks (paragraph chaining, whether the close returns to the
opening) are ADVISORY on purpose. They encode a procedure written on 2026-08-25
and validated against one letter; they collect signal until there is enough of it
to justify blocking on.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

CRITICAL = "CRITICAL"
ADVISORY = "ADVISORY"

EXIT_CLEAN = 0
EXIT_NOTHING = 3   # no letter to lint. Not a pass; an unattended caller must tell these apart.
EXIT_BLOCKED = 4   # at least one CRITICAL finding.

EM_DASH = "—"

# The guide's §2 list is longer and is the authority. These are the ones that
# survive as a literal match without catching honest usage.
AI_TROPES = (
    "uniquely positioned", "spearhead", "delve", "navigate the landscape",
    "cutting-edge", "seamless", "at the intersection of", "passionate about",
    "would love to connect", "would love the opportunity",
    "excited to explore", "hope this finds you well",
    "hope your week is off to a good start", "synergize", "best-in-class",
)

# Openings that announce a reaction instead of stating an observation. The defect
# takes new wording every time, so this list is a floor, not a definition: the
# structural rule is that sentence one carries a fact about the company.
REACTION_OPENERS = re.compile(
    r"\byour (posting|job posting|listing|ad)\b"
    r"|\bi (came across|stumbled|noticed|saw)\b"
    r"|\bi'?m reaching out\b"
    r"|\bi'?ve (long )?admired\b"
    r"|\bcaught my (eye|attention)\b"
    r"|\b(is|was) what got my attention\b"
    r"|\bthe part i keep coming back to\b",
    re.I,
)

FEELING_VERBS = re.compile(
    r"\bi(?:'m| am)? ?(?:am )?(excited|thrilled|passionate|eager|drawn)\b"
    r"|\bexcited (to|about|by)\b|\bthrilled (to|about|by)\b"
    r"|\bpassionate about\b|\bdrawn to\b|\bdrew me to\b",
    re.I,
)

# A relative clause restating the sentence it hangs off (epexegesis). Legitimate
# ones carry a new fact, so every hit here is a candidate for a human, never a
# verdict.
GLOSS = re.compile(r",\s+(which (?:is|means|was|would be)|meaning|that is)\b", re.I)

# Backward references that satisfy the known-new contract at a paragraph opening.
BACKREF = re.compile(
    r"\b(that|those|these|this|neither|both|none|it|they|there|then|since|"
    r"same|getting|doing so|before|after|instead|also|still|again)\b",
    re.I,
)

STOPWORDS = frozenset("""
a an and are as at be been before but by for from had has have how i if in into is it its
me my no not of on or our so than that the their them then there they this to us was we
were what when where which who will with would you your
""".split())


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    detail: str
    where: str

    def __str__(self) -> str:
        return f"  {self.severity:<8} {self.check:<22} {self.where}: {self.detail}"


def paragraphs(letter: dict[str, Any]) -> list[str]:
    return [p for p in letter.get("paragraphs", []) if str(p).strip()]


def sentences(text: str) -> list[str]:
    """Split on sentence-final punctuation followed by a capital.

    Naive by design. An abbreviation mid-sentence can split wrong; the checks
    that use this degrade to a false ADVISORY rather than a wrong CRITICAL.
    """
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def content_words(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 3}


def _flat(letter: dict[str, Any]) -> str:
    return "\n\n".join(paragraphs(letter))


def check_em_dash(letter: dict[str, Any]) -> list[Finding]:
    out = []
    for i, para in enumerate(paragraphs(letter), 1):
        if EM_DASH in para:
            out.append(Finding("em_dash", CRITICAL,
                               f"{para.count(EM_DASH)} em-dash(es)", f"para {i}"))
    return out


def check_paragraph_opening_i(letter: dict[str, Any]) -> list[Finding]:
    out = []
    for i, para in enumerate(paragraphs(letter), 1):
        first = re.match(r"\W*(\w+)", para)
        if first and first.group(1) == "I":
            out.append(Finding("paragraph_starts_with_i", CRITICAL,
                               f'opens "{para[:40]}..."', f"para {i}"))
    return out


def check_opening(letter: dict[str, Any]) -> list[Finding]:
    paras = paragraphs(letter)
    if not paras:
        return []
    first = sentences(paras[0])[0] if sentences(paras[0]) else paras[0]
    hit = REACTION_OPENERS.search(first)
    if hit:
        return [Finding("reaction_opener", CRITICAL,
                        f'sentence 1 announces a reaction ("{hit.group(0)}"); '
                        "it must carry a fact about the company", "para 1")]
    return []


def check_feeling_verbs(letter: dict[str, Any]) -> list[Finding]:
    out = []
    for i, para in enumerate(paragraphs(letter), 1):
        for hit in FEELING_VERBS.finditer(para):
            out.append(Finding("feeling_verb", CRITICAL,
                               f'"{hit.group(0)}": specificity carries it, not the word',
                               f"para {i}"))
    return out


def check_tropes(letter: dict[str, Any]) -> list[Finding]:
    out = []
    low = _flat(letter).lower()
    for trope in AI_TROPES:
        if trope in low:
            out.append(Finding("ai_trope", CRITICAL, f'"{trope}"', "body"))
    return out


def check_closing(letter: dict[str, Any]) -> list[Finding]:
    closing = str(letter.get("closing", "")).strip()
    if closing and closing.rstrip(",") != "Thanks":
        return [Finding("wrong_closing", CRITICAL,
                        f'"{closing}": the closing is always "Thanks,"', "closing")]
    return []


def check_gloss(letter: dict[str, Any]) -> list[Finding]:
    out = []
    for i, para in enumerate(paragraphs(letter), 1):
        for sent in sentences(para):
            hit = GLOSS.search(sent)
            if not hit:
                continue
            tail = sent[hit.start():].rstrip(".")
            out.append(Finding("gloss_candidate", ADVISORY,
                               f'"{tail[:70]}": delete it; if no fact is lost it was a gloss',
                               f"para {i}"))
    return out


# One word in common is coincidence; "work" appeared in two adjacent paragraphs
# of a letter that plainly had no transition. Two is a link.
MIN_SHARED_WORDS = 2

# How far into the opening sentence a backward reference still counts.
BACKREF_WINDOW = 5


def check_paragraph_chain(letter: dict[str, Any]) -> list[Finding]:
    """Paragraphs after the first should open on something the last one said.

    Comparing against the previous paragraph's final sentence alone was too
    strict: a real letter hands off to the paragraph's subject, not always to its
    last clause. Two shared content words, because one is coincidence.
    """
    out = []
    paras = paragraphs(letter)
    for i, para in enumerate(paras[1:], 2):
        opener = sentences(para)[0] if sentences(para) else para
        # A backward reference need not be the first word: "The work there is..."
        # points back as plainly as "That work is...".
        if BACKREF.search(" ".join(opener.split()[:BACKREF_WINDOW])):
            continue
        if len(content_words(opener) & content_words(paras[i - 2])) >= MIN_SHARED_WORDS:
            continue
        # The last paragraph's job is to return to the opening, not to continue
        # from the one before it, so reaching back that far counts as a link.
        if i == len(paras) and content_words(opener) & content_words(paras[0]):
            continue
        out.append(Finding("no_transition", ADVISORY,
                           f'opens on a fresh topic with no backward reference: "{opener[:60]}"',
                           f"para {i}"))
    return out


def check_close_returns(letter: dict[str, Any]) -> list[Finding]:
    """The last line should name something the first paragraph opened on."""
    paras = paragraphs(letter)
    if len(paras) < 2:
        return []
    opening = " ".join(sentences(paras[0])[:2])
    last = sentences(paras[-1])[-1] if sentences(paras[-1]) else paras[-1]
    if content_words(opening) & content_words(last):
        return []
    return [Finding("close_does_not_return", ADVISORY,
                    f'last line shares no subject with the opening: "{last[:60]}"',
                    f"para {len(paras)}")]


CHECKS = (
    check_em_dash, check_paragraph_opening_i, check_opening, check_feeling_verbs,
    check_tropes, check_closing, check_gloss, check_paragraph_chain,
    check_close_returns,
)


def lint(letter: dict[str, Any]) -> list[Finding]:
    return [f for check in CHECKS for f in check(letter)]


def load_letter(folder: Path) -> dict[str, Any] | None:
    path = folder / "cover_letter.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def find_folders(applications_dir: Path, date: str | None) -> list[Path]:
    if not applications_dir.is_dir():
        return []
    pattern = f"{date}_*" if date else "*"
    return sorted(p for p in applications_dir.glob(pattern)
                  if p.is_dir() and (p / "cover_letter.json").is_file())


def report(results: list[tuple[str, list[Finding]]], quiet: bool = False) -> int:
    blocked = False
    for name, findings in results:
        crit = [f for f in findings if f.severity == CRITICAL]
        adv = [f for f in findings if f.severity == ADVISORY]
        blocked = blocked or bool(crit)
        if quiet and not crit:
            continue
        status = "BLOCKED" if crit else ("clean" if not adv else "clean, with notes")
        print(f"\n{name}: {status}")
        for f in crit + adv:
            print(f)
    if not results:
        print("No cover_letter.json found. Nothing to lint.")
        return EXIT_NOTHING
    print()
    return EXIT_BLOCKED if blocked else EXIT_CLEAN


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--folder", type=Path, help="one per-application folder")
    ap.add_argument("--date", help="lint every folder rendered on YYYY-MM-DD")
    ap.add_argument("--applications-dir", type=Path,
                    help="override the configured render target")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the letters that block")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.folder:
        folders = [args.folder]
    else:
        root = args.applications_dir
        if root is None:
            from . import job_apply, settings
            root = job_apply.load_config(settings.require_profile()).applications_dir
        folders = find_folders(root, args.date)

    results = []
    for folder in folders:
        letter = load_letter(folder)
        if letter is None:
            continue
        results.append((folder.name, lint(letter)))
    return report(results, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
