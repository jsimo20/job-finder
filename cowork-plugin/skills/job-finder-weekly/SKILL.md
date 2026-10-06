---
name: job-finder-weekly
description: Run the weekly job-finder cycle from Cowork with no API key. Polls the tracked boards, reads the new job descriptions in-session, scores them, writes the digest, then tailors, fact-checks, renders and fills the top N roles, leaving every form unsubmitted for review. Idempotent on a seven-day stamp, so a daily schedule is safe. Takes a count ("top 3", "--top 5", "all"), --apply-only, --pipeline-only, --force; defaults to 3. Use for the weekly run, a scheduled run, or "work through the top roles".
---

# job-finder-weekly

Cowork does not index project-level `.claude/skills/`, so this exists only to be
discoverable from `/`. **The procedure is `.claude/skills/job-finder-weekly/SKILL.md`
in the mounted repo. Read it and follow it, passing `$ARGUMENTS` through.**
Nothing about the pipeline, the extraction batches, the apply loop or the
reporting is restated here; that file is maintained alongside the code it
drives and a second copy would drift from it.

## If the repo is not mounted

This drives a specific repository. Without it there are no tracked companies,
no profile, and no ground truth to check claims against.

Say so and stop. Do not improvise an application from a job posting alone.
