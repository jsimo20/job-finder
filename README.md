# job-finder

A job-search system in three parts: it **finds** roles worth applying to,
**preps and fills** the applications (stopping short of Submit, always), and
**grades its own fills** so coverage improves with every batch. Everything
that defines "your search" — titles, industry, metros, identity — is
configuration, not code:

- **`config/pipeline.toml`** (committed) — target job titles and seniority
  band, metros, commute tiers, domain/stage weights, comp floor. Shipped
  defaults target senior product management roles in New England; edit every
  section for your own market.
- **`profile/`** (gitignored) — who you are: identity, EEO answers, stock
  screening answers, master resume, writing voice. Copied from
  `profile.example/`; `python -m job_finder.profile_check` verifies it's
  filled in.

New user? Follow **[SETUP.md](SETUP.md)** top to bottom — written so you can
hand it to a Claude Code session and let it drive.

## Find — the weekly digest

GitHub Actions (Mondays 13:00 UTC) collects postings from each tracked company's
public ATS endpoint (Greenhouse, Lever, Ashby), hard-filters on title,
seniority, and location, extracts structured signals with one Claude Haiku
call per surviving JD (YOE, comp, domains, onsite days), scores
deterministically, and emails a ranked Markdown digest with commute warnings.

The SQLite DB is rebuilt every run; durable state lives in committed JSONL
ledgers instead: `data/applied.jsonl` suppresses roles you've applied to
(including reposts, matched by company + title) and `data/seen.jsonl` drives
the digest's new-vs-carried-forward split. The `manage-companies` Claude skill
edits the company universe from plain English.

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

## Improve — the eval loop

Every fill captures before/after field inventories to `data/fill_audits/`.
Each batch ends with a letter-graded scorecard
(`python -m job_finder.fill_grader --date …`, zero tokens): what filled, what
missed, what had no configured answer. `/fill-review` turns that into
permanent improvements — wrong answers become code fixes with regression
tests, unanswered questions get asked once and stored in your profile, so
the next batch starts where the last one left off.

## Run

```bash
python -m job_finder.cli run             # full pipeline (spends API tokens)
python -m job_finder.cli review          # interactive picker: applied/dismissed
python -m job_finder.profile_check       # is my profile complete?
python -m job_finder.fill_grader --date <YYYY-MM-DD> --suggest
pytest                                    # no network, keys, or profile needed
```

Secrets (GitHub Actions): `ANTHROPIC_API_KEY`, `GMAIL_USER`,
`GMAIL_APP_PASSWORD` — see SETUP.md §6.

## Handing this repo to someone else

Never fork or plain-clone for a new user — git history carries the owner's
application log. Instead:

```bash
python scripts/export_clean_copy.py <target_dir>
```

which copies tracked files minus personal data and inits a fresh repo. The
recipient follows SETUP.md.
