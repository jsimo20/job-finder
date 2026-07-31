# Setup — new user

Step-by-step setup for a fresh clone. Written so you can paste it into a
Claude Code session ("follow SETUP.md") and have it drive; every step also
works by hand. Nothing here requires the original owner's files: all personal
context lives in two places you create yourself — `config/pipeline.toml`
(committed preferences) and `profile/` (gitignored identity).

## 0. Prerequisites

- Python 3.12+
- `git`, and the `gh` CLI logged into your GitHub account
- `uv` (`pip install uv`) — or plain pip, adjusting the commands below
- An Anthropic API key with credit (console.anthropic.com) — the pipeline's
  extraction stage and the optional PR reviewer both bill against it
- A Gmail account with 2FA, for the digest email

## 1. Get a copy

```sh
git clone <repo-url> my-job-finder && cd my-job-finder
```

Then point it at your own private GitHub repo and reset the owner's search
state — the ledgers and digest archive are theirs, not yours:

```sh
git remote set-url origin git@github.com:<your-user>/my-job-finder.git
: > data/applied.jsonl
: > data/seen.jsonl
git rm -rq digests/ && mkdir digests
git commit -am "reset search state for new owner"
gh repo create <your-user>/my-job-finder --private --source=. --push
```

(`data/no_auto_apply.json` ships empty; `data/companies.json` you'll rebuild
in §5.)

## 2. Install

```sh
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install uv
uv pip install -e ".[dev]"
```

The browser-autofill workflow (optional, local-only — CI never needs it):

```sh
uv pip install -e ".[apply]"
playwright install chromium
```

Sanity check — the suite must pass on a fresh clone with no profile:

```sh
python -m pytest -q
```

To run the pipeline locally (optional — CI normally runs it), create a
`.env` at the repo root with one line:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Nothing else goes in it; email credentials only exist as GitHub secrets (§6).

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
7. **`profile/qa_checklist.md`** and **`profile/session_context.md`** — grow
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

Edit **`config/pipeline.toml`** (this one IS committed — CI reads it):

- `[location]` — replace the metro regexes with your own target geography,
  and the commute tiers/notes with drive times from where you live.
- `[domains.*]` / `[stages.*]` — reweight to your background; definitions
  feed the extraction prompt, so keep them concrete.
- `[filters]` — your comp floor and years-of-experience cap.

- `[titles]` — which job titles count as target roles, adjacent tracks to
  exclude, and the seniority band. This is the industry knob: replace the
  product-management defaults with your own market's title patterns.
- `[extraction]` — the role noun the extraction prompt speaks about.

## 5. Build your company list

`data/companies.json` ships with the previous owner's ~400 New England
companies. Replace it with companies in your own market. The
`.claude/skills/manage-companies` skill adds/removes/probes companies from
plain-English instructions in a Claude Code session; the format is plain JSON
if you'd rather script it.

## 6. GitHub Actions secrets

In your repo: Settings → Secrets and variables → Actions →

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | from console.anthropic.com (paste via a plain-text editor — invisible BOMs from rich editors break the SDK) |
| `GMAIL_USER` | your Gmail address (auth user AND digest recipient) |
| `GMAIL_APP_PASSWORD` | 16-char app password from myaccount.google.com/apppasswords (requires 2FA) |

The digest workflow (`.github/workflows/daily.yml`) runs Mondays 13:00 UTC;
trigger a first run manually from the Actions tab (workflow_dispatch). The PR
reviewer (`.github/workflows/claude-review.yml`) works as-is once
`ANTHROPIC_API_KEY` is set — delete that file if you don't want it.

## 7. Personalize the Claude-side prompts

If you use the Claude Code workflows, three files still describe the previous
owner's rules and should be regenerated from YOUR profile docs (a Claude
session can do this: "rewrite these against my profile/ files"):

- `.claude/agents/materials-fact-checker.md` §§1–4 — metric baselines and
  banned framings specific to the owner's resume
- `.claude/commands/job-apply.md` — workflow is generic, skim for fit
- `CLAUDE.md` — rewrite the project instructions for your own setup

## 8. What never goes in git

Already handled by `.gitignore`, listed so you don't fight it: `profile/`,
`.env`, `data/jobs.db` (rebuilt every run), `data/outreach.jsonl` (third-party
PII), `data/fill_audits/` (captured form values). `data/applied.jsonl` IS
committed — it's your own application log and the digest needs it in CI to
suppress roles you've already applied to.

## Day-to-day commands

```sh
python -m pytest -q                              # tests
python -m job_finder.profile_check         # is my profile complete?
job-finder review                          # interactive digest review
job-finder applied add --external-id ...   # record an application
python -m job_finder.fill_greenhouse \
    --url <apply url> --folder <per-app folder>   # deterministic form fill
python -m job_finder.fill_grader --date <YYYY-MM-DD>   # grade a fill batch
```

After every fill batch, run the grader on that date's audit manifests. It
letter-grades each form (missed fields, environment failures, critical
violations like a wrong sponsorship answer) and its `no_rule` list is your
backlog: each entry becomes a new `[[custom_combos]]` answer in
`profile/profile.toml`, so coverage compounds batch over batch.

The pipeline itself (`job-finder run`) normally only runs in CI — it
spends real Anthropic tokens, so avoid running it casually on a laptop.
