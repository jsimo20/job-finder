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

- **CRITICAL** blocks. A flat ban with no legitimate exception: em-dashes, an
  opening that announces a reaction, a feeling verb,
  a trope from the guide's §2, a banned hedge word, a sentence whose content is
  the absence of experience (§15), a closing that is not "Thanks,", a final
  sentence that is not the fixed one.
- **ADVISORY** never blocks. Patterns with real exceptions, where the value is a
  human glance rather than a verdict. Trailing-gloss candidates live here because
  "which is what started my search" is correct and matches the same shape.

Paragraph chaining is ADVISORY on purpose. It encodes a procedure written on
2026-08-25 and validated against one letter; it collects signal until there is
enough of it to justify blocking on. The closing is not in that category: the
final sentence is fixed text, so there is nothing to weigh.
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
    "worth saying up front", "worth naming up front", "worth noting up front",
)

# Whole-word bans from the guide's §2. Substring matching would be wrong here:
# "mostly" must not catch a containing word, so these match on word boundaries.
BANNED_WORDS = ("mostly",)

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


def check_banned_words(letter: dict[str, Any]) -> list[Finding]:
    out = []
    for i, para in enumerate(paragraphs(letter), 1):
        for word in BANNED_WORDS:
            for _ in re.finditer(rf"\b{word}\b", para, re.I):
                out.append(Finding("banned_word", CRITICAL,
                                   f'"{word}": cut it or commit to the statement',
                                   f"para {i}"))
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


FINAL_LINE = "I look forward to discussing this opportunity in greater detail with you."

# The close this replaced: one line naming the hook and asking a real question.
# Across a stack of letters it was the tell, so it is now a violation rather than
# the target.
CURIOSITY_CLOSE = re.compile(
    r"\bi(?:'m| am)? curious\b"
    r"|\bif we end up talking\b"
    r"|\bcurious (?:how|what|whether|where|why)\b",
    re.I,
)


def check_final_line(letter: dict[str, Any]) -> list[Finding]:
    """The letter ends on one fixed sentence, verbatim, and nothing follows it."""
    paras = paragraphs(letter)
    if not paras:
        return []
    last_para = paras[-1]
    said = sentences(last_para)
    last = said[-1] if said else last_para
    out: list[Finding] = []
    if last.strip().rstrip(".") != FINAL_LINE.rstrip("."):
        out.append(Finding("wrong_final_line", CRITICAL,
                           f'the last sentence must be "{FINAL_LINE}", not "{last[:60]}"',
                           f"para {len(paras)}"))
    if match := CURIOSITY_CLOSE.search(last_para):
        out.append(Finding("curiosity_close", CRITICAL,
                           f'"{match.group(0)}": the closing question pattern is retired',
                           f"para {len(paras)}"))
    return out



# ---------------------------------------------------------------------------
# Guide §15: never name the gap.
#
# Added 2026-09-28, replacing the opposite rule. "Name the disqualifying gap in
# paragraph 1, then drop it" was a confirmed improvement over burying it, and it
# shipped in five letters before the user called it: the reader has the resume and
# the posting, finds the delta without help, and owns the decision about whether
# it matters. The sentence only spends the strongest paragraph on the weakest
# fact.
#
# These are CRITICAL rather than ADVISORY because the ban is flat. A cover letter
# has no legitimate use for a sentence whose content is the absence of
# experience. The carve-out in the guide is for a direct question on a form, and
# a form answer that must state a shortfall states it as a fact ("five years")
# rather than in any of these shapes.
GAP_DISCLAIMERS = (
    (re.compile(r"\b(?:is|are|was|were)\s+not\s+(?:my|his)\s+"
                r"(?:background|domain|area|field|world|strong\s+suit|thing)\b", re.I),
     "declares a domain is not his background"),
    (re.compile(r"\b(?:I|he)\s+(?:have|has|had)\s+(?:never|not)\s+"
                r"(?:worked|done|built|shipped|touched|led|owned)\b", re.I),
     "declares work he has not done"),
    (re.compile(r"\b(?:I|he)\s+(?:have|has)\s+(?:no|zero)\s+"
                r"(?:background|experience|exposure)\b", re.I),
     "declares an absence of experience"),
    (re.compile(r"\bnone\s+of\s+(?:those|these|them|that|it)\s+(?:are|is|were)\s+"
                r"(?:things|something|areas|work|experience)\b", re.I),
     "lists things he has not worked on"),
    (re.compile(r"\bnot\s+something\s+(?:I|he)\s+(?:have|has|'ve)\b", re.I),
     "declares work he has not done"),
    (re.compile(r"\b(?:I|he)\s+(?:would|'d|will)\s+be\s+learning\b", re.I),
     "concedes a part of the role as unlearned"),
    (re.compile(r"\b(?:is|are|was|remains)\s+the\s+gap\b", re.I),
     "names the gap outright"),
    (re.compile(r"\bthe\s+nearest\s+thing\s+(?:I|he)\b", re.I),
     "frames real work as a substandard substitute for the gap"),
    (re.compile(r"\bwhat\s+the\s+posting\s+(?:prefers|asks\s+for|wants|requires)\b", re.I),
     "measures him against a stated requirement"),
    (re.compile(r"\bthe\s+posting\s+asks\s+for\s+(?:it|that|them|this)\s+directly\b", re.I),
     "measures him against a stated requirement"),
)

# Shapes that concede without quite declaring. Real prose reaches for these
# honestly often enough that a human glance beats a verdict.
GAP_SOFTENERS = (
    (re.compile(r"\b(?:only|just)\s+about\s+"
                r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+years?\b", re.I),
     "understates tenure"),
    (re.compile(r"\bas\s+a\s+reader\s+(?:rather|more)\s+than\b", re.I),
     "concedes the knowledge is secondhand"),
    (re.compile(r"\b(?:than|instead\s+of)\s+pad(?:ding)?\s+it\b", re.I),
     "announces he is not padding, which raises the thing he is not padding"),
)


def check_gap_disclaimer(letter: dict[str, Any]) -> list[Finding]:
    """§15: no sentence whose content is the absence of experience."""
    out: list[Finding] = []
    for i, para in enumerate(paragraphs(letter), 1):
        for said in sentences(para):
            for pattern, why in GAP_DISCLAIMERS:
                if match := pattern.search(said):
                    out.append(Finding("gap_disclaimer", CRITICAL,
                                       f'"{match.group(0)}" {why}: '
                                       f"put real work in the slot instead (\u00a715)",
                                       f"para {i}"))
            for pattern, why in GAP_SOFTENERS:
                if match := pattern.search(said):
                    out.append(Finding("gap_softener", ADVISORY,
                                       f'"{match.group(0)}" {why} (\u00a715)',
                                       f"para {i}"))
    return out



# ---------------------------------------------------------------------------
# §14, positional half: the old information goes at the FRONT.
#
# Added 2026-09-28 from the HBR transitions guidance the user supplied. Its gold
# pair is the reason this check exists, because check_paragraph_chain passes
# BOTH halves of it:
#
#   ineffective: "Change will not be effected, say some others, unless
#                 individual actions raise the necessary awareness."
#   effective:   "Other experts argue that individual actions are key to
#                 raising the awareness necessary to effect change."
#
# Both repeat "individual", "actions" and "change" from the sentence before, so
# a bag-of-words overlap cannot tell them apart. What separates them is where
# the shared material sits: the effective version leads with it ("Other experts
# argue"), the ineffective version buries it behind new information. Measured on
# the first six words, the pair scores 1 against 6.
#
# ADVISORY, and it fires only where check_paragraph_chain already passed, so it
# never double-reports the same opener. On the corpus at the time it was added
# it fired on 3 of 120 passing openers.
OPENING_WINDOW = 6
MIN_OPENING_LINK = 2


def check_known_new(letter: dict[str, Any]) -> list[Finding]:
    """The link exists but arrives late: new information lands before old."""
    out: list[Finding] = []
    paras = paragraphs(letter)
    already = {f.where for f in check_paragraph_chain(letter)}
    for i, para in enumerate(paras[1:], 2):
        if f"para {i}" in already:
            continue
        opener = sentences(para)[0] if sentences(para) else para
        head = " ".join(opener.split()[:OPENING_WINDOW])
        strength = len(content_words(head) & content_words(paras[i - 2]))
        if BACKREF.search(head):
            strength += 2
        if strength < MIN_OPENING_LINK:
            out.append(Finding("buried_link", ADVISORY,
                               f'the backward reference arrives after word {OPENING_WINDOW}: '
                               f'"{opener[:60]}". Lead with what the reader already has.',
                               f"para {i}"))
    return out



# ---------------------------------------------------------------------------
# §16: no dramatic pivot, and the first-person preference that replaced the
# old ban on paragraph-opening "I".
#
# Added 2026-09-28 after the user flagged the pattern on sight. Both checks are
# here together because they are one defect. A pivot opener always has a
# non-human subject ("None of that", "That work", "What changed"), which was the
# cheapest way to start a paragraph without typing "I" under the rule that used
# to ban that. The user removed that rule on 2026-09-28 (check_paragraph_opening_i
# went with it); the pivot stays banned on its own account. Measured across every
# letter and form answer in the repo that day: 100% of 176 paragraph openers had
# a non-human subject and 7% reached first person within six words, against 73%
# in his own personal statement.
#
# The carve-out is §14's reinterpretation, whose worked example opens on a
# negation ("Neither of those is really a security problem. Both are onboarding
# problems"). A regex cannot judge whether a negation re-files the previous
# paragraph or merely delays the point, so only the shapes that have no
# reinterpreting reading are CRITICAL: those that name the text itself (the
# writing, the applying, the reason, the point) as the thing being disowned.
# The CRITICAL shape is narrow on purpose: the negation must disown THE WRITING
# ITSELF ("why I am writing", "the reason I am applying"). "None of that is why
# we are in Farport" is the standard logistics line and disowns a reason for
# a fact about his life, not the text; an earlier version of this pattern flagged
# it, which would have blocked every letter that explains the move. Anything
# looser is ADVISORY, because §14's reinterpretation ("Neither of those is really
# a security problem") is a legitimate negated opener and no regex can tell the
# two apart.
DISOWNING_PIVOT = re.compile(
    r"^\W*(?:none of (?:that|this|it|those)|nothing (?:about|in) (?:that|this|it)|"
    r"(?:that|this|it)(?:\s+\w+){0,2}?\s+(?:is|was)\s+not)"
    r"[^.]{0,50}?\b(?:why|the reason|the point)\b[^.]{0,25}?"
    r"\b(?:I|we)\s*(?:am|'m|are)\s+(?:writing|applying|here|sending|reaching)",
    re.I,
)

NEGATIVE_FIRST = re.compile(
    r"^\W*(?:what\b[^.]{0,40}?\b(?:was|is)\s+not\b"
    r"|[^.]{0,35}?\b(?:was|is|were)\s+never\s+(?:about|really)\b)", re.I)


def check_dramatic_pivot(letter: dict[str, Any]) -> list[Finding]:
    """§16: do not say what it is not about before saying what it is."""
    out: list[Finding] = []
    for i, para in enumerate(paragraphs(letter), 1):
        opener = sentences(para)[0] if sentences(para) else para
        if DISOWNING_PIVOT.match(opener):
            out.append(Finding("dramatic_pivot", CRITICAL,
                               f'"{opener[:60]}" disowns what came before. '
                               "Lead with the point (\u00a716)", f"para {i}"))
        elif NEGATIVE_FIRST.match(opener):
            out.append(Finding("negative_first", ADVISORY,
                               f'"{opener[:60]}" defines by what it is not. '
                               "Apply the delete test (\u00a716)", f"para {i}"))
    return out


FIRST_PERSON = re.compile(r"\b(I|my|we|our)\b", re.I)
PERSON_WINDOW = 6
MIN_PERSON_RATE = 0.5   # his own personal statement runs at 0.73
# Raised from 0.4 on 2026-09-28. The lower floor was set while a CRITICAL check
# still banned paragraph-opening "I", which made a high rate hard to reach
# honestly. With that ban gone there is nothing pushing openers onto
# abstractions, so the floor moves toward what he actually writes.


def check_first_person_reach(letter: dict[str, Any]) -> list[Finding]:
    """He should turn up early in his own paragraphs, not only mid-sentence."""
    paras = paragraphs(letter)
    if len(paras) < 3:
        return []
    early = 0
    for para in paras:
        opener = sentences(para)[0] if sentences(para) else para
        if FIRST_PERSON.search(" ".join(opener.split()[:PERSON_WINDOW])):
            early += 1
    rate = early / len(paras)
    if rate < MIN_PERSON_RATE:
        return [Finding("absent_narrator", ADVISORY,
                        f"{early} of {len(paras)} paragraph openers reach "
                        f'"I", "my", "we" or "our" within {PERSON_WINDOW} words '
                        f"({rate:.0%}; his own writing runs about 73%). Open on "
                        '"I ...", "My ...", or a short phrase that reaches him at once',
                        "body")]
    return []



# ---------------------------------------------------------------------------
# §17: vary the length on purpose. A long sentence followed by a short one reads
# well; six medium sentences in a row read as machine output.
#
# Only the "no short sentence anywhere" half is checkable, and only as a rhythm
# smell. §17's actual test is whether a short sentence adds logic or adds
# feeling, which no regex can answer: "It is still in beta" and "That's the trade
# I want to make" are the same length and opposite verdicts. So a hit here is a
# prompt to look, never an instruction to insert one. If the only short sentence
# available would add feeling, the paragraph is better left long.
#
# Dangling modifiers, colon structure and semicolon balance all need a parser or
# a human, and §17 says so rather than pretending otherwise. ADVISORY: the
# closing paragraph legitimately runs long, because the fixed final line is 13
# words and the logistics take room.
SHORT_SENTENCE = 12
MIN_SENTENCES_TO_JUDGE = 3


def check_sentence_variety(letter: dict[str, Any]) -> list[Finding]:
    """No sentence under SHORT_SENTENCE words anywhere in a multi-sentence para."""
    out: list[Finding] = []
    for i, para in enumerate(paragraphs(letter), 1):
        said = sentences(para)
        if len(said) < MIN_SENTENCES_TO_JUDGE:
            continue
        lengths = [len(x.split()) for x in said]
        if min(lengths) > SHORT_SENTENCE:
            out.append(Finding("no_short_sentence", ADVISORY,
                               f"every sentence runs over {SHORT_SENTENCE} words "
                               f"({', '.join(str(n) for n in lengths)}). A short one would "
                               f"help only if it adds logic; if it would add feeling, "
                               f"leave the paragraph long (\u00a717)",
                               f"para {i}"))
    return out


CHECKS = (
    check_em_dash, check_opening, check_feeling_verbs,
    check_tropes, check_banned_words, check_gap_disclaimer, check_closing,
    check_gloss, check_paragraph_chain, check_known_new,
    check_dramatic_pivot, check_first_person_reach, check_sentence_variety,
    check_final_line,
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
