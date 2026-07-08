# CLAUDE.md — boston-pm-tracker

Project-level instructions for Claude Code sessions in this repo. See `session-context.md` for current state and open threads.

## What this is

Cron-driven pipeline that surfaces Senior PM roles in Boston (and adjacent metros / remote-US). Runs every 3 days on GitHub Actions, emails the resulting digest to `GMAIL_USER`.

## Pipeline architecture

```
seeds/companies.json
    ↓
collect (adapters/{greenhouse,lever,ashby}.py)  →  postings table
    ↓
Stage 1 filter (filter.py)                       →  hard_filter_verdict
    ↓
extract (Claude Haiku, one call per kept role)  →  extractions table
    ↓
Stage 3 filter + score (score.py)               →  scoring table
    ↓
digest (digest.py, jinja2)                       →  digests/YYYY-MM-DD.md
```

## Stack

- Python 3.12. Deps: httpx, anthropic, jinja2, beautifulsoup4, python-dotenv. Install via `uv pip install --system -e .`.
- SQLite at `data/jobs.db` — gitignored, rebuilt every pipeline run. Applied/dismissed state is local-only by design (CI rebuilds the DB, doesn't preserve state across runs).

## Key files

- `src/boston_pm_tracker/cli.py` — entry point (`run` subcommand drives the pipeline)
- `src/boston_pm_tracker/adapters/*.py` — one per ATS, each exports `fetch()` and `normalize()`
- `src/boston_pm_tracker/extract.py` — Claude Haiku call, system prompt cached, defensive BOM/whitespace strip on `ANTHROPIC_API_KEY`
- `src/boston_pm_tracker/filter.py` — hard filter rules (Stage 1 + Stage 3)
- `src/boston_pm_tracker/score.py` — deterministic scoring
- `src/boston_pm_tracker/review.py` — interactive picker for the CLI `review` subcommand
- `seeds/companies.json` — 398-company seed across GH + Lever + Ashby
- `.github/workflows/daily.yml` — cron `0 13 */3 * *`, runs pipeline + emails digest
- `.github/workflows/claude-review.yml` — Claude PR reviewer, fires on `.py` / `.claude/**` / `claude-review.yml` PRs

## Commands

```sh
# Run tests (47 tests, should all pass)
.venv/Scripts/python.exe -m pytest -q

# Run pipeline locally — MAKES REAL CLAUDE API CALLS, don't run casually
.venv/Scripts/python.exe -m boston_pm_tracker.cli run

# Interactive review picker
.venv/Scripts/boston-pm-tracker.exe review
# Other subcommands: mark-applied <external_id>, dismiss <external_id>, unmark <external_id>
# external_id = gh_jid for Greenhouse, slug for Lever, id for Ashby
```

## Secrets (GitHub Actions)

| Secret | Used by | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | extract.py, claude-review.yml | Paste cleanly via Notepad to avoid BOM corruption (see Gotchas) |
| `GMAIL_USER` | Email step | Gmail address; used as both SMTP auth user and recipient |
| `GMAIL_APP_PASSWORD` | Email step | 16-char app password from https://myaccount.google.com/apppasswords (requires 2FA) |

## Gotchas

- **`data/jobs.db` is gitignored** and rebuilt every CI run. Never `git add` it in a workflow step — `git add` of a gitignored path exits 1 and fails the job.
- **BOMs in Python source**: use `chr(0xfeff)` constants, never literal BOM characters. Source-file encoding can corrupt the literal between Windows editors and Linux runners. See `_BOM = chr(0xfeff)` patterns in `extract.py`, `ashby.py`, `lever.py`.
- **Defensive `.strip().replace(_BOM, "")` on env-var reads** in `extract.py` — pasted secrets can carry invisible BOMs that crash SDK header construction. Already in place.
- **Don't auto-run the pipeline locally** to test changes — it spends real Anthropic + Gmail tokens (~$$). Prefer targeted unit tests via pytest.
- **PRs are the norm**, not direct-to-main. The reviewer fires on `.py` / `.claude/**` paths. Non-Python YAML/Markdown changes (e.g., `daily.yml`) bypass the path filter — still PR them for the audit trail, expect the reviewer to no-op.
- **Reviewer can't review changes to its own workflow file** (`claude-review.yml`) due to `anthropics/claude-code-action@v1`'s self-modification guard. Self-merge those after careful local review.

## Apply workflow (slash commands)

- `/job-apply [external_id | --top N]` — tailors resume + cover letter for pending roles, runs the materials fact-checker, renders the per-job folder via `job_apply.render()`, then dispatches autofill. Logic in `.claude/commands/job-apply.md`; deterministic render in `src/boston_pm_tracker/job_apply.py`.
- `/fill-application <url> [folder]` — standalone Playwright autofill via the `application-autofiller` subagent. Stops without submitting; James reviews and submits by hand. Logic in `.claude/commands/fill-application.md`.
- **Greenhouse forms: prefer the deterministic script** over the agent — `python -m boston_pm_tracker.fill_greenhouse --url <url> --folder <per-app folder> [--city <city>]`. Fills the standard section (contact, auth, EEO, uploads) with zero LLM tokens, DOM-verifies every dropdown commit, prints a fill report, holds the browser open for review, never submits. ~2k tokens vs ~63k for the agent. One-time setup: `pip install -e .[apply]` + `playwright install chromium` (local only; CI never needs it). The agent stays as the fallback for unknown ATSes and custom questions.
- Field values come from `~/path/to/job-search/inputs/standard_answers.md`.
- **Playwright MCP is project-scoped** (`.mcp.json`). Its `mcp__playwright__*` tools only load when the Claude session is rooted in this directory — autofill won't work from a session started in the parent `dev/` directory.
- **Batch autofill = one Chrome instance, one tab per app** (never a separate browser per app). Dispatch a single `application-autofiller` with the full list of `(url, folder)` pairs; it opens each app in a new tab and leaves them all open, unsubmitted, for review. Rule lives in the Batch mode section of `.claude/agents/application-autofiller.md`.

## Project-level skills

- `.claude/skills/manage-seeds/SKILL.md` — add/remove/probe companies in `seeds/companies.json` from plain-English instructions, without manual JSON editing.

## Subagents

`.claude/agents/` — dispatched from slash commands or directly via the `Agent` tool. Each pins its own model and tool list. The Sonnet subagents below handle mechanical work so the main Opus-tier conversation keeps focus on voice and judgment.

| Subagent | Purpose | Model |
|---|---|---|
| `digest-triager` | Reads latest digest, ranks pending roles against fit profile, returns ranked picks | Sonnet |
| `materials-fact-checker` | Cross-checks drafted RESUME_DATA + cover letter against ground-truth files; severity-tagged findings | Sonnet |
| `application-autofiller` | Drives Playwright MCP through the application form; stops before submit | Sonnet |
| `python-code-reviewer` | PR review on `.py` / `.claude/**` changes; fires via `claude-review.yml` and `/review` | Opus |

## Outreach log

Tracks people James contacts on LinkedIn (name + company + date + optional role/context). Separate from the pipeline and the digest on purpose: not every contact is tied to a role application (he often reaches out for an internal referral), and the DB gets wiped every run so it can't hold durable state.

- **Store:** `data/outreach.jsonl` — append-only, **gitignored** (third-party names are PII; local-only, does not sync across machines). Untouched by the pipeline.
- **Module:** `src/boston_pm_tracker/outreach.py` — `add_contact()`, `list_contacts(company=…)`, `format_contacts()`.
- **CLI:**
  ```sh
  boston-pm-tracker outreach add --name "Contact-A" --company "ZoomInfo" [--role "…"] [--type connection-request|message|hm-message] [--notes "…"] [--date YYYY-MM-DD]
  boston-pm-tracker outreach list [--company zoominfo]
  boston-pm-tracker outreach remove --name "Contact-C" --company "Axon"   # exact name+company, case-insensitive
  ```

**Agent trigger (do this automatically):** whenever James asks you to draft a LinkedIn message or connection request for someone, log it with `outreach add` afterward. **Always get the person's name and their company from James** before logging — ask if either is missing. Default `--type` to `connection-request`, or `hm-message` for a hiring-manager message. This keeps a recall-able record of who he talked to, when, and where they work.

## Applied log

Durable record of roles applied to, keyed by `external_id`. Fixes the fact that `data/jobs.db` (and its `applied_at` flag) is rebuilt every run, so applied roles otherwise resurface in the next digest. Also captures **ad-hoc roles** applied to outside the pipeline (pasted URLs never in the seed set), which the DB never knew about.

- **Store:** `data/applied.jsonl` — append-only, **committed** (unlike the outreach log). It must be in git so the CI-generated digest can read it to suppress already-applied roles. Contents are James's own application records (no third-party PII), fine for a private repo.
- **Module:** `src/boston_pm_tracker/applied.py` — `record_applied()`, `list_applied()`, `is_applied(external_id=…, url=…)`, `applied_external_ids()`, `remove_applied()`. URL matching normalizes scheme/query/trailing `/apply`/`/application` so a pasted apply-form link matches the posting.
- **Digest integration:** `digest.render()` drops any row whose `external_id` is in the log (both new and carried-forward, main and stretch queues).
- **CLI:**
  ```sh
  boston-pm-tracker applied add --external-id 8030599 --company Datadog --title "Senior PM - Agent Integrations" [--url …] [--date YYYY-MM-DD] [--source …]
  boston-pm-tracker applied list [--company datadog]
  boston-pm-tracker applied check 8030599        # or a full posting/apply URL → "APPLIED" / "not applied"
  ```
  `mark-applied <external_id>` also writes to this log automatically (pulling company/title/url from the DB row). For ad-hoc roles with no DB row, use `applied add`.

**Agent trigger:** when James applies to (or has you prep+fill) any role — especially ad-hoc ones pasted directly — record it with `applied add`. When he asks "have we applied to X?", answer with `applied check`.

## Reviewer rubric

`.claude/agents/python-code-reviewer.md` defines what the PR reviewer looks for. Severity-tagged findings (CRITICAL/HIGH/MEDIUM/LOW/NIT). On-demand context files in `.claude/context/`:
- `google-python-style.md` — loaded for `.py` reviews
- `ai-agent-security.md` — loaded for files under `agents/`, `tools/`, `mcp/`, `prompts/` or importing `anthropic`/`openai`/`langchain`
- `pr-review-checklist.md` — the working checklist
