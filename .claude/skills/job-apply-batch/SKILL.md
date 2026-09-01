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
count in your first message. Above 10, state what the run will cost; ask first
only if someone is there to answer, and otherwise proceed and note it. A
scheduled run has nobody to ask, and stalling on a question is worse than a
long run.

**Which fill path is available depends on the surface, and on Cowork there is
only one.** `fill_greenhouse` needs the `playwright` Python module, which the
Cowork device VM does not have, and a browser launched inside that VM is not one
the user can see or click, which defeats leaving tabs open for review. Tested
2026-08-31: it does not run there. So a Cowork batch fills every form through the
autofill agent at roughly 63k tokens per form, and that is a ceiling on how many
roles one batch can carry, not a preference to weigh. In Claude Code on Windows
`fill_greenhouse` does run, costs about 2k per form, and is the better path
wherever the ATS is Greenhouse.

**The per-role loop is `.claude/commands/job-apply.md` and is not restated
here.** Read it and follow it for each role. This file specifies only what
changes when nobody is watching. Two copies of that loop would drift.

## 1. Preflight, before drafting anything

**Every Python call below is prefixed `PYTHONPATH=".cowork-deps:src" python3`.**
`job_finder` lives under `src/` and the only editable install is a .pth file in
the Windows `.venv`, which a Linux device VM cannot see, so a bare `python -c`
dies on `No module named 'job_finder'` before it reaches any real work.

**On Windows, drop the prefix and use `.venv/Scripts/python.exe`.** The editable
install already puts `job_finder` on the path there, and Windows separates
PYTHONPATH entries with `;` rather than `:`, so the prefix as written resolves to
one nonexistent directory.

If `.cowork-deps/` is missing, build it rather than failing:

```sh
sh scripts/bootstrap_cowork_deps.sh
```

It is gitignored, so a fresh clone or a different machine will not have it.
**If the bootstrap itself fails** (no egress, no pip), say so plainly in the
report and carry on: liveness treats unknown as live, so losing it costs tokens
on dead postings rather than correctness. Losing `reportlab` is different and
does stop the run, because `render()` cannot write a PDF without it.

Confirm you can read every ground-truth file and print the absolute path of
each:

- `profile/inputs/resume_master.md`
- `profile/inputs/personal_statement.md`
- `profile/inputs/standard_answers.md`
- `profile/ai_skills/claims_ground_truth.md`
- the writing-style file named by `[paths].writing_style_path`
- the resume generator at `[paths].resume_skill_path`

All of them live inside the repo. **If any is unreadable, stop and say so
before doing any work.** Nothing drafted against an unreachable source pool can
be traced, and no revision pass will reach CLEAN.

Then check the digest is current:

```sh
job-finder digest-archive list
```

The `job-finder` console script comes from the editable install, so on a device
VM it is not on PATH either. There the equivalent is
`PYTHONPATH=".cowork-deps:src" python3 -m job_finder.cli digest-archive list`,
which needs the `--cli` extras. **Prefer running this on Windows**, where the install already works; pulling `anthropic` into
`.cowork-deps` locks it to one Python build.

**Report the date of the latest digest, and stop if it is more than 7 days old.**
The roles come from that digest; a stale one means applying to postings that may
already be filled. If the caller named a required date, honour it exactly.

Then drop the roles that have already closed, **before spending anything on
them**:

```sh
PYTHONPATH=".cowork-deps:src" python3 -c "
from job_finder import liveness
import json,sys
roles = json.load(sys.stdin)
worth, dead = liveness.partition(roles)
print(json.dumps({'worth': worth, 'dead': dead}, indent=1))
" <<< '<the picked roles as JSON: company, external_id, title>'
```

A digest is a snapshot, and postings close between the run that wrote it and
the run that reads it. Checking costs under a second per board and no tokens;
tailoring a closed posting costs a full draft, fact-check and render.

**Report the dead ones as skipped, with their titles, and carry on with the
rest.** An undetermined role counts as live and gets tailored: a network blip
must never look like a closed posting. If dropping the dead ones leaves fewer
roles than asked for, say so rather than topping the list back up.

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
than the agent by roughly 30x and drives its own browser too. Prefer it in Claude
Code on Windows. **It is not available on Cowork** — see the note at the top of
this file; do not attempt it there and do not report it as a fill path.

**Playwright starts from a fresh profile with no cookies or logins.** Any form
behind an account wall is unreachable by it however well it fills, so those get
an `APPLY_NOTES.md` handoff rather than an attempt. That is the existing rule,
not a new limitation.

### Probe the upload path before drafting anything

**The server accepts uploads only from its `--output-dir` and its cwd.** Cowork
spawns it with `cwd=C:\Windows\System32`, so if the installed plugin was built
without `--output-dir`, every staged PDF is rejected as outside allowed roots and
no application gets a resume or a cover letter attached. On 2026-08-31 that
surfaced only after seven roles had been tailored, rendered and filled, which is
the expensive place to find it.

So test it first, with one throwaway file, on the real path:

```sh
mkdir -p .playwright-mcp/uploads
echo upload probe > .playwright-mcp/uploads/_probe.txt
```

Then, using the Playwright tools:

1. `browser_navigate` to
   `data:text/html,<input type="file" id="probe">`
2. `browser_snapshot` to get the ref, then `browser_click` it, which opens the
   file chooser. **The ref goes in `target`, not `ref`** — `ref` is rejected as a
   missing argument and costs a round trip.
3. `browser_file_upload` the **absolute** path of `.playwright-mcp/uploads/_probe.txt`
4. Confirm it actually attached, because a call that returns without an error is
   not proof:
   ```
   browser_evaluate: () => document.getElementById('probe').files.length
   ```
   Verified 2026-08-31 in Claude Code, where the output dir is set: returns 1.

Three outcomes, and they are not two:

- **Accepted** — step 4 returns 1. Uploads work. Say so in one line and carry on.
- **Rejected** — quote the error verbatim at the **top** of your first message,
  before anything about roles. The rejection names the roots the running server
  actually allows, and that text is the only place the installed plugin's real
  configuration is visible, so it is the diagnosis rather than just the symptom.
  Say plainly: **every role in this batch will need its resume and cover letter
  attached by hand**, and the fix is to rebuild and reinstall the plugin
  (`python scripts/build_cowork_plugin.py`, then Cowork tab -> Customize ->
  Plugins -> upload the zip). **Do not stop.** Prep is still worth doing: the
  tailoring, fact-checking and rendering are all still good, and the forms still
  get filled with everything that is not a file.
- **Inconclusive** — the probe itself could not run (no file chooser, the
  `data:` URL blocked, the tools absent). Report it as inconclusive. **Never
  report an inconclusive probe as a pass**, and expect the hand-attach.

Delete `_probe.txt` afterwards.

**Do not work around a rejection.** The allowed-roots restriction is a security
boundary on a browser-driving agent. No `browser_run_code_unsafe`, no
self-written JS, no copying PDFs into Windows temp to land inside the server's
own directory. The fix is the server's configuration, and a run that cannot
upload reports that it cannot upload.

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
- **Uploaded filenames are `<Name>_Resume_<company>.pdf`, always.** That name is
  what the hiring manager sees on the application, so it never carries a slug,
  a date, a tab index or any other staging artifact. Same-company roles still
  have to be kept apart, and the role slug goes in the staging **folder**, never
  in the filename. Both halves of this have already gone wrong once: identically
  named PDFs overwriting each other, and then a `role-slug__` prefix shipping to
  a live Greenhouse form on 2026-08-25.

## 5. Gate the batch

Two gates. Run the letter linter **after render and before any fill**, so a bad
letter never reaches a form:

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.letter_linter --date <today>
```

- **0** — no critical violation.
- **4** — a letter breaks a flat ban (em-dash, a paragraph opening on "I", an
  opening that announces a reaction rather than stating a fact about the company,
  a feeling verb, a trope, a closing that is not "Thanks,"). **Re-draft that letter and re-render
  before filling it.** These are zero-judgment rules, so there is nothing to
  weigh and nothing to ask about: fix it and carry on. Never fill a form with a
  letter that failed, and never skip the role instead of fixing it.
- **3** — no `cover_letter.json` found, so nothing was rendered. Not a pass.

ADVISORY lines never block. They are candidates for a human: a trailing clause
that may be restating its sentence, a paragraph opening on a fresh topic, a close
that names nothing from the opening. Put them in the report; do not act on them
unattended, because each has legitimate exceptions.

Then, after the last fill:

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.fill_grader --date <today> --gate
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
5. **Gates** — the letter linter's exit code and any ADVISORY lines, then the
   fill grader's exit code, or why either could not run. Name the fill path each
   role took, deterministic script or autofill agent; that is the run's largest
   cost and the report is the only place it is visible.
6. **One cover letter, quoted in full.** Pick the role you are least sure of and
   paste its four paragraphs. **Neither gate can tell whether the opening's
   contrast is true.** "Most companies do X, this one does Y" passes the linter
   and the fact-checker both while being something you invented about the
   category, and a build procedure makes that failure more likely rather than
   less. One letter read by a human per batch is the only check on it.
7. **`mark-applied` commands** for everything in section 2, ready to paste.

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
