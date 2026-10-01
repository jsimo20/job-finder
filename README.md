# job-finder

A job-search system in three parts: it **finds** roles worth applying to,
**preps and fills** the applications (stopping short of Submit, always), and
**grades its own fills** so coverage improves with every batch. Everything
that defines "your search" — titles, industry, metros, identity — is
configuration, not code:

- **`config/pipeline.toml`** (gitignored; template in
  `config/pipeline.example.toml`) — target job titles and seniority band,
  metros, commute tiers, domain/stage weights, comp floor. A fresh clone
  falls back to the example so nothing breaks before you configure.
- **`data/state.db`** (gitignored SQLite) — the tracked-company list, the
  applied and seen ledgers, and the digest archive. Managed via
  `job-finder companies|no-auto|applied|digest-archive` subcommands.
- **`profile/`** (gitignored) — who you are: identity, EEO answers, stock
  screening answers, master resume, writing voice. Created from the file
  blocks in SETUP.md §3 (`python -m job_finder.profile_init`);
  `python -m job_finder.profile_check` verifies it's filled in.

New user? Follow **[SETUP.md](SETUP.md)** top to bottom — written so you can
hand it to a Claude Code session and let it drive.

## Find — the weekly digest

A local scheduled task (Mondays 09:00; `scripts/install_schedule.ps1`
registers it and wakes the machine for it) collects postings from each tracked
company's public ATS endpoint (Greenhouse, Lever, Ashby, Workday), hard-filters
on title, seniority, and location, extracts structured signals with one Claude
Haiku call per surviving JD (YOE, comp, domains, onsite days), scores
deterministically, archives the ranked digest to `data/state.db`, and emails
it. Everything runs on your machine; nothing personal round-trips through
git or any cloud.

Companies with no pollable board are tracked as `manual` and listed in the
digest's **Manual check** section. If `[discovery]` in `config/pipeline.toml`
names Built In sites, each run also proposes untracked companies posting your
target role; `job-finder discover add` tracks one, and nothing is added
without you.

The working DB (`data/jobs.db`) is rebuilt every run; durable state lives in
`data/state.db`: the company list, the applied ledger that suppresses roles
you've applied to (including reposts, matched by company + title), the seen
ledger that drives new-vs-carried-forward, and the digest archive. The
`manage-companies` Claude skill edits the company universe from plain
English.

## Apply — materials and autofill (local-only)

- `/job-apply` — pick a role (or feed it ad-hoc URLs), review a tailored
  resume + cover-letter draft, fact-checked against your master resume by a
  separate agent so nothing gets overstated, then rendered to a per-job PDF
  folder.
- `python -m job_finder.fill_greenhouse --url … --folder …` — deterministic
  Greenhouse filler, zero LLM tokens: contact, work authorization, EEO,
  education, uploads, and your stored screening answers, in one browser with
  one tab per application. `/fill-application` is the agent fallback for
  other ATSes.
- Hard rules, both paths: never clicks Submit, never answers salary or legal
  questions, refuses ambiguous dropdown matches, and won't run at all until
  a real `profile/` exists.
- `job-finder applied add` / `outreach add` record what you submitted and who
  you contacted, so nothing resurfaces and nothing is forgotten.

### Unattended batches

From Cowork, build and install the plugin in `cowork-plugin/` (SETUP.md §8) and
run `/job-apply-weekly 5`. From Claude Code,
`/job-apply-batch --top 5` runs the whole loop over several roles without
stopping between them and reports once at the end, for a session you are not
watching. It is the same per-role loop as `/job-apply` with the approval gates
removed and three things added: a preflight that fails in ten seconds rather
than ten minutes if the ground-truth docs are unreadable, a rule to park a role
rather than guess when the fact-checker will not go CLEAN, and a gate over the
whole batch afterwards.

Nothing safety-relevant is relaxed. It still never submits, still leaves salary
blank, still refuses to claim anything it cannot trace. Those rules are why
running it unattended is reasonable, so they tighten rather than loosen: a
prompt asking it to submit is treated as the error.

## Improve — the eval loop

Every fill captures before/after field inventories to `data/fill_audits/`.
Each batch ends with a letter-graded scorecard
(`python -m job_finder.fill_grader --date …`, zero tokens): what filled, what
missed, what had no configured answer. `/fill-review` turns that into
permanent improvements — wrong answers become code fixes with regression
tests, unanswered questions get asked once and stored in your profile, so
the next batch starts where the last one left off.

`letter_linter` (zero tokens) blocks a drafted cover letter that breaks a flat
voice rule before it reaches a form. The rest of the eval suite is manual:
`eval_calibration` checks whether the score predicts what you apply to (zero
tokens), and `eval_factcheck`, `eval_skill_terms` and `eval_generation` grade
the fact-checker, the resume term mapper and the letter drafter (these spend
tokens). CLAUDE.md lists the commands.

## Run

```bash
job-finder run --email                   # full pipeline + digest email (spends API tokens)
job-finder status                        # last run, schedule, digest age, applied count
job-finder review                        # interactive picker: applied/dismissed
job-finder companies list                # the tracked-company universe
job-finder digest-archive show           # latest digest from the archive
python -m job_finder.profile_check       # is my profile complete?
python -m job_finder.letter_linter --date <YYYY-MM-DD>   # voice rules, zero tokens
python -m job_finder.fill_grader --date <YYYY-MM-DD> --suggest
pytest                                    # no network, keys, or profile needed
```

Credentials (`ANTHROPIC_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`) go in a
local `.env` or in user environment variables, never both; see SETUP.md §2. No
GitHub secrets are needed; the repo runs no CI workflows.

## Handing this repo to someone else

`git clone`, then follow SETUP.md, which keeps the original as an `upstream`
remote so later fixes can be pulled. There is nothing to reset: the repo
tracks no one's search state (all of `data/` and `digests/` is gitignored),
and history is kept clean of personal data on purpose.
