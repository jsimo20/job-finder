# pm-tracker (boston-pm-tracker)

Cron-driven pipeline that tracks senior Product Manager roles at a curated set
of companies, scores them against a configurable profile, and emails a ranked
Markdown digest. A second, local-only half tailors application materials and
autofills forms — always stopping short of Submit.

All personal context is configurable:

- **`config/pipeline.toml`** (committed) — target metros, commute tiers,
  domain/stage weights, comp floor. Edit for your own search.
- **`profile/`** (gitignored) — who you are: identity, EEO answers, master
  resume, writing voice. Copied from `profile.example/`.

New user? Follow **[SETUP.md](SETUP.md)** top to bottom — it's written so you
can hand it to a Claude Code session and let it drive.

## How the pipeline works

1. **Collect** — hit each seed company's public ATS endpoint (Greenhouse,
   Lever, Ashby) and normalize postings.
2. **Stage 1 hard filters** — discard wrong title, wrong location, wrong
   seniority (geography from `config/pipeline.toml`).
3. **Extract** — one Claude Haiku call per surviving JD returns structured
   JSON (YOE, comp range, domain tags, company stage, onsite days).
4. **Stage 3 hard filters** — comp floor, YOE routing to main vs stretch.
5. **Score** — deterministic scorer sums the configured domain + stage + comp
   weights.
6. **Digest** — render Markdown to `digests/YYYY-MM-DD.md`, sorted by score,
   with commute warnings for distant-but-heavy-onsite roles.

State lives in `data/jobs.db` (SQLite, gitignored, rebuilt every run).
Roles you've applied to are suppressed via the committed `data/applied.jsonl`
log. Stale postings (older than `stale_days`) are dropped as likely
evergreen reqs.

## Run

```bash
python -m boston_pm_tracker.cli run             # full pipeline (spends API tokens)
python -m boston_pm_tracker.cli review          # interactive picker: applied/dismissed
boston-pm-tracker applied add --external-id …   # record an ad-hoc application
boston-pm-tracker outreach add --name … --company …   # log a LinkedIn contact
```

GitHub Actions runs the pipeline weekly (Mondays 13:00 UTC) and emails the
digest; see SETUP.md §6 for the three required secrets.

## Apply workflow (Claude Code, local-only)

- `/job-apply` — conversational loop: pick a role, review a tailored
  RESUME_DATA diff + cover-letter draft (fact-checked against your
  `profile/resume_master.md`), render a per-job folder of PDFs.
- `/fill-application <url> [folder]` — agent-driven Playwright autofill for
  any ATS. Stops before Submit, always.
- **Greenhouse forms: prefer the deterministic script** — zero LLM tokens:

  ```bash
  python -m boston_pm_tracker.fill_greenhouse --url <url> --folder <per-app folder>
  ```

  Identity, work-authorization stance, and EEO answers come from
  `profile/profile.toml`; it refuses to run until that file exists. Salary
  fields are always left blank. Every fill captures a before/after field
  inventory to `data/fill_audits/` (gitignored).

## Editing the company universe

- **Manually**: edit `seeds/companies.json` (`name`, `ats_provider`,
  `ats_slug`).
- **Via Claude**: the [manage-seeds skill](.claude/skills/manage-seeds/SKILL.md)
  handles add / remove / probe / audit from plain English.

## Tests

```bash
pytest
```

154 tests, no network, no API keys, no profile required — they must pass on a
fresh clone.

## Handing this repo to someone else

Never fork or plain-clone for a new user — git history carries the owner's
application log. Instead:

```bash
python scripts/export_clean_copy.py <target_dir>
```

which copies tracked files minus personal data and inits a fresh repo. The
recipient then follows SETUP.md.
