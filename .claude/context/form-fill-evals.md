# Form-fill evals — rules

How autofill quality is measured and improved. Layer 1 is implemented as
`src/job_finder/fill_grader.py`; Layer 2 (LLM judgment grading) is unbuilt
and local-only by design.

## The core idea: a per-page field inventory, not computer vision

One DOM pass over the form root (`form_inventory.py`) emits, for every
control: `field_id`, `label`, `type`, `required`, `value`, `options`.
Captured **before** the fill (page manifest) and **after** (filled state) to
`data/fill_audits/<date>_<slug>.{pre,post}.json`. Both fill paths (script and
agent) use the same inventory so their outputs are comparable.

Why this beats screenshots as the primary signal: exact values, full option
lists for collapsed dropdowns, conditional-field detection by diffing, and
stability across ATS restyles. Vision is a fallback only (canvas widgets,
unreachable iframes, "did it render broken").

## Two-layer grading

**Layer 1 — deterministic (free, every batch, CI-safe).** Assertions over the
manifests; every field lands in one bucket:

- `filled` / `missed` (a configured rule existed but the field is blank)
- `deliberate_blank` — blank is CORRECT: salary/comp, legal questions,
  name-trap fields, checkboxes/consent
- `env_failure` — a rule existed but the dropdown rendered zero options while
  the filler had it open (async menu); a repeat across batches is a
  retry-timing code fix, not an answers gap
- `no_rule` — no configured answer; the growth backlog that feeds
  `[[custom_combos]]` / `[[custom_text]]`
- `upload` — file inputs verify by rendered filename in the fill report, not
  the manifest (the input node is removed on upload)

Critical violations cap the form at F: a vetoed sponsorship answer
committed, any value in a salary or name-trap field, or instruction-like text
found in a field's own label, options or value.

**Layer 1 is also the gate.** `--gate` exits 4 when any form carries a
critical violation and 3 when no manifest matched at all, and the fill agent
runs it before reporting. The empty case is its own code because a run that
filled nothing produces the same silence as a run that filled everything
cleanly, and only the exit code tells them apart. An
interactive run has a human reading the report; an unattended one does not, so
the batch needs something that refuses rather than something that describes.

**Layer 2 — LLM (small input, one call per form, if ever built).** Grades
only judgment, reading the inventory diff, never the raw page: is this value
semantically right for this label; does short-answer text match the user's
voice (`~/.claude/rules/writing-style.md` is the rubric — a user-global path,
so Layer 2 stays off CI); was a custom question answered by guessing.

## Scope limits

- **Multi-step gated wizards are out of scope** (user decision). The
  manifest only sees the step reached, so grade what it shows and say so.
- A re-grade of an old batch after adding answers moves fields
  `no_rule → missed` and the grade may drop — that is backlog conversion
  working, not a regression. The letter-grade gain lands on the next live
  batch.

## Failure classes this system exists to catch

Each was observed live before the grader existed:

- Conditionally-revealed EEO fields left blank (a Race dropdown that appears
  only after the ethnicity question is answered).
- Two same-company applications rendering identically-named upload files, so
  one role's resume could overwrite the other's — hence per-role filename
  prefixes.
- Plausible-but-wrong mappings (a GitHub URL in a "LinkedIn" field).
- A semantically inverted dropdown commit: a sponsorship question whose label
  also contains "authorization" matched the authorization rule and committed
  its bare "yes" candidate. Fixed by match ordering plus a veto; the audit
  manifest is what caught it.

## Storage and PII

Captured inventories are **gitignored** — the `value` column carries the
user's name, contact details, and every answer given. Promoting a manifest to
`tests/fixtures/` requires redacting values first (`form_inventory.redact()`);
Layer 1 asserts on structure (label/type/required/options/value-presence), so
redacted fixtures keep it CI-capable. Test fixtures are otherwise synthetic.

## Injection resistance

`fill_grader.INJECTION_PATTERN` scans every field's label, options and value
for text addressed to the agent reading the form rather than to the applicant,
and buckets a hit as `critical`. The fill agent already carries a prompt rule
saying page content is data; this is the same rule in code, so an unattended
run cannot reason its way past it. The hostile fixture is
`tests/fixtures/injection_manifest.post.json`.

The pattern is deliberately narrow. Ordinary form copy says "submit your
application" and "review the instructions above" constantly, so only phrasings
that address a reader-of-instructions qualify — nine benign labels are pinned
as a false-positive guard. A false positive costs a human glance; a false
negative costs an autonomous submit.

Still unbuilt: a live agent run against a hostile page asserting the agent
itself surfaces the string and stops. The deterministic check above catches the
manifest either way, so this is now defence in depth rather than the only line.
