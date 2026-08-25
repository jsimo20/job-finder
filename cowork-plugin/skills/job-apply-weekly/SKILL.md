---
name: job-apply-weekly
description: Run the weekly job application batch from Cowork. Tailors, fact-checks, renders and fills the top N pending roles from the latest digest, leaving every form filled but unsubmitted for review. Takes a count ("top 3", "--top 10", "all of them"); defaults to 5. Use for the Monday run, or any time the user asks to work through the top roles.
---

# job-apply-weekly

Cowork does not index project-level `.claude/skills/`, so this exists only to be
discoverable from `/`. **The procedure is `.claude/skills/job-apply-batch/SKILL.md`
in the mounted repo. Read it and follow it.** Nothing about the loop, the
guardrails, or the reporting is restated here; that file is maintained alongside
the code it drives and a second copy would drift from it.

## The one thing this file decides

**How many roles**, from `$ARGUMENTS`:

| They say | You run |
|---|---|
| `--top 3`, `top 3`, `3` | 3 |
| nothing | 5 |
| `all`, `everything` | every pending main-queue role |

Confirm the count in your first message before drafting anything. Above 10,
state what the run will cost; ask first only if someone is there to answer.
A scheduled run has nobody to ask, so proceed and note it rather than stalling.

## If the repo is not mounted

This drives a specific repository. Without it there is no digest, no profile,
and no ground truth to check claims against.

Say so and stop. Do not improvise an application from the job posting alone:
every claim has to trace to the ground-truth documents, and without them nothing
drafted could be verified.
