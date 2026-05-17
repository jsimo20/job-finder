# boston-pm-tracker

Daily, deterministic pipeline that tracks Senior+ Product Manager roles at a curated
set of companies (Boston metro, NYC, Hartford, or fully remote US) and produces a
ranked Markdown digest of new / closed / changed postings.

## How it works

1. **Collect** — hit each company's public ATS endpoint (Greenhouse, Lever) and
   normalize postings.
2. **Stage 1 hard filters** — discard wrong title, wrong location, wrong seniority.
3. **Extract (agentic)** — for each surviving JD, one Claude Haiku call returns
   structured JSON (YOE, comp range, domain tags, company stage, etc.).
4. **Stage 3 hard filters** — comp floor, YOE routing.
5. **Score** — deterministic scorer weights domain + stage + comp signals.
6. **Digest** — render today's Markdown to `digests/YYYY-MM-DD.md`, sorted by score.

State lives in `data/jobs.db` (SQLite, committed). Closed-role inference is by
feed absence — a posting present yesterday but absent today is marked closed.

Stale roles (likely resume-fishing reqs) are excluded from the digest. A role is
considered stale if its source-side posted timestamp (Greenhouse `first_published`,
Lever `createdAt`) is more than `STALE_DAYS` (30) old. If the source doesn't expose
a timestamp, we fall back to our own `first_seen_at`.

## Setup

```bash
uv venv && uv pip install -e ".[dev]"
cp .env.example .env  # add ANTHROPIC_API_KEY
python -m boston_pm_tracker.cli init-db
```

## Run

```bash
python -m boston_pm_tracker.cli run        # full pipeline: collect → extract → score → digest
python -m boston_pm_tracker.cli collect    # ATS fetch only
python -m boston_pm_tracker.cli extract    # Claude extraction on new postings
python -m boston_pm_tracker.cli score      # deterministic scoring
python -m boston_pm_tracker.cli digest     # render today's markdown
```

## Tests

```bash
pytest
```

## Schedule

GitHub Actions runs the full pipeline daily at 13:00 UTC and commits `data/jobs.db`
and `digests/*.md` back to `main`. Manual trigger via `workflow_dispatch`.

## Editing the company universe

Edit `seeds/companies.json`. Each row needs `name`, `ats_provider`
(`greenhouse` | `lever`), and `ats_slug` (verify by visiting the public board).
