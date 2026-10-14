# Development

For changing code, prompts, tests or the plugin. Left out of user installs
(`.gitattributes` export-ignore), so nothing here may be needed at run time.
Rules every agent follows, users' included, live in `CLAUDE.md`.

## Architecture

```
companies (data/state.db)
  → collect: adapters/{greenhouse,lever,ashby,workday}.py → postings (data/jobs.db)
  → Stage 1 filter (filter.py)
  → extraction: weekly.py hands JDs to the session, which reads them (no API key)
  → Stage 3 filter + score (score.py)
  → digest (digest.py) → digests/YYYY-MM-DD.md + archive in state.db
  → apply: .claude/skills/job-apply-batch → job-apply, per role
```

Users run it in Cowork from a folder that `scripts/self_update.sh` keeps on
`main`. The plugin (`cowork-plugin/`) is only the setup launcher.

## Key files

- `src/job_finder/settings.py`: loads `config/pipeline.toml` and `profile/`;
  `require_profile()` gates any real fill or render.
- `src/job_finder/weekly.py`: the weekly cycle (`status`, `collect`,
  `prompt`, `import-extractions`, `finish`); `extract.py` holds the extraction
  prompt and storage. Nothing at run time imports `anthropic`; only the evals
  do, from the `dev` extras.
- `src/job_finder/adapters/*.py`: `fetch()` and `normalize()` per ATS; Workday
  also `fetch_detail()` (its list payload has no JD; slug `tenant/wdN/site`).
- `src/job_finder/filter.py`, `score.py`, `taxonomy.py`: Stage 1/3 rules and
  scoring, all driven by `config/pipeline.toml`.
- `src/job_finder/job_apply.py`: `load_config()` resolves every profile path;
  `render()` writes the application folder.
- `src/job_finder/form_inventory.py`: field inventory shared by both fill
  paths; writes `data/fill_audits/` manifests.
- `src/job_finder/ats_probe.py`, `builtin_discovery.py`, `liveness.py`.
- `SETUP.md`: the profile starting files; `profile_init` parses its
  destination-tagged blocks, and `tests/test_profile_init.py` pins them.

## Tests

```sh
.venv/Scripts/python.exe -m pytest -q
```

- `tests/conftest.py` sets `JOB_FINDER_PIPELINE_CONFIG` to
  `tests/fixtures/pipeline_test.toml` before anything imports, so no test reads
  a real or example config.
- Guards that keep the product shippable:
  - `test_cowork_procedures.py`: no named repo-agent dispatch, every
    `CLAUDE.md` entry point exists, no prompt names a `profile/<dir>/` layout.
  - `test_build_cowork_plugin.py`: plugin and repo skills pass Cowork's
    upload checks.
  - `test_settings.py`: the example config carries no one's search.
  - `test_profile_init.py`: SETUP.md's blocks parse and cover every default
    path.
- Never run the pipeline to test a change; it spends tokens.

## Conventions

- Commit subjects and PR titles: one plain imperative sentence, lowercase
  start, no `type(scope):` prefix. PRs for every change.
- Review on demand: the `python-code-reviewer` agent or `/code-review`. Its
  rubric is `.claude/agents/python-code-reviewer.md`, with
  `.claude/context/google-python-style.md`, `ai-agent-security.md` and
  `pr-review-checklist.md`.
- Python floor is 3.10, the Cowork VM's version. `tomllib` imports fall back to
  `tomli`.
- BOMs: use `chr(0xfeff)` constants, never a literal BOM.
- `fill_greenhouse`'s playwright import stays guarded: `fill_grader` imports its
  patterns and runs where no browser client exists.
- Digest markdown is parsed by `eval_calibration.parse_digest`. Change the
  `### [Score N] Company — [Title](url)` header and the `- Domain: … · Stage: …`
  line only additively; archived digests cannot be re-rendered.
- Every new procedure is a skill under `.claude/skills/` plus a row in
  `CLAUDE.md`'s entry-point table. Never a plugin skill, never a named
  subagent dispatch.

## Releasing

**Merging to `main` deploys every procedure, code and doc change**: installs
update from `main` on each daily scheduled run. Stage before merging.

- **Stage in this checkout.** Connect it in Cowork with the branch checked out;
  a full checkout never self-updates, so Cowork reads the branch. Run the
  requests the change touches and read the trace.
- **Setup downloads `main`**, so a fresh-folder setup test checks only the
  launcher's own steps.
- **A plugin change** (launcher, `.mcp.json`, manifest): bump
  `cowork-plugin/.claude-plugin/plugin.json`'s version, run
  `python scripts/build_cowork_plugin.py` (it refuses what Cowork's uploader
  rejects), install the zip here and smoke-test, then publish a GitHub release
  with the zip. Users re-upload; `releases/latest` serves the newest.
- **Before outsiders depend on it**, point the tarball URL in
  `scripts/self_update.sh` and the setup launcher at a `stable` tag. Merging
  then stops deploying; moving the tag deploys.
- Files deleted upstream stay in existing installs; the overlay never removes.

## Cowork plugin

- `cowork-plugin/skills/job-finder-setup/SKILL.md`: checks the network,
  installs from the tarball (never `git clone`; it breaks on a Cowork folder
  mount) or updates, then hands over to `.claude/skills/job-finder-setup/`.
- `cowork-plugin/.mcp.json`: Playwright, version-pinned. Cowork ignores a
  project's `.mcp.json`, so the plugin is its only source of Playwright; the
  repo-root copy serves Claude Code. Keep the two pins equal. Its absolute
  `--output-dir` is this machine's; the batch's upload probe tells other users
  how to repoint it.
- The server runs on the user's machine through `npx`, so Node.js must be
  installed there; setup walks them through it. It downloads its own browser;
  `browser_install` fixes a missing one.
- Editing `cowork-plugin/` changes nothing until the zip is rebuilt and
  re-uploaded. Cowork keeps the installed snapshot service-side; the version
  in its plugin list against `plugin.json` is the only drift check.

## Cowork device VM

- `.cowork-deps/` (gitignored) holds `httpx tomli reportlab beautifulsoup4`,
  pure Python, built by `scripts/bootstrap_cowork_deps.sh`. It covers every
  runtime module, `job_finder.cli` included.
- `reportlab` is needed at call time, not import time: importing `job_apply`
  succeeds without it and `render()` fails.
- `fill_greenhouse` cannot run there (no playwright module, no visible
  browser); every Cowork fill goes through the autofill agent (~63k tokens a
  form, against ~2k for the script in Claude Code).

## Evals

Run them yourself; they ship to no user. LLM evals take `--repeat N` and
report the spread: a change smaller than the spread is not a result.

| Command | Measures | Tokens |
|---|---|---|
| `python -m job_finder.eval_calibration` | Does the score predict what gets applied to (lift per signal) | 0 |
| `python -m job_finder.eval_factcheck` | Fact-checker catches planted defects; clean controls stay clean | yes |
| `python -m job_finder.eval_skill_terms` | Term mapper takes real swaps and refuses gaps | yes |
| `python -m job_finder.eval_generation --n 3` | Drafter writes letters with no CRITICAL, on live JDs and the real profile | yes |

- `eval_factcheck` and `eval_skill_terms` use a synthetic person in
  `tests/fixtures/`; their clean fixtures must follow the current voice rules.
- `eval_generation` reads the real profile and live postings, so runs are not
  reproducible; it holds out applied postings. Neither grader can tell whether
  a claim about the company is true: read one letter.
- `eval_calibration` recomputes archived scores under today's weights and warns
  when they do not reproduce; digests either side of a reweight are not
  comparable.
- Unmeasured: `extract.py` and `digest-triager` ranking.
- Last measured 2026-10-01: `eval_factcheck` B (18/19 detected, 2/2 clean);
  `eval_skill_terms` median 1.00, spread 0.09; `eval_generation` 1/3 passed.

The token-spending evals need `ANTHROPIC_API_KEY` in a gitignored `.env`; they
load it with override on, so keep the key in one place.
