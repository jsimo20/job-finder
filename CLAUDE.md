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

- Python 3.10+. Deps: httpx, anthropic, jinja2, beautifulsoup4, python-dotenv, plus `tomli` on 3.10 only. **The floor is 3.10 because the Cowork device VM runs it**; `tomllib` was the sole 3.11+ import and `settings.py` and `conftest.py` fall back to `tomli`. Install via `uv pip install --system -e .`.
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

## Checking on the system

```sh
job-finder status
```

One read-only report across both halves: last pipeline run with its exit code
**and** the two numbers that exit 0 hides (rate-limited requests, collect
errors), the scheduled task's next run and whether it will wake the machine, the
latest digest and its age, applied count, application folders not in the applied
ledger, and this repo's cowork-plugin version for comparison against the one
Cowork shows. No network, no tokens.

**Exit 0 is not a healthy run.** The 2026-08-31 pipeline exited 0 with 963
rate-limited requests and 50 collect errors; 46 Ashby boards contributed nothing
to that digest. That is why those two counts sit next to the exit code rather
than in a log nobody opens.

## Evals

Three deterministic zero-token graders plus two that spend tokens. They read
artifacts the system already produces rather than running a parallel harness,
and each has a bucket that is a backlog rather than a failure.

```sh
# Does the score predict what actually gets applied to?
.venv/Scripts/python.exe -m job_finder.eval_calibration
# Did the last fill batch fill everything it had a rule for?
.venv/Scripts/python.exe -m job_finder.fill_grader --date <YYYY-MM-DD>
# Refuse the batch instead of describing it (unattended runs)
.venv/Scripts/python.exe -m job_finder.fill_grader --date <YYYY-MM-DD> --gate
# Does the drafted cover letter break a flat voice rule? (zero tokens)
.venv/Scripts/python.exe -m job_finder.letter_linter --date <YYYY-MM-DD>
# Does the term mapper take honest keywords and refuse gaps? (spends tokens)
.venv/Scripts/python.exe -m job_finder.eval_skill_terms
# Any eval, repeated, so a change can be told apart from noise
.venv/Scripts/python.exe -m job_finder.eval_skill_terms --repeat 3
# Does the fact-checker catch a defect planted on purpose? (spends tokens)
.venv/Scripts/python.exe -m job_finder.eval_factcheck
# Does the drafter write a good letter unattended? (spends tokens, live JDs)
.venv/Scripts/python.exe -m job_finder.eval_generation --n 3
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
  `--gate` turns it into a check the fill agent runs before reporting: **0**
  ready, **4** critical violation, **3** nothing to grade because no form was
  filled. 3 and 4 are separate because an unattended caller cannot act on
  "nothing happened" and "every form was unsafe" the same way, and both stay
  clear of argparse's own exit 2.
  Critical now includes **prompt-injection suspects**: `INJECTION_PATTERN` scans
  each field's label, options and value for text addressed to the agent rather
  than the applicant. The agent already carries a prompt rule saying page
  content is data — this is the same rule in code, so an unattended run cannot
  reason past it. Nine benign labels are pinned as a false-positive guard.
- **`letter_linter.py`** reads a rendered letter's `cover_letter.json` and flags
  the voice rules that survive as patterns. **CRITICAL blocks and ADVISORY never
  does**, because a flat ban (em-dash, a paragraph opening on "I", an opening that
  announces a reaction rather than stating a fact about the company, a feeling
  verb, a trope, a closing that is not "Thanks,") has no legitimate exception,
  while a trailing-gloss candidate does: "which is what started my search" carries
  a new fact and matches the same shape. It carries a **subset** of the style
  guide, never the whole of it; the guide named by `[paths].writing_style_path` is
  the authority and the `materials-fact-checker` is what reads all of it. Both
  exist because the checker's measured failure mode is filing a real violation as
  NIT, and a pattern match cannot reason its way down to NIT. The batch runs it
  **after render and before any fill**, so a bad letter never reaches a form.
  Structural checks (paragraph chaining, whether the close returns to the opening)
  are ADVISORY on purpose: they encode a procedure written 2026-08-25 against one
  letter, and collect signal until there is enough to justify blocking on.
- **`eval_generation.py`** measures the drafter rather than the checker, and its
  graders are the two that already exist, so there is no new rubric to drift:
  `letter_linter` for patterns, the `materials-fact-checker` prompt for judgment.
  A letter passes when neither reports a CRITICAL. **It reads the real profile**,
  unlike `eval_factcheck` — a synthetic person would measure a different system,
  since the drafting prompt's whole job is turning those documents into a letter.
  **JDs are live, not fixtures**: a frozen JD goes stale while quietly becoming
  the thing the prompt was tuned against, so runs are not reproducible and the
  report names the postings used. Any posting in the applied ledger is held out.
  ~25k tokens per case. **Neither grader can tell whether the opening's contrast
  is true** — a manufactured departure passes every check, so read one letter.
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
- **`eval_skill_terms.py`** measures the `skill-term-mapper`'s judgment, which
  `skill_terms.py` cannot. Each case is one JD built around a single repeated
  term. Three kinds: `swap` (the pool holds the same thing under another name),
  `gap` (a capability it does not hold), and **`covered`** (the term is already on
  the resume verbatim). `covered` exists because swaps are one-in-one-out, so a
  redundant swap would take a real skill off to add a word already there. Grade is
  the harmonic mean of swaps-taken and holds-refused, so a mapper that proposes
  nothing scores F. Ground truth is synthetic. **13 cases: 6 swaps, 6 gaps, 1 covered.** Measured
  2026-09-01 at **1.00 across two runs, spread 0.00**, after the prompt gained a
  practice-name rule and lost a self-contradiction the eval surfaced. Four of the
  gaps exist to catch that looser rule going sloppy ("data engineering is a
  practice built on SQL"); they are the cases to watch when the prompt changes.
- **Every LLM eval takes `--repeat N` and reports the spread.** They graded each
  case once until 2026-09-01, which is a single sample from a stochastic process:
  14/14 and 12/14 on an unchanged prompt are both ordinary, so one number cannot
  tell a regression from noise. `--repeat` prints median, spread, stdev, and the
  cases that flipped between runs. **A change smaller than the spread is not a
  result.** Shared implementation in `eval_spread.py` so the three evals agree on
  what a spread means.
- **Digest markdown is a parsed interface now.** Changing the `### [Score N] Company — [Title](url)`
  header or the `- Domain: … · Stage: …` detail line in `digest.py` breaks
  `eval_calibration.parse_digest` against every already-archived digest, and
  archived bodies cannot be re-rendered. Change the format only additively.
- Unmeasured: `extract.py` (no golden set of JD to expected extraction, so Haiku
  drift is invisible) and `digest-triager` ranking.

## Resume skill terms and the ATS

An ATS filters on the job description's exact words, and the source pool often
holds the same skill under a different name. So a JD term may be written onto the
resume **in place of** a pool term that already names it — never in addition.

- `.claude/agents/skill-term-mapper.md` makes the judgment: 90% confidence that
  the JD's word names something in the pool. "Lovable" for "Figma", "creating
  PRDs" for "writing requirements", "ChatGPT" for "LLM-based workflows" clear it.
  "Databricks", "Kubernetes", "assembly line optimization" do not — those are new
  capabilities, and they belong in the cover letter as named gaps.
- **Every swap anchors to the pool, never to another swap.** Figma → Lovable is
  defensible; Lovable → "production React delivery" is defensible *from Lovable*,
  and the chain lands on a claim nothing supports. `skill_terms.check_substitutions`
  enforces this by requiring `replaces` to exist in the pool.
- `python -m job_finder.skill_terms --folder <per-app folder>` verifies the
  structure deterministically: 0 clean, 4 a critical violation, 3 nothing to check.
  **It cannot check the judgment** — a swap the agent rationalized reaches an
  employer, which is why `rejected` entries are read rather than trusted.
- **Named tools the user has not opened do go on the resume** when a swap clears
  the bar. That is a deliberate call (2026-09-01) trading interview exposure for
  the keyword match; the folder records what each swap stands on so the honest
  answer is ready before anyone asks.

## Per-user configuration (two layers)

- **`config/pipeline.toml`** — gitignored (template: `config/pipeline.example.toml`). Location scope, metro tiers, commute thresholds/notes, title targeting, domain + stage weights, comp floor, YoE cap, stale days. `settings.pipeline_config()` loads it, falling back to the example on a fresh clone. The pipeline runs locally, so edits take effect on the next run — no sync step.
- **`profile/`** — gitignored. Identity, EEO answers, `[paths]` to the driving docs, fit profile, QA checklist, the resume generator.
  **The driving docs live inside `profile/` as real files**, not as links or absolute paths pointing outside the repo: `profile/inputs/` (resume_master, personal_statement, standard_answers, qa_checklist, steering, cover_letter_examples), `profile/ai_skills/` (claims_ground_truth.md, the resume and cover-letter generators), and `profile/applications/`, where `render()` writes and where finished folders **stay permanently**. `profile/` is gitignored and synced nowhere, which is an accepted tradeoff; there is no backup step and none should be added. **Applications sent before 2026-08-26 live in `OneDrive/Documents/Job Search/2026/applications` and stay there** — the history is split on purpose, so do not reconcile the two. **`profile/` is the source of truth — edit the docs here.** Copies still sitting in OneDrive and `~/.claude/ai_skills` are stale the moment you change one; editing those instead is the failure mode to watch for. Junctions do not work here: Cowork's device bridge resolves a junction to its real target before applying its folder grant, so a linked path reads as the outside folder and fails. Keep these as real files. Relative `[paths]` resolve against the repo root, never the cwd — `job_apply.load_config()` enforces that so the scheduled task keeps working.
- Handing the repo to a new user: plain `git clone`; SETUP.md §1 resets the owner's ledgers and digests. History is scrubbed of PII and MUST stay that way — no personal data in commits, ever; the committed ledgers are the only owner-specific tracked state.

## Location scope and the commute warning

The committed config encodes the owner's home base and a deliberately different target metro; `standard_answers.md` may state the target metro as the location on purpose — that is positioning, not an error, so never "fix" it. The actual metro regexes, tiers, and warning text live in `config/pipeline.toml [location]`.

- **In scope** (`filter.stage1`, via `in_scope_patterns`): Boston metro, NYC metro, all of CT, RI/Providence, western + central MA, southern NH, Albany, any "East Coast"/"Northeast" phrasing, and any US-remote role.
- **Metro tiers** (`filter.metro_tier`) are drive time from the configured home base, defined in `config/pipeline.toml [location.tiers]`. Checked far-first, because a far-metro string like "Boston, MA" also matches the state tokens that place near-metro cities.
- **`filter.commute_warning`** flags `far` + 4-5 days onsite, and `mid` + 5 days. It **warns, never discards** — days-per-week is often negotiable and postings misstate it. Surfaced in the digest as a `⚠️ Commute:` line.
- Depends on `onsite_days_per_week` from extraction (0-5 or null; null means the JD said nothing, and never warns). Validated at the boundary by `extract._clamp_days`, since the field feeds a user-facing warning.

## Credentials

Everything is read through `os.environ`, so a credential can sit in the gitignored `.env` or in a Windows user environment variable. **They are split today, and that is fine:** `ANTHROPIC_API_KEY` (extract, `eval_factcheck`) is in `.env`, while `GMAIL_USER` + `GMAIL_APP_PASSWORD` (digest email via `emailer.py`; user is both sender and recipient) are user env vars set with `setx`. The scheduled task inherits them.

**Never add the Gmail keys to `.env` as a second copy.** `cli.py` calls `load_dotenv(override=True)`, so a stale value in `.env` silently wins over the working environment one, and the failure looks like a credential that stopped working for no reason.

No GitHub Actions secrets are needed — the repo runs no workflows. Paste keys into `.env` via a plain-text editor to avoid BOM corruption (see Gotchas); `setx` avoids that problem entirely.

## Gotchas

- **BOMs in Python source**: use `chr(0xfeff)` constants, never literal BOM characters. Source-file encoding can corrupt the literal between Windows editors and Linux runners. See `_BOM = chr(0xfeff)` patterns in `extract.py`, `ashby.py`, `lever.py`.
- **Defensive `.strip().replace(_BOM, "")` on env-var reads** in `extract.py` — pasted secrets can carry invisible BOMs that crash SDK header construction. Already in place.
- **Both SQLite databases run `journal_mode = TRUNCATE`, set per connection in
  `db.connect()` and `state.connect()`.** The default DELETE mode unlinks the
  rollback journal on every commit, and a Cowork device-bridge mount blocks
  unlink: the commit fails, a hot journal is left behind, and the next reader
  gets `disk I/O error` until someone clears it by hand. This wedged `jobs.db` on
  2026-08-28. TRUNCATE zeroes the journal instead of removing it, so no unlink is
  ever needed and rollback still works. **Not MEMORY** — that also avoids the
  file but gives up crash recovery, and `state.db` holds the applied ledger with
  no backup anywhere. The pragma does not persist (only WAL is written to the
  file header), so any new code opening `sqlite3.connect()` directly reintroduces
  the bug; go through the two `connect()` helpers.
- **Don't auto-run the pipeline** to test changes — it spends real Anthropic tokens (~$$). The scheduled task owns the weekly run; prefer targeted unit tests via pytest.
- **Commit subjects and PR titles are one plain sentence stating what the change does** — imperative, lowercase start, no `type(scope):` prefixes, no "Type of change" checklists. The body (optional) explains why.
- **PRs are the norm**, not direct-to-main — for the audit trail, not for review gating. Nothing reviews them automatically. When a change is worth a second pass, dispatch the `python-code-reviewer` agent, or use the built-in `/code-review`.

- `src/job_finder/liveness.py` — is a posting still listed on its board? Reads the
  light listing endpoints, not the collect adapters, so a board answers in under a
  second instead of minutes. **HTTP status cannot answer this**: a closed Ashby
  posting still serves 200 from its single-page app, and only the board listing
  distinguishes it. Unknown counts as live, since skipping a real posting costs an
  application while tailoring a dead one costs tokens. Workday is deliberately
  absent — no cheap listing endpoint, so its roles read as undetermined.

## Apply workflow (slash commands)

- `/job-apply [external_id | --top N]` — tailors resume + cover letter for pending roles, runs the materials fact-checker, renders the per-job folder via `job_apply.render()`, then dispatches autofill. Logic in `.claude/commands/job-apply.md`; deterministic render in `src/job_finder/job_apply.py`.
- **The ATS never gates prep — only who pushes Submit.** Any posting with a readable JD gets the full tailor→fact-check→render loop, including pasted URLs and manual-tier companies. Autofill runs when the form is reachable; account-walled portals (SuccessFactors, Workday, iCIMS, Phenom) get a complete package plus an `APPLY_NOTES.md` manual-submit handoff instead. A role is never skipped because of its ATS.
- `job-finder applications archive [--dry-run]` — **unused by default.** `[paths].applications_archive_dir` is unset, so this raises rather than moving anything. It stays for anyone who wants a second location; set the key and it moves finished folders there, skipping any name that already exists.
- `/job-apply-batch [--top N] [--include-stretch]` — the same loop over N roles with no per-role gates and one report at the end, for unattended sessions. Defers to `job-apply.md` for the per-role work rather than restating it. Adds a ground-truth preflight, a park-don't-guess rule, and a batch gate. Main queue only by default: the calibration eval puts stretch roles at 0.52x the baseline apply rate against main's 1.23x, and in a batch nobody skips them.
- `/fill-application <url> [folder]` — standalone Playwright autofill via the `application-autofiller` subagent. Stops without submitting; the user reviews and submits by hand. Logic in `.claude/commands/fill-application.md`.
- **Greenhouse forms: prefer the deterministic script** over the agent — `python -m job_finder.fill_greenhouse --url <url> --folder <per-app folder> [--city <city>]`. Fills the standard section (contact, auth, EEO, uploads) with zero LLM tokens, DOM-verifies every dropdown commit, prints a fill report, holds the browser open for review, never submits. ~2k tokens vs ~63k for the agent. One-time setup: `pip install -e .[apply]` + `playwright install chromium` (local only; CI never needs it). The agent stays as the fallback for unknown ATSes and custom questions.
- Field values come from `profile/profile.toml` (identity, EEO, work-auth stance) plus `standard_answers.md` in the configured `inputs_dir` (`profile/profile.toml [paths]`; may point at a cloud-synced folder outside the repo).
- **`render()` writes `cover_letter.json` beside the PDFs.** The PDF is not readable input, so
  without it a revision is a rewrite rather than an edit, and `letter_linter` has nothing to read.
- **Grade every fill batch**: `python -m job_finder.fill_grader --date <YYYY-MM-DD>` letter-grades the audit manifests (Layer 1, zero tokens). Its `no_rule` output is the backlog — turn entries into `[[custom_combos]]` answers in `profile/profile.toml`. `python -m job_finder.profile_check` is the profile doctor (placeholder/missing-doc detection); SETUP.md tells new users to run it.
- **Every fill captures a before/after field inventory** to `data/fill_audits/<date>_<slug>.{pre,post}.json` (gitignored — the `value` column holds contact details). Both fill paths use `form_inventory.py` so their output is comparable; the deterministic script writes them directly, the agent via `browser_evaluate`. Capture is best-effort and never blocks a fill. Redact with `form_inventory.redact()` before promoting a manifest to `tests/fixtures/`. Design: `.claude/context/form-fill-evals.md`.
- **Playwright MCP is project-scoped** (`.mcp.json`). Its `mcp__playwright__*` tools only load when the Claude session is rooted in this directory — autofill won't work from a session started in the parent `dev/` directory.
- **Uploaded filenames are exactly what `render()` wrote** — `James_Simonelli_Resume_<company>.pdf` and
  `James_Simonelli_CoverLetter_<company>.pdf`. The ATS shows the uploaded filename to the hiring manager,
  so it never carries a role slug, a date, or any other staging artifact. Keeping two same-company roles
  apart is what the staging **folder** is for: `<uploads root>/<role-slug>/<filename>`. A `role-slug__`
  filename prefix shipped to a live Greenhouse form on 2026-08-25; the rule now lives in
  `.claude/agents/application-autofiller.md` and the batch skill.
- **Batch autofill = one Chrome instance, one tab per app** (never a separate browser per app). Dispatch a single `application-autofiller` with the full list of `(url, folder)` pairs; it opens each app in a new tab and leaves them all open, unsubmitted, for review. Rule lives in the Batch mode section of `.claude/agents/application-autofiller.md`.

## Running an unattended batch (Cowork, or any session that will not be watched)

**Invoke it by file path, not by slash command:**

> Read `.claude/skills/job-apply-batch/SKILL.md` and follow it for the top 1 role.

A file read works on every surface. **Cowork does not index project-level
`.claude/skills/` or `.claude/commands/` at all** — confirmed by typing `/mana`
there and getting only plugin skills, with `manage-companies` absent despite
being correctly formed and weeks old. It loads plugin skills and this
`CLAUDE.md`, nothing else from the repo.

So do not move a file between `commands/` and `skills/` hoping that surface will
notice, and do not copy a procedure into this file: point at its path, so there
is still one source of truth.

**Playwright works from Cowork and opens a real, clickable window.** Verified
2026-08-24 by running it there. The autofill path is Playwright everywhere, with
no Chrome-extension fallback and nothing to open beforehand.

The rule that follows: **anything an unattended session must run should be
invocable by path.** Keep the skills and commands for the surfaces that resolve
them, and point at the file when you cannot rely on that.

## Running Python from a Cowork device VM

**Every Python call on a device VM is prefixed `PYTHONPATH=".cowork-deps:src" python3`.**

`job_finder` lives under `src/`, and the only editable install is
`.venv/Lib/site-packages/_editable_impl_job_finder.pth` inside the **Windows**
venv, which the Linux VM Cowork mounts cannot see. `pyproject.toml`'s
`pythonpath = ["src"]` only applies under pytest. So a bare `python -c "from
job_finder import liveness"` dies on `ModuleNotFoundError` before any dependency
question arises, and an unattended run has nobody to ask.

`PYTHONPATH=src` fixes the import. `.cowork-deps/` fixes the third-party imports
behind it, because the VM ships bare Python with no site-packages. Build it with
`sh scripts/bootstrap_cowork_deps.sh`; it is gitignored, so a fresh clone will
not have it and the batch preflight rebuilds it rather than failing.

- **Default set is `httpx tomli reportlab`**, all pure Python with no compiled
  extensions, so the directory survives a Python minor-version bump.
- **`reportlab` is a call-time dependency, not an import-time one.** `import
  job_finder.job_apply` succeeds without it and `render()` then fails, so an
  import-only smoke test does not prove the batch will work.
- **`--cli` adds `anthropic python-dotenv`** for
  `python3 -m job_finder.cli ...`, the stand-in for the `job-finder` console
  script, which also does not exist on the VM. Not the default: anthropic pulls
  `jiter.cpython-310-x86_64-linux-gnu.so` and locks the directory to CPython 3.10
  on linux/x86_64. Prefer running `job-finder digest-archive list` on Windows.
- `python3`, not `python`. Both exist on the VM; be explicit.
- **On Windows use `.venv/Scripts/python.exe` with no prefix.** Windows separates
  PYTHONPATH entries with `;`, so `".cowork-deps:src"` resolves to a single
  nonexistent directory there; the editable install makes the prefix unnecessary
  anyway.
- **`fill_grader` imports its pattern constants from `fill_greenhouse`**, whose
  playwright import is guarded for that reason. Keep it guarded: the fill gate
  runs where no browser client is installed.

## Cowork plugin (`cowork-plugin/`)

Cowork does not index project-level `.claude/skills/`, so the weekly batch is
also packaged as a plugin. It is a **thin launcher, not a copy**: the skill reads
`.claude/skills/job-apply-batch/SKILL.md` from the mounted repo and decides only
the role count. Everything else, the archive step included, lives in the batch
skill; two copies of that procedure would drift.

- `cowork-plugin/.claude-plugin/plugin.json` — manifest
- `cowork-plugin/.mcp.json` — Playwright, **version-pinned** (`@latest`
  re-resolves per session and a breaking change would land silently). **Not a
  duplicate of the repo-root `.mcp.json`:** Cowork does not read a project's
  `.mcp.json` at all (verified 2026-08-25), so a plugin-bundled server is the only
  way it gets one. The repo copy serves Claude Code.
- `cowork-plugin/skills/job-apply-weekly/SKILL.md` — the launcher

**Install it, do not add the folder as context.** A connected folder is just
files on disk, so `.mcp.json` never runs and the failure looks like a broken
plugin. Cowork tab → Customize → Plugins → upload. Full reference, including
the `mcp__remote-devices__plugin_*` tool naming:
`~/.claude/context/cowork-plugins.md`.

**Bump `plugin.json`'s `version` on every change that has to reach Cowork.**
The repo cannot see what is installed, but Cowork's plugin list shows the
installed version, so the two versions side by side are the one drift check a
human can run in five seconds. A version left alone across a rebuild throws that
away.

**Editing `cowork-plugin/` changes nothing until you rebuild and re-upload.**
`python scripts/build_cowork_plugin.py`, then upload the zip. Cowork runs the
snapshot it was given and keeps it service-side — `~/.claude/plugins/data/job-finder-inline/`
is empty, so nothing local can compare the repo against what is installed, and a
correct file here can sit next to a stale running plugin indefinitely. That gap
filed seven applications with no resume attached on 2026-08-31. The batch
preflight's upload probe is the only check that catches it, because it asks the
running server instead of reading a file.

**`fill_greenhouse` does not run on Cowork.** The device VM has no `playwright`
Python module, and a browser launched inside it is not one the user can see or
click, which defeats leaving tabs open for review. On Cowork the autofill agent
is the only fill path at ~63k tokens per form, which caps how many roles a batch
can carry. In Claude Code on Windows the script runs and costs ~2k.

## Project-level skills

- `.claude/skills/job-apply-batch/SKILL.md` — the unattended apply loop. **Lives in `skills/`, not `commands/`, on purpose:** Cowork rejected it as an unknown skill while it sat in `.claude/commands/`, and its frontmatter only parsed once it carried a `name:` field. Skills register on both surfaces; commands appear not to. Prefer `skills/` for anything an unattended session must invoke.
- `.claude/skills/manage-companies/SKILL.md` — add/remove/probe tracked companies in `data/state.db` from plain-English instructions, via the `job-finder companies` CLI.

## Subagents

`.claude/agents/` — dispatched from slash commands or directly via the `Agent` tool. Each pins its own model and tool list. The Sonnet subagents below handle mechanical work so the main Opus-tier conversation keeps focus on voice and judgment.

| Subagent | Purpose | Model |
|---|---|---|
| `digest-triager` | Reads latest digest, ranks pending roles against fit profile, returns ranked picks | Sonnet |
| `skill-term-mapper` | Proposes JD-vocabulary swaps into the resume skills section, anchored to the source pool | Sonnet |
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
- **`applied.drop_applied(rows)` is the only correct way to ask "is this still pending?"** `postings.applied_at` in jobs.db is rebuilt to NULL every run, so it only catches applies made since the last one; anything older reads as pending. `digest.py` and `review.py` both route through `drop_applied`, and any new caller reaching for pending roles must too. Trusting the column instead re-offered two already-applied roles on 2026-08-31 and both were submitted twice.
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
