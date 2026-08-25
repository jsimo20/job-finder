# Setup — new user

Step-by-step setup for a fresh clone. Written so you can paste it into a
Claude Code session ("follow SETUP.md") and have it drive; every step also
works by hand. Nothing here requires the original owner's files, and the repo
carries no personal data at all: everything personal lives in three gitignored
places you create yourself — `config/pipeline.toml` (search preferences),
`profile/` (identity), and `data/state.db` (companies, ledgers, digest
archive). The pipeline runs locally on a weekly schedule; there is no cloud
pipeline to configure.

## 0. Prerequisites

- Python 3.10 or newer
- `git`, and the `gh` CLI logged into your GitHub account
- `uv` (`pip install uv`) — or plain pip, adjusting the commands below
- An Anthropic API key with credit (console.anthropic.com) — the pipeline's
  extraction stage bills against it
- A Gmail account with 2FA, for the digest email
- A Windows machine that's usually on (the weekly run is a Scheduled Task;
  on macOS/Linux use cron/launchd with the same command)

If a Claude Code session is driving this setup, four things still need a
human first — everything else it can do from this document:

1. Installing Claude Code itself (plus Python/git/gh above)
2. Access to this repo (a collaborator invite, or a copy from whoever
   handed it to you)
3. Creating the Anthropic API key and adding billing
4. Generating the Gmail app password (§2) — never paste it into chat;
   put it straight into `.env` yourself

## 1. Get a copy

```sh
git clone <repo-url> my-job-finder && cd my-job-finder
git remote set-url origin git@github.com:<your-user>/my-job-finder.git
gh repo create <your-user>/my-job-finder --private --source=. --push
```

Nothing to reset: the repo contains no one's search state. Everything
personal is created locally in the steps below and never committed.

## 2. Install

```sh
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install uv
uv pip install -e ".[dev]"
```

The browser-autofill workflow (optional, local-only):

```sh
uv pip install -e ".[apply]"
playwright install chromium
```

Sanity check — the suite must pass on a fresh clone with no profile:

```sh
python -m pytest -q
```

Create a `.env` at the repo root — the pipeline and the digest email read
it (plain key=value, three lines):

```
ANTHROPIC_API_KEY=sk-ant-...
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
```

`GMAIL_APP_PASSWORD` is a 16-char app password from
myaccount.google.com/apppasswords (requires 2FA). `GMAIL_USER` is both the
sender and the recipient of the digest.

## 3. Create your profile

```sh
cp -r profile.example profile
```

Then edit, in this order:

1. **`profile/profile.toml`** — your name, email, phone, links, city;
   work-authorization stance; EEO defaults (leave `""` for any question you
   want to answer by hand on every form). Optionally point `[paths]` at
   folders outside the repo.
2. **`profile/resume_master.md`** — your real history. This is ground truth:
   the fact-checker flags anything in a draft that doesn't trace to it.
3. **`profile/personal_statement.md`** — a page in your own voice.
4. **`profile/standard_answers.md`** — contact block + stock screening answers.
5. **`profile/fit_profile.md`** — what a great role looks like for you.
6. **`profile/generate_resume.py`** — edit only the RESUME_DATA block.
7. **`profile/qa_checklist.md`** and **`profile/claims_ground_truth.md`** — grow
   these over time; the defaults work on day one.

**Do not skip 2–4.** The tailoring, fact-checking, and autofill workflows all
read those files; with placeholders still in them you'd be submitting
applications carrying example data. When you think you're done, prove it:

```sh
python -m job_finder.profile_check
```

It flags every placeholder value and missing driving doc, and exits non-zero
until your profile is real. Run it again any time; the apply workflow assumes
it passes.

`profile/` is gitignored. Verify before your first push:

```sh
git check-ignore profile/ && git status --short
```

## 4. Configure the pipeline

Your search parameters are personal, so the real config is gitignored:

```sh
cp config/pipeline.example.toml config/pipeline.toml
```

Edit **`config/pipeline.toml`**. What to edit:

- `[location]` — replace the metro regexes with your own target geography,
  and the commute tiers/notes with drive times from where you live.
- `[domains.*]` / `[stages.*]` — reweight to your background; definitions
  feed the extraction prompt, so keep them concrete.
- `[filters]` — your comp floor, comp score thresholds, and years-of-experience cap.

- `[titles]` — which job titles count as target roles, adjacent tracks to
  exclude, and the seniority band. This is the industry knob: replace the
  product-management defaults with your own market's title patterns.
- `[extraction]` — the role noun the extraction prompt speaks about.

## 5. Build your company list

The tracked-company list lives in `data/state.db` (gitignored). Start from
the tiny neutral example, then build your own market's list:

```sh
job-finder companies import config/companies.example.json
job-finder companies list
```

To expand: put candidate employer names in a text file, probe them
(`python scripts/discover_companies.py --file candidates.txt --json hits.json`),
verify the hits, and `job-finder companies import hits.json`. The
`manage-companies` skill drives all of this from plain English in a Claude
Code session.

## 6. Schedule the weekly run

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_schedule.ps1
```

Registers a Windows Scheduled Task: `job-finder run --email` every Monday at
09:00 local, with catch-up at next boot if the machine was off. Test it once
by hand first (`job-finder run --email` — this spends real API tokens).

No GitHub Actions secrets are required: the repo runs no CI workflows. Code
review is on demand: dispatch the `python-code-reviewer` agent, or use the
built-in `/code-review`. Either runs locally against your own key.

## 7. Personalize the Claude-side workflows

The `.claude/` prompts are generic: every user-specific rule (metric
baselines, banned framings, voice) is read at run time from your profile
docs, mainly `profile/claims_ground_truth.md` and the files in `[paths]`. So
personalization happens in §3, not by editing prompts. Two things worth a
skim anyway:

- `profile/claims_ground_truth.md` — the per-claim framing rules the
  fact-checker enforces come from here; the richer you make it, the more it
  catches
- `CLAUDE.md` — project instructions; adjust anything that doesn't match how
  you work

## 8. Optional — run it from Cowork

Skip this if you only use Claude Code; everything works there already.

Cowork does not index a project's `.claude/skills/`, so the weekly batch is also
packaged as a plugin in `cowork-plugin/`. Build the archive:

```sh
python scripts/build_cowork_plugin.py
```

That writes `job-finder-cowork-plugin.zip` to your Downloads folder (`--out` to
put it elsewhere). Then, in Cowork: **Customize -> Plugins -> upload** it.

**Install it; do not add `cowork-plugin/` as a context folder.** A connected
folder is just files on disk, so its `.mcp.json` never runs, Playwright never
starts, and the failure looks exactly like a broken plugin.

Once installed, `/job-apply-weekly` runs the batch. It takes a count:
`/job-apply-weekly 3`, or `all`, defaulting to 5. The plugin is a launcher only
— the procedure it follows is `.claude/skills/job-apply-batch/SKILL.md` in this
repo, so **the repo still has to be the mounted folder for that session.**

Two things worth knowing before you rely on it:

- The plugin's `.mcp.json` is **required, not a duplicate of the repo-root one**.
  Cowork does not read a project's `.mcp.json`, so a plugin-bundled server is the
  only way it gets Playwright; the repo copy serves Claude Code. If you bump the
  version, bump both.
- Playwright starts from a fresh browser profile with no cookies or logins, so
  any form behind an account wall gets an `APPLY_NOTES.md` handoff for manual
  submission rather than a fill attempt.

## 9. What never goes in git

Everything personal, already handled by `.gitignore`: `profile/`, `.env`,
`config/pipeline.toml`, and ALL of `data/` and `digests/` — the state
database (companies, applied/seen ledgers, digest archive), the ephemeral
jobs.db, fill audits, and the outreach log. The repo is pure engine; if a
commit ever contains personal data, that's a bug.

## Day-to-day commands

```sh
python -m pytest -q                              # tests
python -m job_finder.profile_check         # is my profile complete?
job-finder review                          # interactive digest review
job-finder applied add --external-id ...   # record an application
python -m job_finder.fill_greenhouse \
    --url <apply url> --folder <per-app folder>   # deterministic form fill
python -m job_finder.letter_linter --date <YYYY-MM-DD>  # grade the drafted letters
python -m job_finder.fill_grader --date <YYYY-MM-DD>   # grade a fill batch
```

After every fill batch, run the grader on that date's audit manifests. It
letter-grades each form (missed fields, environment failures, critical
violations like a wrong sponsorship answer) and its `no_rule` list is your
backlog: each entry becomes a new `[[custom_combos]]` answer in
`profile/profile.toml`, so coverage compounds batch over batch.

The pipeline itself (`job-finder run`) is what the scheduled task runs
weekly — it spends real Anthropic tokens, so avoid extra casual runs.
`job-finder digest-archive list|show` reads the archive in state.db.
