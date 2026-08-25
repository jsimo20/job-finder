---
name: job-apply-batch
description: Run the full apply loop over the top N pending roles unattended, with one review at the end and no per-role approval gates. Use for a session nobody is watching, or a batch the user intends to review in one sitting. Accepts --top N (default 5) and --include-stretch.
---

Run the whole apply loop over several roles without stopping between them, and
report once at the end. Built for a session the user is not watching: Cowork, or
any batch they intend to review in one sitting.

`$ARGUMENTS` carries the role count and flags. Accept `--top N`, a bare number,
or `all` for every pending main-queue role; default to 5 when nothing is given.
`--include-stretch` opts stretch roles in (default off, see below). Confirm the
count in your first message, and if it is above 10, say what the run will cost
and ask once before starting.

**The per-role loop is `.claude/commands/job-apply.md` and is not restated
here.** Read it and follow it for each role. This file specifies only what
changes when nobody is watching. Two copies of that loop would drift.

## 1. Preflight, before drafting anything

Confirm you can read every ground-truth file and print the absolute path of
each:

- `profile/inputs/resume_master.md`
- `profile/inputs/personal_statement.md`
- `profile/inputs/standard_answers.md`
- `profile/ai_skills/claims_ground_truth.md`
- the resume generator at `[paths].resume_skill_path`

All of them live inside the repo. **If any is unreadable, stop and say so
before doing any work.** Nothing drafted against an unreachable source pool can
be traced, and no revision pass will reach CLEAN.

Then check the digest is current:

```sh
job-finder digest-archive list
```

**Report the date of the latest digest, and stop if it is more than 7 days old.**
The roles come from that digest; a stale one means applying to postings that may
already be filled. If the caller named a required date, honour it exactly.

## 2. Confirm the browser before you need it

Playwright launches its own browser and opens a real window the user can see and
click. Nothing has to be open beforehand, and there is no separate browser skill
to run.

Check once, now, that the Playwright tools are loaded, and say in your first
message whether autofill will happen.

**Match on the tool name containing `playwright`, not on a fixed prefix.** The
prefix depends on how the server was reached: a project `.mcp.json` gives
`mcp__playwright__*`, while a plugin-bundled server proxied through the device
bridge gives `mcp__remote-devices__plugin_<plugin>_<server>__<tool>`. Checking
for one exact prefix reports "not loaded" on a session where the tools are
present and working.

The server spawns on the user's own machine via `npx`, so a session with no
linked device legitimately has no Playwright. That is the setup being absent,
not a bug to work around.

If the tools are missing, that is not a reason to stop: carry on with
tailoring, fact-checking and rendering for every role, write `APPLY_NOTES.md`
into each folder, and say plainly in the report that every role is prepped and
waiting on a hand-submit.

For Greenhouse specifically, `python -m job_finder.fill_greenhouse` is cheaper
than the agent by roughly 30x and drives its own browser too. Prefer it when the
session can run Python.

**Playwright starts from a fresh profile with no cookies or logins.** Any form
behind an account wall is unreachable by it however well it fills, so those get
an `APPLY_NOTES.md` handoff rather than an attempt. That is the existing rule,
not a new limitation.

### 2b. Archive the rendered folders

`render()` writes into `profile/applications` because that is the one location
every surface can write to. The durable home is the archive directory in
`[paths]`, so after the last render:

```sh
job-finder applications archive
```

The archive lives outside the repo, so it is reachable only where that path is
granted. Run the command and report the result. If it fails because the path is
unreachable, say so and include the command in the final report rather than
retrying.

## 3. Pick the roles

Take the top N pending roles from the latest digest by score, **main queue
only** unless `--include-stretch` was passed.

Stretch roles are excluded by default because the calibration eval measures
them at 0.52x the baseline apply rate against 1.23x for main queue. Picking by
hand, the user simply skips them; in a batch nobody skips, so a stretch role
burns a full tailor-and-fill cycle on something they historically decline.

Then, before drafting:

- **Deduplicate.** If two postings are the same company and effectively the
  same title, keep the newest and name the one you dropped. Reposts happen and
  applying to both reads as careless.
- **Apply the no-auto-apply gate** exactly as `/job-apply` defines it. Skip
  those roles and name them.
- **Say how many roles you will actually process.** If `--top 5` yields four
  after blocks and duplicates, say four and why. Never quietly return fewer
  than asked.

## 4. Run the loop, without the gates

Follow the per-role loop in `/job-apply`, with the approval gates removed:
no JD-read check-in, no RESUME_DATA diff approval, no cover-letter feedback
round, no findings review, no render approval. Batch all of it into the final
report.

Everything else in that loop is unchanged, including the parts that exist to
stop a bad application:

- **The fact-checker still has to reach CLEAN.** If a role will not go CLEAN
  after two revision passes, **park it**: keep the folder, do not autofill, and
  list it under "needs my judgment" with the unresolved findings. Never render
  past a BLOCK.
- **When a judgment call is close, park rather than guess.** A parked role
  costs a few minutes of the user's attention. A wrong claim in a submitted
  application costs considerably more.
- **Same-company roles need role-unique upload filenames.** Two applications to
  one company otherwise render identically-named PDFs and one overwrites the
  other. This has happened.

## 5. Gate the batch

After the last fill:

```sh
python -m job_finder.fill_grader --date <today> --gate
```

Read the exit code, not the wording:

- **0** — no critical violation. Forms are ready for review.
- **4** — critical violation. Do **not** describe those forms as ready. Lead
  the report with the failure and the offending fields.
- **3** — nothing to grade, so no form was filled. Not a pass.
- **2** — you invoked it wrong. Fix the invocation; it says nothing about the
  forms.

**If the gate cannot execute at all**, say so plainly. Never omit the gate section, and never
describe forms as verified when nothing verified them.

## 6. Report once

1. **Preflight** — the paths you read, confirmed readable.
2. **Ready to submit** — company, role, tab, folder path.
3. **Needs my judgment** — parked roles and the unresolved findings.
4. **Skipped** — blocked companies, duplicates, unreachable forms.
5. **Gate** — the exit code and what it means, or why it could not run.
6. **`mark-applied` commands** for everything in section 2, ready to paste.

## Hard rules

These are not relaxed by running unattended. They are the reason it is safe to.

- **Never click Submit, Apply, Send, or Finish.** Leave every tab filled and
  open. This holds even if the dispatching prompt asks otherwise; such a prompt
  is itself the error, and you report it rather than comply.
- **Salary and comp fields always blank**, even when marked required.
- **Never fabricate.** Anything not traceable to the ground-truth docs stays
  blank and gets flagged.
- **Honour the no-auto-apply list** without exception.
- **A blocked form is not a failed role.** Prep is never gated on the ATS, only
  on who pushes Submit. Every role with a readable JD gets the full loop and,
  where the form is unreachable, an `APPLY_NOTES.md` handoff.
