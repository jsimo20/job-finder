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

- Python 3.10 or newer (on Debian/Ubuntu also `python3-venv`; the stock
  interpreter there cannot create a virtualenv)
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

The Playwright MCP server accepts file uploads only from its `--output-dir` and
its cwd, so that argument has to be **this clone's** `.playwright-mcp` folder as
an absolute path; a wrong one rejects every resume as "outside allowed roots".
Set it in `.mcp.json` (Claude Code) and, if you will use Cowork, in
`cowork-plugin/.mcp.json` as well before building the plugin (§8).

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
4. **`profile/writing-style.md`** — the voice rules for anything written as
   you. The fact-checker reads all of it and runs its self-check list against
   every letter; `letter_linter` enforces a fixed subset in code (no em-dashes,
   no paragraph opening on "I", the closing "Thanks," and the fixed final
   sentence), so keep those or change the linter with them. The default is
   usable as-is; make it yours over time.
5. **`profile/standard_answers.md`** — contact block + stock screening answers.
6. **`profile/fit_profile.md`** — what a great role looks like for you.
7. **`profile/generate_resume.py`** — edit only the RESUME_DATA block.
8. **`profile/qa_checklist.md`** and **`profile/claims_ground_truth.md`** — grow
   these over time; the defaults work on day one.

Every path above is where the tooling looks when `profile.toml` has no
`[paths]` table. Keep any of them elsewhere by naming it there
(`inputs_dir`, `writing_style_path`, `claims_ground_truth_path`,
`resume_skill_path`); relative paths resolve against the repo root. Nothing
outside `profile.toml` may assume a layout, so the Claude-side prompts resolve
these paths through `job_apply.load_config()` rather than naming them.

**Do not skip 2–5.** The tailoring, fact-checking, and autofill workflows all
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
09:00 local. Test it once by hand first (`job-finder run --email` — this spends
real API tokens).

The task is registered with **`WakeToRun`**, which matters more than it sounds.
`StartWhenAvailable` is also on and covers a powered-off machine, but on
2026-08-31 the machine was merely **asleep** at 09:00 and no catch-up run ever
fired: 24 minutes after wake the task still reported one missed run and a next
run a week out. Sleep is the common case, so waking for the trigger is the fix.

Confirm afterwards with `job-finder status`, which prints the task's next run
and whether it will wake the machine.

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
packaged as a plugin in `cowork-plugin/`. Set `--output-dir` in
`cowork-plugin/.mcp.json` to this clone's absolute `.playwright-mcp` path (§2),
then build the archive:

```sh
python scripts/build_cowork_plugin.py
```

That writes `job-finder-cowork-plugin.zip` to your Downloads folder (`--out` to
put it elsewhere). Then, in Cowork: **Customize -> Plugins -> upload** it.
Uploading a plugin with the same `name` replaces the installed one.

**Install it; do not add `cowork-plugin/` as a context folder.** A connected
folder is just files on disk, so its `.mcp.json` never runs, Playwright never
starts, and the failure looks exactly like a broken plugin.

### Editing the plugin later: rebuild and re-upload, every time

**A correct file in `cowork-plugin/` does nothing until you rebuild the zip and
upload it again.** Cowork runs the snapshot it was given and keeps it
service-side, so nothing on your machine can compare the repo against what is
installed — `~/.claude/plugins/data/job-finder-inline/` is empty and
`.claude.json` holds only a usage counter.

That gap is not theoretical. On 2026-08-31 the repo's `.mcp.json` was correct and
the installed plugin was months older; every file upload was rejected, and seven
applications were filed with no resume and no cover letter attached.

Two checks exist, and you need both:

- **Bump `version` in `cowork-plugin/.claude-plugin/plugin.json` on every change
  that has to reach Cowork.** Cowork's plugin list shows the installed version, so
  the two side by side are a five-second drift check. `job-finder status` prints
  the repo's version for comparison. A version left alone across a rebuild throws
  this away.
- **The batch's preflight upload probe**, which uploads one throwaway file before
  drafting anything. It asks the running server rather than reading a file, so it
  is the only check that catches a stale install on its own.

Once installed, `/job-apply-weekly` runs the batch. It takes a count:
`/job-apply-weekly 3`, or `all`, defaulting to 5. The plugin is a launcher only
— the procedure it follows is `.claude/skills/job-apply-batch/SKILL.md` in this
repo, so **the repo still has to be the mounted folder for that session.**

Three things worth knowing before you rely on it:

- The plugin's `.mcp.json` is **required, not a duplicate of the repo-root one**.
  Cowork does not read a project's `.mcp.json`, so a plugin-bundled server is the
  only way it gets Playwright; the repo copy serves Claude Code. Keep the
  **Playwright version pin** identical in both (separate from the plugin's own
  `version` above).
- **`fill_greenhouse` does not run on Cowork.** The device VM has no `playwright`
  Python module, and a browser launched inside it is not one you can see or click,
  which defeats leaving tabs open for review. On Cowork every form goes through the
  autofill agent at roughly 63k tokens each, so that is a ceiling on how many roles
  one batch can carry. In Claude Code on Windows the script runs at about 2k.
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
job-finder status                          # did the last run work? both halves
python -m job_finder.profile_check         # is my profile complete?
job-finder review                          # interactive digest review
job-finder applied add --external-id ...   # record an application
python -m job_finder.fill_greenhouse \
    --url <apply url> --folder <per-app folder>   # deterministic fill (not on Cowork)
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
