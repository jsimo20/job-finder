# CLAUDE.md — job-finder

Project-level instructions for Claude Code sessions in this repo. See `session-context.md` for current state and open threads.

## What this is

Local-first pipeline that surfaces target roles and emails a weekly digest. Runs as a Windows Scheduled Task (Mondays 09:00 local, `job-finder run --email`); nothing personal lives in the repo or any cloud — the repo is pure engine.

## Pipeline architecture

```
companies table (data/state.db)
    ↓
collect (adapters/{greenhouse,lever,ashby,workday}.py)  →  postings table
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
- SQLite at `data/jobs.db` — gitignored, ephemeral, rebuilt every pipeline run.
- Company tiers: `greenhouse`/`lever`/`ashby`/`workday` rows are polled by collect; `manual` rows (no pollable ATS — SuccessFactors, Phenom, iCIMS, Eightfold, custom sites) carry only a careers URL and surface in the digest's **Manual check** section for a weekly hand check.
- **Per-company freshness override:** `companies.max_age_days` narrows the digest for one company below the global `STALE_DAYS` — set it on high-volume boards worth watching but not worth re-reading (`companies add --max-age-days 14`). Applied in `digest.drop_stale_for_company()`, which **fails closed**: an override company's posting with no `posted_at` is dropped, because `first_seen_at` is always "now" and would defeat the filter.
- Durable state lives in `data/state.db` (gitignored SQLite; `state.py`): tracked companies, no-auto-apply blocklist, applied ledger, seen ledger, digest archive. `first_seen_at` in jobs.db is always "now" and must never be used to distinguish new from carried — that's the seen table's job. Manage via `job-finder companies|no-auto|applied|digest-archive`; never edit the DB files directly, and never commit anything under `data/` or `digests/`.

## Key files

- `src/job_finder/settings.py` — loaders for `config/pipeline.toml` (committed knobs) and `profile/` (gitignored identity); `require_profile()` is the gate before any real form fill or render
- `config/pipeline.toml` — location scope, weights, filter knobs (committed, per-user)
- `profile/` / `profile.example/` — identity, EEO, driving docs (gitignored / template)
- `src/job_finder/cli.py` — entry point (`run` subcommand drives the pipeline)
- `src/job_finder/adapters/*.py` — one per ATS, each exports `fetch()` and `normalize()`; workday also exports `fetch_detail()` (its list payload has no JD, so collect enriches Stage-1 survivors only; slug format `tenant/wdN/site`)
- `src/job_finder/extract.py` — Claude Haiku call, system prompt cached, defensive BOM/whitespace strip on `ANTHROPIC_API_KEY`
- `src/job_finder/filter.py` — hard filter rules (Stage 1 + Stage 3)
- `src/job_finder/score.py` — deterministic scoring
- `src/job_finder/review.py` — interactive picker for the CLI `review` subcommand
- `src/job_finder/form_inventory.py` — ATS-agnostic form field inventory (label/type/required/value/options per control) plus the audit-manifest writer; shared by the deterministic filler and the autofill agent
- `data/state.db` — all durable personal state (see above); `config/companies.example.json` is the neutral starter list

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

## Evals

Two deterministic zero-token graders plus one that spends tokens. They read
artifacts the system already produces rather than running a parallel harness,
and each has a bucket that is a backlog rather than a failure.

```sh
# Does the score predict what actually gets applied to?
.venv/Scripts/python.exe -m job_finder.eval_calibration
# Did the last fill batch fill everything it had a rule for?
.venv/Scripts/python.exe -m job_finder.fill_grader --date <YYYY-MM-DD>
# Refuse the batch instead of describing it (unattended runs)
.venv/Scripts/python.exe -m job_finder.fill_grader --date <YYYY-MM-DD> --gate
# Does the fact-checker catch a defect planted on purpose? (spends tokens)
.venv/Scripts/python.exe -m job_finder.eval_factcheck
```

**Interactive runs are graded after the fact; unattended runs have to be able
to refuse.** `/job-apply` puts five human approval gates between a defect and a
submitted application. Remove those and the only things left are the
fact-checker and `--gate`, which is why both are measured rather than trusted.

- **`eval_calibration.py`** grades the scorer against the applied ledger. The
  digest archive in `state.db` is the only durable record of what a role scored
  (jobs.db is rebuilt every run), so it reconstructs scores by parsing archived
  digest bodies. Outputs precision@k against a per-digest chance baseline, apply
  rate per score band, and per-signal lift. **A signal with high lift and a low
  weight in `config/pipeline.toml` is an underweighted signal** — that table is
  the actionable output. Read-only; safe to run any time.
- **Reweighting `pipeline.toml` invalidates archive comparisons.** Scores are
  additive, so `eval_calibration` recomputes every archived entry under today's
  weights and warns when they don't reproduce. Digests either side of a reweight
  aren't comparable, and a signal whose weight was raised in response to past
  behaviour will show high lift for that reason alone. Read the warning before
  trusting the lift table.
- **`fill_grader.py`** grades form fills; design in `.claude/context/form-fill-evals.md`.
  `--gate` turns it into a check both fill agents run before reporting: **0**
  ready, **4** critical violation, **3** nothing to grade because no form was
  filled. 3 and 4 are separate because an unattended caller cannot act on
  "nothing happened" and "every form was unsafe" the same way, and both stay
  clear of argparse's own exit 2.
  Critical now includes **prompt-injection suspects**: `INJECTION_PATTERN` scans
  each field's label, options and value for text addressed to the agent rather
  than the applicant. Both agents already carry a prompt rule saying page
  content is data — this is the same rule in code, so an unattended run cannot
  reason past it. Nine benign labels are pinned as a false-positive guard.
- **`eval_factcheck.py`** measures the `materials-fact-checker`, the last
  automated step before a claim reaches an employer. Each case is a clean draft
  plus one planted defect (invented metric, rounded metric, claimed direct
  reports, banned Phase-1 framing, unsourced skill, em-dash, AI trope). It reads
  the system prompt straight from the agent definition, so it grades the shipped
  prompt, not a copy. **Half the suite is clean controls** — a checker that
  flags everything has perfect recall and is useless, so the grade is the
  harmonic mean of recall and precision. Ground truth is a synthetic person in
  `tests/fixtures/factcheck/`; the real profile is never read. **Detection and
  severity are reported separately** — a defect nobody named can reach an
  employer, while one filed a rung too low still reaches the report, so only
  the former fails the run. First live run: grade B, 14/14 detected, 12/14 at
  the expected severity, 2/2 clean controls untouched.
- **Digest markdown is a parsed interface now.** Changing the `### [Score N] Company — [Title](url)`
  header or the `- Domain: … · Stage: …` detail line in `digest.py` breaks
  `eval_calibration.parse_digest` against every already-archived digest, and
  archived bodies cannot be re-rendered. Change the format only additively.
- Unmeasured: `extract.py` (no golden set of JD to expected extraction, so Haiku
  drift is invisible) and `digest-triager` ranking.

## Per-user configuration (two layers)

- **`config/pipeline.toml`** — gitignored (template: `config/pipeline.example.toml`). Location scope, metro tiers, commute thresholds/notes, title targeting, domain + stage weights, comp floor, YoE cap, stale days. `settings.pipeline_config()` loads it, falling back to the example on a fresh clone. The pipeline runs locally, so edits take effect on the next run — no sync step.
- **`profile/`** — gitignored. Identity, EEO answers, `[paths]` to the driving docs, fit profile, QA checklist, the resume generator.
  **The driving docs live inside `profile/` as real files**, not as links or absolute paths pointing outside the repo: `profile/inputs/` (resume_master, personal_statement, standard_answers, qa_checklist, steering, cover_letter_examples), `profile/ai_skills/` (claims_ground_truth.md, the resume and cover-letter generators), and `profile/applications/` for rendered output. `profile/` is gitignored, so none of it reaches git. **`profile/` is the source of truth — edit the docs here.** Copies still sitting in OneDrive and `~/.claude/ai_skills` are stale the moment you change one; editing those instead is the failure mode to watch for. Junctions were tried first and removed: Cowork's device bridge resolves a junction to its real target before applying its folder grant, so a linked path reads as the outside folder and fails. Real files in the workspace are the only form that works everywhere. Relative `[paths]` resolve against the repo root, never the cwd — `job_apply.load_config()` enforces that so the scheduled task keeps working.
- Handing the repo to a new user: plain `git clone`; SETUP.md §1 resets the owner's ledgers and digests. History is scrubbed of PII and MUST stay that way — no personal data in commits, ever; the committed ledgers are the only owner-specific tracked state.

## Location scope and the commute warning

The committed config encodes the owner's home base and a deliberately different target metro; `standard_answers.md` may state the target metro as the location on purpose — that is positioning, not an error, so never "fix" it. The actual metro regexes, tiers, and warning text live in `config/pipeline.toml [location]`.

- **In scope** (`filter.stage1`, via `in_scope_patterns`): Boston metro, NYC metro, all of CT, RI/Providence, western + central MA, southern NH, Albany, any "East Coast"/"Northeast" phrasing, and any US-remote role.
- **Metro tiers** (`filter.metro_tier`) are drive time from the configured home base, defined in `config/pipeline.toml [location.tiers]`. Checked far-first, because a far-metro string like "Boston, MA" also matches the state tokens that place near-metro cities.
- **`filter.commute_warning`** flags `far` + 4-5 days onsite, and `mid` + 5 days. It **warns, never discards** — days-per-week is often negotiable and postings misstate it. Surfaced in the digest as a `⚠️ Commute:` line.
- Depends on `onsite_days_per_week` from extraction (0-5 or null; null means the JD said nothing, and never warns). Validated at the boundary by `extract._clamp_days`, since the field feeds a user-facing warning.

## Credentials

Local `.env` (gitignored): `ANTHROPIC_API_KEY` (extract, `eval_factcheck`), `GMAIL_USER` + `GMAIL_APP_PASSWORD` (digest email via `emailer.py`; user is both sender and recipient). No GitHub Actions secrets are needed — the repo runs no workflows. Paste keys via a plain-text editor to avoid BOM corruption (see Gotchas).

## Gotchas

- **BOMs in Python source**: use `chr(0xfeff)` constants, never literal BOM characters. Source-file encoding can corrupt the literal between Windows editors and Linux runners. See `_BOM = chr(0xfeff)` patterns in `extract.py`, `ashby.py`, `lever.py`.
- **Defensive `.strip().replace(_BOM, "")` on env-var reads** in `extract.py` — pasted secrets can carry invisible BOMs that crash SDK header construction. Already in place.
- **Don't auto-run the pipeline** to test changes — it spends real Anthropic tokens (~$$). The scheduled task owns the weekly run; prefer targeted unit tests via pytest.
- **Commit subjects and PR titles are one plain sentence stating what the change does** — imperative, lowercase start, no `type(scope):` prefixes, no "Type of change" checklists. The body (optional) explains why.
- **PRs are the norm**, not direct-to-main — for the audit trail, not for review gating. Nothing reviews them automatically. When a change is worth a second pass, dispatch the `python-code-reviewer` agent, or use the built-in `/code-review`.

## Apply workflow (slash commands)

- `/job-apply [external_id | --top N]` — tailors resume + cover letter for pending roles, runs the materials fact-checker, renders the per-job folder via `job_apply.render()`, then dispatches autofill. Logic in `.claude/commands/job-apply.md`; deterministic render in `src/job_finder/job_apply.py`.
- **The ATS never gates prep — only who pushes Submit.** Any posting with a readable JD gets the full tailor→fact-check→render loop, including pasted URLs and manual-tier companies. Autofill runs when the form is reachable; account-walled portals (SuccessFactors, Workday, iCIMS, Phenom) get a complete package plus an `APPLY_NOTES.md` manual-submit handoff instead. A role is never skipped because of its ATS.
- `/job-apply-batch [--top N] [--include-stretch]` — the same loop over N roles with no per-role gates and one report at the end, for unattended sessions. Defers to `job-apply.md` for the per-role work rather than restating it. Adds a ground-truth preflight, a park-don't-guess rule, and a batch gate. Main queue only by default: the calibration eval puts stretch roles at 0.52x the baseline apply rate against main's 1.23x, and in a batch nobody skips them.
- `/fill-application <url> [folder]` — standalone Playwright autofill via the `application-autofiller` subagent. Stops without submitting; the user reviews and submits by hand. Logic in `.claude/commands/fill-application.md`.
- **Greenhouse forms: prefer the deterministic script** over the agent — `python -m job_finder.fill_greenhouse --url <url> --folder <per-app folder> [--city <city>]`. Fills the standard section (contact, auth, EEO, uploads) with zero LLM tokens, DOM-verifies every dropdown commit, prints a fill report, holds the browser open for review, never submits. ~2k tokens vs ~63k for the agent. One-time setup: `pip install -e .[apply]` + `playwright install chromium` (local only; CI never needs it). The agent stays as the fallback for unknown ATSes and custom questions.
- Field values come from `profile/profile.toml` (identity, EEO, work-auth stance) plus `standard_answers.md` in the configured `inputs_dir` (`profile/profile.toml [paths]`; may point at a cloud-synced folder outside the repo).
- **Grade every fill batch**: `python -m job_finder.fill_grader --date <YYYY-MM-DD>` letter-grades the audit manifests (Layer 1, zero tokens). Its `no_rule` output is the backlog — turn entries into `[[custom_combos]]` answers in `profile/profile.toml`. `python -m job_finder.profile_check` is the profile doctor (placeholder/missing-doc detection); SETUP.md tells new users to run it.
- **Every fill captures a before/after field inventory** to `data/fill_audits/<date>_<slug>.{pre,post}.json` (gitignored — the `value` column holds contact details). Both fill paths use `form_inventory.py` so their output is comparable; the deterministic script writes them directly, the agent via `browser_evaluate`. Capture is best-effort and never blocks a fill. Redact with `form_inventory.redact()` before promoting a manifest to `tests/fixtures/`. Design: `.claude/context/form-fill-evals.md`.
- **Playwright MCP is project-scoped** (`.mcp.json`). Its `mcp__playwright__*` tools only load when the Claude session is rooted in this directory — autofill won't work from a session started in the parent `dev/` directory.
- **Batch autofill = one Chrome instance, one tab per app** (never a separate browser per app). Dispatch a single `application-autofiller` with the full list of `(url, folder)` pairs; it opens each app in a new tab and leaves them all open, unsubmitted, for review. Rule lives in the Batch mode section of `.claude/agents/application-autofiller.md`.

## Project-level skills

- `.claude/skills/job-apply-batch/SKILL.md` — the unattended apply loop. **Lives in `skills/`, not `commands/`, on purpose:** Cowork rejected it as an unknown skill while it sat in `.claude/commands/`, and its frontmatter only parsed once it carried a `name:` field. Skills register on both surfaces; commands appear not to. Prefer `skills/` for anything an unattended session must invoke.
- `.claude/skills/manage-companies/SKILL.md` — add/remove/probe tracked companies in `data/state.db` from plain-English instructions, via the `job-finder companies` CLI.
- `.claude/skills/ensure-browser/SKILL.md` — get a usable browser before dispatching a fill agent. The Claude in Chrome tools attach to a running Chrome, they never launch one, and `list_connected_browsers` reflects live state: it empties when the browser closes and repopulates within seconds of it starting. So an empty list usually means Chrome is shut, not that the extension is missing. The skill checks the cheaper surfaces first (`fill_greenhouse` needs no browser at all; Playwright launches its own), and is honest that a genuinely unconnected extension is one-time human setup it cannot do.

## Subagents

`.claude/agents/` — dispatched from slash commands or directly via the `Agent` tool. Each pins its own model and tool list. The Sonnet subagents below handle mechanical work so the main Opus-tier conversation keeps focus on voice and judgment.

| Subagent | Purpose | Model |
|---|---|---|
| `digest-triager` | Reads latest digest, ranks pending roles against fit profile, returns ranked picks | Sonnet |
| `materials-fact-checker` | Cross-checks drafted RESUME_DATA + cover letter against ground-truth files; severity-tagged findings | Sonnet |
| `application-autofiller` | Drives Playwright MCP through the application form; stops before submit | Sonnet |
| `python-code-reviewer` | Code review on demand; dispatched by hand, not wired to any trigger | Opus |

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

- **Store:** the `applied` table in `data/state.db` (gitignored, local-only). The digest reads it to suppress already-applied roles, including reposts (company + normalized-title match).
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

`.claude/agents/python-code-reviewer.md` defines what the reviewer looks for when you dispatch it. Severity-tagged findings (CRITICAL/HIGH/MEDIUM/LOW/NIT). On-demand context files in `.claude/context/`:
- `google-python-style.md` — loaded for `.py` reviews
- `ai-agent-security.md` — loaded for files under `agents/`, `tools/`, `mcp/`, `prompts/` or importing `anthropic`/`openai`/`langchain`
- `pr-review-checklist.md` — the working checklist
