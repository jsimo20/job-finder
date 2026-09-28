#!/usr/bin/env python3
"""Score a set of drafted materials on the writing rules, deterministically.

The letter linter answers "does this block". This answers "how close is it to
how the user writes", which is the question the voice rules are actually about and
which no single check covers. Run it over two directories to compare a revision
against what it replaced.

Baselines are measured from the personal statement that `job_apply.load_config()`
resolves, not invented.

Usage:  python3 scripts/score_writing.py <dir> [<dir> ...]
        where each dir holds <slug>/cover_letter.json and/or form_answers.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from job_finder import job_apply, settings  # noqa: E402
from job_finder import letter_linter as LL  # noqa: E402

FIRST_PERSON = re.compile(r"\b(I|my|we|our|me)\b", re.I)
CLEFT = re.compile(r"^(what|where|the (thing|part|reason|one)s?)\b.{0,60}?\b(is|was|are|were)\b", re.I)
IDENT = re.compile(r"\b(is|was|are|were)\s+(what|where|the (thing|part|reason|one)s?)\b", re.I)
WINDOW = 6


def docs(root: Path):
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        c = folder / "cover_letter.json"
        if c.is_file():
            yield folder.name, "letter", json.loads(c.read_text(encoding="utf-8"))
        a = folder / "form_answers.json"
        if a.is_file():
            for item in json.loads(a.read_text(encoding="utf-8")):
                yield folder.name, "answer", item


def ngrams(text: str, n: int = 8):
    w = re.findall(r"[a-z0-9$%.]+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def score(root: Path) -> dict:
    items = list(docs(root))
    paras = [p for _, _, d in items for p in LL.paragraphs(d)]
    sents = [s for p in paras for s in LL.sentences(p)]
    # A form answer is not a letter: it has no salutation, no fixed closing line
    # and no "Thanks,". Linting it with the full set would report two CRITICALs
    # per answer that are artifacts of the harness, not defects in the writing.
    form_checks = tuple(c for c in LL.CHECKS
                        if c not in (LL.check_closing, LL.check_final_line))
    findings = Counter()
    for _, kind, d in items:
        checks = LL.CHECKS if kind == "letter" else form_checks
        doc = {**d, "closing": d.get("closing", "Thanks,")}
        for f in (x for c in checks for x in c(doc)):
            findings[f"{f.severity}:{f.check}"] += 1

    openers = [LL.sentences(p)[0] if LL.sentences(p) else p for p in paras]
    early = sum(bool(FIRST_PERSON.search(" ".join(o.split()[:WINDOW]))) for o in openers)
    cleft = sum(bool(CLEFT.match(s.strip()) or IDENT.search(s)) for s in sents)
    starts_fp = sum(bool(re.match(r"\W*(I|My|We|Our)\b", s.strip())) for s in sents)
    lengths = [len(s.split()) for s in sents]

    # cross-document duplication: 8-word runs shared by two or more documents
    seen, dup = {}, Counter()
    for name, kind, d in items:
        key = f"{name}/{kind}"
        for g in ngrams(" ".join(LL.paragraphs(d))):
            if g in seen and seen[g] != key:
                dup[g] += 1
            seen.setdefault(g, key)

    return {
        "documents": len(items),
        "paragraphs": len(paras),
        "sentences": len(sents),
        "CRITICAL": sum(v for k, v in findings.items() if k.startswith("CRITICAL")),
        "ADVISORY": sum(v for k, v in findings.items() if k.startswith("ADVISORY")),
        "by_check": dict(findings),
        "opener_first_person_pct": round(100 * early / len(openers)) if openers else 0,
        "sentence_starts_first_person_pct": round(100 * starts_fp / len(sents)) if sents else 0,
        "cleft_pct": round(100 * cleft / len(sents), 1) if sents else 0,
        "mean_sentence_len": round(sum(lengths) / len(lengths), 1) if lengths else 0,
        "shortest_sentence": min(lengths) if lengths else 0,
        "em_dashes": sum(p.count("—") for p in paras),
        "shared_8grams": len(dup),
    }


def baselines() -> dict:
    path = job_apply.load_config(settings.require_profile()).personal_statement_md
    text = path.read_text(encoding="utf-8")
    ps = [p for p in text.split("\n\n") if p.strip() and not p.startswith("#")]
    ss = [s for p in ps for s in LL.sentences(p.replace("\n", " "))]
    openers = [LL.sentences(p.replace("\n", " "))[0] for p in ps]
    return {
        "opener_first_person_pct": round(100 * sum(
            bool(FIRST_PERSON.search(" ".join(o.split()[:WINDOW]))) for o in openers) / len(openers)),
        "sentence_starts_first_person_pct": round(100 * sum(
            bool(re.match(r"\W*(I|My|We|Our)\b", s.strip())) for s in ss) / len(ss)),
        "cleft_pct": round(100 * sum(
            bool(CLEFT.match(s.strip()) or IDENT.search(s)) for s in ss) / len(ss), 1),
        "mean_sentence_len": round(sum(len(s.split()) for s in ss) / len(ss), 1),
    }


def main() -> int:
    roots = [Path(a) for a in sys.argv[1:]]
    if not roots:
        print(__doc__)
        return 2
    results = [(r.name, score(r)) for r in roots]
    base = baselines()

    rows = ["CRITICAL", "ADVISORY", "opener_first_person_pct",
            "sentence_starts_first_person_pct", "cleft_pct", "mean_sentence_len",
            "shortest_sentence", "em_dashes", "shared_8grams"]
    w = max(len(r) for r in rows) + 2
    head = "".join(f"{n[:22]:>24}" for n, _ in results)
    print(f"{'metric':<{w}}{head}{'  his own writing':>20}")
    print("-" * (w + 24 * len(results) + 20))
    for r in rows:
        cells = "".join(f"{s[r]:>24}" for _, s in results)
        print(f"{r:<{w}}{cells}{str(base.get(r, '')):>20}")
    print()
    for name, s in results:
        if s["by_check"]:
            print(f"{name}: " + ", ".join(f"{k.split(':')[1]}={v}"
                                          for k, v in sorted(s["by_check"].items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
