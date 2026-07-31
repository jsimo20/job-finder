# /fill-review — turn fill grades into permanent improvements

Usage: `/fill-review [date]` — date defaults to the most recent batch with
post manifests in `data/fill_audits/`.

You are running the improvement ritual after a fill batch. The goal: every
graded gap either becomes a stored answer, a code fix, or an explicit
"leave manual" decision. Nothing gets diagnosed twice.

## 1. Grade with suggestions

```sh
python -m job_finder.fill_grader --date <date> --suggest
```

## 2. Triage each bucket, in this order

**critical** — stop and fix the code first. A critical is a wrong answer
committed to a form (vetoed sponsorship option, populated salary or
name-trap field). Diagnose against `fill_greenhouse.py`'s matching order and
VETO table, write the fix, and add a regression test that pins the exact
label and options from the manifest. This is a PR before anything else.

**missed** (rule exists, field blank) — compare the field's actual options
(shown by `--suggest`) against the configured candidates. Almost always a
phrasing gap: propose adding a fallback candidate to the relevant list
(`[eeo]`, `[education]`, `[answers]`, or a `[[custom_combos]]` entry —
values accept ordered fallback lists). Show the user the proposed diff
before writing it.

**env_failure** (dropdown options never rendered) — not an answers problem.
Note the count; if the same field fails twice across batches, that is a
code issue (menu-open retry timing in `fill_combo`) worth a PR.

**no_rule** (no configured answer) — these are questions only the user can
answer. Collect them across the batch, dedupe by label, and ask the user
each one, showing the form's actual options. Use AskUserQuestion for
multiple-choice screening questions when there are few; a plain list is
fine for many.

## 3. Persist the user's answers — both stores, always

For each answer the user gives:

1. Add a `[[custom_combos]]` entry (or extend `[eeo]`/`[education]`/
   `[answers]`) in `profile/profile.toml` — the deterministic filler's
   store. Label regex should be tight enough not to collide with the
   built-in patterns; check `build_combo_fields` ordering.
2. Mirror it in the `Screening question stock answers` section of the
   `standard_answers.md` in the configured `inputs_dir` — the autofill
   agent's store.

If the user says "leave that one manual" (legal questions, consent,
anything they want to see every time), record it as a comment in
profile.toml so the next review doesn't re-ask.

## 4. Prove the improvement

Re-run the grader on the same date after persisting answers:

```sh
python -m job_finder.fill_grader --date <date> --quiet
```

Read the delta correctly: the manifest is frozen, so every question you just
answered moves from `no_rule` to `missed` on the re-run — the old batch's
grade may DROP, and that is the signal working, not a regression. Report the
backlog conversion ("9 no_rule -> answered; 2 left manual by choice") and
state plainly that the letter-grade gain lands on the next live batch, when
the filler actually holds these answers.

## Hard rules

- Never invent an answer to a screening question. Every new stored answer
  comes from the user in this conversation, verbatim or confirmed.
- Sponsorship/authorization questions never get new candidates without the
  user restating the answer — the veto table exists because this is the one
  field where a wrong commit is unrecoverable.
- Multi-step wizard forms (Phenom/Circle) are out of eval scope by the
  user's decision: grade what the manifest shows, don't chase
  the unreached steps.
- Code fixes go through a PR like everything else; profile/standard-answer
  edits are local files, no PR needed.
