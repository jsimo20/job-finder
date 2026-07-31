# CLAUDE.md — job-finder

Project-level instructions for Claude Code sessions in this repo. See `session-context.md` for current state and open threads.

## What this is

Cron-driven pipeline that surfaces Senior PM roles in Boston (and adjacent metros / remote-US). Runs weekly (Mondays 13:00 UTC) on GitHub Actions, emails the resulting digest to `GMAIL_USER`.

## Pipeline architecture

```
data/companies.json
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
- Durable state that must survive the rebuild lives in committed JSONL ledgers: `data/applied.jsonl` (applied suppression) and `data/seen.jsonl` (first-seen dates driving the digest's new-vs-carried split; `seen.py`). `daily.yml` commits both alongside digests. `first_seen_at` in the DB is always "now" and must never be used to distinguish new from carried.

## Key files

- `src/job_finder/settings.py` — loaders for `config/pipeline.toml` (committed knobs) and `profile/` (gitignored identity); `require_profile()` is the gate before any real form fill or render
- `config/pipeline.toml` — location scope, weights, filter knobs (committed, per-user)
- `profile/` / `profile.example/` — identity, EEO, driving docs (gitignored / template)
- `src/job_finder/cli.py` — entry point (`run` subcommand drives the pipeline)
- `src/job_finder/adapters/*.py` — one per ATS, each exports `fetch()` and `normalize()`
- `src/job_finder/extract.py` — Claude Haiku call, system prompt cached, defensive BOM/whitespace strip on `ANTHROPIC_API_KEY`
- `src/job_finder/filter.py` — hard filter rules (Stage 1 + Stage 3)
- `src/job_finder/score.py` — deterministic scoring
- `src/job_finder/review.py` — interactive picker for the CLI `review` subcommand
- `src/job_finder/form_inventory.py` — ATS-agnostic form field inventory (label/type/required/value/options per control) plus the audit-manifest writer; shared by the deterministic filler and the autofill agent
- `data/companies.json` — 406-company tracked list across GH + Lever + Ashby
- `.github/workflows/daily.yml` — cron `0 13 * * 1` (weekly), runs pipeline + emails digest, commits digests + both JSONL ledgers
- `.github/workflows/claude-review.yml` — Claude PR reviewer, fires on `.py` / `.claude/**` / `claude-review.yml` PRs

## Commands

```sh
# Run tests (should all pass; ~180 and growing)
.venv/Scripts/python.exe -m pytest -q

# Run pipeline locally — MAKES REAL CLAUDE API CALLS, don't run casually
.venv/Scripts/python.exe -m job_finder.cli run

# Interactive review picker
.venv/Scripts/job-finder.exe review
# Other subcommands: mark-applied <external_id>, dismiss <external_id>, unmark <external_id>
# external_id = gh_jid for Greenhouse, slug for Lever, id for Ashby
```

## Per-user configuration (two layers)

- **`config/pipeline.toml`** — committed. Location scope, metro tiers, commute thresholds/notes, domain + stage weights, comp floor, YoE cap, stale days. `settings.pipeline_config()` loads it; `taxonomy.py` and `filter.py` are thin views over it. CI reads it, so per-user pipeline preferences MUST go here, never in a gitignored file.
- **`profile/`** — gitignored. Identity, EEO answers, `[paths]` to the driving docs, fit profile, QA checklist, the resume generator. `settings.load_profile()` falls back to the committed `profile.example/` so imports and tests work on a fresh clone; anything that acts on the values (form fill, PDF render) goes through `settings.require_profile()` and refuses the example.
- Handing the repo to a new user: plain `git clone`; SETUP.md §1 resets the owner's ledgers and digests. History is scrubbed of PII and MUST stay that way — no personal data in commits, ever; the committed ledgers are the only owner-specific tracked state.

## Location scope and the commute warning

The committed config encodes the owner's home base and a deliberately different target metro; `standard_answers.md` may state the target metro as the location on purpose — that is positioning, not an error, so never "fix" it. The actual metro regexes, tiers, and warning text live in `config/pipeline.toml [location]`.

- **In scope** (`filter.stage1`, via `in_scope_patterns`): Boston metro, NYC metro, all of CT, RI/Providence, western + central MA, southern NH, Albany, any "East Coast"/"Northeast" phrasing, and any US-remote role.
- **Metro tiers** (`filter.metro_tier`) are drive time from the configured home base, defined in `config/pipeline.toml [location.tiers]`. Checked far-first, because a far-metro string like "Boston, MA" also matches the state tokens that place near-metro cities.
- **`filter.commute_warning`** flags `far` + 4-5 days onsite, and `mid` + 5 days. It **warns, never discards** — days-per-week is often negotiable and postings misstate it. Surfaced in the digest as a `⚠️ Commute:` line.
- Depends on `onsite_days_per_week` from extraction (0-5 or null; null means the JD said nothing, and never warns). Validated at the boundary by `extract._clamp_days`, since the field feeds a user-facing warning.

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
- **Commit subjects and PR titles are one plain sentence stating what the change does** — imperative, lowercase start, no `type(scope):` prefixes, no "Type of change" checklists. The body (optional) explains why.
- **PRs are the norm**, not direct-to-main. The reviewer fires on `.py` / `.claude/**` paths. Non-Python YAML/Markdown changes (e.g., `daily.yml`) bypass the path filter — still PR them for the audit trail, expect the reviewer to no-op.
- **Reviewer can't review changes to its own workflow file** (`claude-review.yml`) due to `anthropics/claude-code-action@v1`'s self-modification guard. Self-merge those after careful local review.

## Apply workflow (slash commands)

- `/job-apply [external_id | --top N]` — tailors resume + cover letter for pending roles, runs the materials fact-checker, renders the per-job folder via `job_apply.render()`, then dispatches autofill. Logic in `.claude/commands/job-apply.md`; deterministic render in `src/job_finder/job_apply.py`.
- `/fill-application <url> [folder]` — standalone Playwright autofill via the `application-autofiller` subagent. Stops without submitting; the user reviews and submits by hand. Logic in `.claude/commands/fill-application.md`.
- **Greenhouse forms: prefer the deterministic script** over the agent — `python -m job_finder.fill_greenhouse --url <url> --folder <per-app folder> [--city <city>]`. Fills the standard section (contact, auth, EEO, uploads) with zero LLM tokens, DOM-verifies every dropdown commit, prints a fill report, holds the browser open for review, never submits. ~2k tokens vs ~63k for the agent. One-time setup: `pip install -e .[apply]` + `playwright install chromium` (local only; CI never needs it). The agent stays as the fallback for unknown ATSes and custom questions.
- Field values come from `profile/profile.toml` (identity, EEO, work-auth stance) plus `standard_answers.md` in the configured `inputs_dir` (`profile/profile.toml [paths]`; may point at a cloud-synced folder outside the repo).
- **Grade every fill batch**: `python -m job_finder.fill_grader --date <YYYY-MM-DD>` letter-grades the audit manifests (Layer 1, zero tokens). Its `no_rule` output is the backlog — turn entries into `[[custom_combos]]` answers in `profile/profile.toml`. `python -m job_finder.profile_check` is the profile doctor (placeholder/missing-doc detection); SETUP.md tells new users to run it.
- **Every fill captures a before/after field inventory** to `data/fill_audits/<date>_<slug>.{pre,post}.json` (gitignored — the `value` column holds contact details). Both fill paths use `form_inventory.py` so their output is comparable; the deterministic script writes them directly, the agent via `browser_evaluate`. Capture is best-effort and never blocks a fill. Redact with `form_inventory.redact()` before promoting a manifest to `tests/fixtures/`. Design: `.claude/context/form-fill-evals.md`.
- **Playwright MCP is project-scoped** (`.mcp.json`). Its `mcp__playwright__*` tools only load when the Claude session is rooted in this directory — autofill won't work from a session started in the parent `dev/` directory.
- **Batch autofill = one Chrome instance, one tab per app** (never a separate browser per app). Dispatch a single `application-autofiller` with the full list of `(url, folder)` pairs; it opens each app in a new tab and leaves them all open, unsubmitted, for review. Rule lives in the Batch mode section of `.claude/agents/application-autofiller.md`.

## Project-level skills

- `.claude/skills/manage-companies/SKILL.md` — add/remove/probe companies in `data/companies.json` from plain-English instructions, without manual JSON editing.

## Subagents

`.claude/agents/` — dispatched from slash commands or directly via the `Agent` tool. Each pins its own model and tool list. The Sonnet subagents below handle mechanical work so the main Opus-tier conversation keeps focus on voice and judgment.

| Subagent | Purpose | Model |
|---|---|---|
| `digest-triager` | Reads latest digest, ranks pending roles against fit profile, returns ranked picks | Sonnet |
| `materials-fact-checker` | Cross-checks drafted RESUME_DATA + cover letter against ground-truth files; severity-tagged findings | Sonnet |
| `application-autofiller` | Drives Playwright MCP through the application form; stops before submit | Sonnet |
| `python-code-reviewer` | PR review on `.py` / `.claude/**` changes; fires via `claude-review.yml` and `/review` | Opus |

## Outreach log

Tracks people the user contacts on LinkedIn (name + company + date + optional role/context). Separate from the pipeline and the digest on purpose: not every contact is tied to a role application (outreach is often for an internal referral), and the DB gets wiped every run so it can't hold durable state.

- **Store:** `data/outreach.jsonl` — append-only, **gitignored** (third-party names are PII; local-only, does not sync across machines). Untouched by the pipeline.
- **Module:** `src/job_finder/outreach.py` — `add_contact()`, `list_contacts(company=…)`, `format_contacts()`.
- **CLI:**
  ```sh
  job-finder outreach add --name "First Last" --company "Example Co" [--role "…"] [--type connection-request|message|hm-message] [--notes "…"] [--date YYYY-MM-DD]
  job-finder outreach list [--company exampleco]
  job-finder outreach remove --name "First Last" --company "Example Co"   # exact name+company, case-insensitive
  ```

**Agent trigger (do this automatically):** whenever the user asks you to draft a LinkedIn message or connection request for someone, log it with `outreach add` afterward. **Always get the person's name and their company from the user** before logging — ask if either is missing. Default `--type` to `connection-request`, or `hm-message` for a hiring-manager message. This keeps a recall-able record of who they talked to, when, and where they work.

## Applied log

Durable record of roles applied to, keyed by `external_id`. Fixes the fact that `data/jobs.db` (and its `applied_at` flag) is rebuilt every run, so applied roles otherwise resurface in the next digest. Also captures **ad-hoc roles** applied to outside the pipeline (pasted URLs never in the tracked-company list), which the DB never knew about.

- **Store:** `data/applied.jsonl` — append-only, **committed** (unlike the outreach log). It must be in git so the CI-generated digest can read it to suppress already-applied roles. Contents are the owner's own application records (no third-party PII), fine for a private repo.
- **Module:** `src/job_finder/applied.py` — `record_applied()`, `list_applied()`, `is_applied(external_id=…, url=…)`, `applied_external_ids()`, `remove_applied()`. URL matching normalizes scheme/query/trailing `/apply`/`/application` so a pasted apply-form link matches the posting.
- **Digest integration:** `digest.render()` drops any row whose `external_id` is in the log (both new and carried-forward, main and stretch queues).
- **CLI:**
  ```sh
  job-finder applied add --external-id 1234567 --company "Example Co" --title "Senior Product Manager" [--url …] [--date YYYY-MM-DD] [--source …]
  job-finder applied list [--company exampleco]
  job-finder applied check 1234567        # or a full posting/apply URL → "APPLIED" / "not applied"
  job-finder applied remove --external-id 1234567   # drop a role you decided not to submit
  ```
  `mark-applied <external_id>` also writes to this log automatically (pulling company/title/url from the DB row). For ad-hoc roles with no DB row, use `applied add`.

**Agent trigger:** when the user applies to (or has you prep+fill) any role — especially ad-hoc ones pasted directly — record it with `applied add`. When they ask "have we applied to X?", answer with `applied check`.

## Reviewer rubric

`.claude/agents/python-code-reviewer.md` defines what the PR reviewer looks for. Severity-tagged findings (CRITICAL/HIGH/MEDIUM/LOW/NIT). On-demand context files in `.claude/context/`:
- `google-python-style.md` — loaded for `.py` reviews
- `ai-agent-security.md` — loaded for files under `agents/`, `tools/`, `mcp/`, `prompts/` or importing `anthropic`/`openai`/`langchain`
- `pr-review-checklist.md` — the working checklist
