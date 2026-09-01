---
description: Tailor resume + cover letter for pending roles and prep apply package
argument-hint: [external_id or --top N]
---

You are driving the apply-prep loop for the user. The pipeline that picks the roles is `job-finder`; the tailoring ground truth lives in the profile driving docs (`resume_master.md`, `personal_statement.md`, and the claims-ground-truth file named by `profile/profile.toml` `[paths]`). The deterministic render lives in `src/job_finder/job_apply.py`.

## What to do

Three subagents (all Sonnet) handle the mechanical phases of this command so the main Opus-tier conversation can focus on drafting work that benefits from Opus voice and judgment. Dispatch them via the `Agent` tool with the indicated `subagent_type`. Each starts with cold context — pass the inputs it needs inline in the prompt.

### 1. Pick role(s)

Argument: `$ARGUMENTS`.

- **A specific external_id** → jump straight to that role.
- **`all`** → process every role in the pending queue, one at a time, in score order.
- **Empty, `--top N`, or "what should I apply to"** → **Dispatch the `digest-triager` subagent** (Sonnet) with `top_n` = N (default 5). The agent reads the latest digest in `digests/` (falling back to `job-finder digest-archive show` when the directory is missing or empty — `digests/` is gitignored working output that only exists after a local pipeline run), ranks pending roles against the fit profile in `profile/fit_profile.md`, and returns a ranked list with one-sentence reasoning per role. Surface the triager's list verbatim to the user and ask which to work — one external_id, several, or `all`.

  Fallback if the digest subagent dispatch fails: read the latest archived digest with `job-finder digest-archive show`. **Do not hand-roll a query against `data/jobs.db`.** Its `postings.applied_at` is rebuilt to NULL on every pipeline run, so a role applied to before that run reads as pending: filtering on it re-offered two roles on 2026-08-31 and both were applied to a second time. The durable answer lives in `data/state.db`. If you genuinely have to query `jobs.db`, pass the rows through `job_finder.applied.drop_applied()` before showing them, which is what `digest.py` and `review.py` both do.

- **No-auto-apply gate (runs for every chosen role, no exceptions).** After a role is picked but before drafting any materials, check its `company_name` (case-insensitive) against `job-finder no-auto list`. If it matches, **do not enter the apply loop for that role** — skip steps 2a–2i entirely. Instead, tell the user: the company is on the no-auto-apply list, surface the listed reason and the posting URL, and remind them to apply through their own channel. These companies stay in the digest on purpose (they want the signal); only the agent-driven apply is blocked. If the user said `all` or passed multiple ids, silently skip the blocked ones and process the rest, then note which were skipped in the batch summary.

### 2. For each chosen role, do this loop:

a. **Load context** (read these files once and keep in memory for the whole session; all paths come from `profile/profile.toml` `[paths]`, defaulting into `profile/`):
   - `<inputs_dir>/resume_master.md`
   - `<inputs_dir>/personal_statement.md`
   - the claims-ground-truth file at `[paths].claims_ground_truth_path` (default `profile/claims_ground_truth.md`) — per-claim framing rules, skill source pool
   - the writing-style file at `[paths].writing_style_path` — the voice rules for anything written as the user. Read it before drafting the cover letter, not after. Its Voice-mode section and its §8 (show the work, don't claim the match) are what keep a letter from reading AI-written.
   - the resume generator at `[paths].resume_skill_path` (default `profile/generate_resume.py`); read any SKILL.md or design notes sitting next to it, if present
   - The full row for this posting from `data/jobs.db` — including `jd_text`. If the DB is stale (it's rebuilt by each pipeline run) or `jd_text` is null, fetch the JD via WebFetch on the posting URL.
   - **Roles with no DB row at all** (a pasted URL, or a company from the digest's Manual check section) are first-class inputs, not errors. Fetch the JD from the live posting page — WebFetch first, the browser if the page is JS-walled — and hand-construct `posting_row` for step g. The ATS behind the URL never gates prep: any posting whose JD you can read gets the full loop below.

b. **Show the user a one-paragraph read of the JD** — what they're hiring for, the 3–5 keywords/frames that genuinely map to the user's resume, anything that risks overstatement. Ask the user for any orientation before you draft (sometimes they'll have a specific angle).

c. **Draft `RESUME_DATA`** as a Python dict, editing only what the resume generator's schema allows:
   - Reorder current-role bullets to lead with the strongest JD match
   - Adjust the title subtitle toward the JD's framing, staying within any subtitle rules the session-context file sets
   - Re-prioritize/rename skill categories per the session-context file's rules
   - Apply any per-application rotation rules the session-context file defines
   - Honor the anti-overstatement rules. If a JD keyword tempts overstatement, find a different angle or flag the gap for the cover letter.

   **Show the user a diff vs. the canonical `RESUME_DATA` in the resume generator at `[paths].resume_skill_path` (default `profile/generate_resume.py`).** Format as: changed-bullets-only. Wait for approval or edits.

d. **Draft the cover letter** as a dict matching `job_apply._render_cover_letter`'s schema:
   ```python
   {
     "date": "<today, written out like 'June 24, 2026'>",
     "recipient": "<Company> Hiring Team\n<Company>\n<City, State>",
     "salutation": "To the <Company> Hiring Team,",
     "paragraphs": ["...", "...", "...", "..."],  # 3–5 paragraphs
     "closing": "Thanks,",
     "title_subtitle": "<must match the title subtitle in resume_data>",
   }
   ```
   Voice: the user's. Source: personal statement + master resume. Every claim must be traceable. No em-dashes anywhere. No AI tropes ("spearheaded," "leveraged," "delve," "navigate the landscape," etc.). Show the user the draft, accept feedback.

e. **Draft 3–5 `why_this_matches` bullets** — short, factual, JD-keyword aligned. These go into `apply.md` for future reference.

f. **Dispatch the `materials-fact-checker` subagent** (Sonnet) with `resume_data`, `cover_letter`, `jd_text`, `company` inline in the prompt. The agent cross-checks every claim against `resume_master.md`, `personal_statement.md`, and the session-context file's anti-overstatement rules; returns severity-tagged findings (CRITICAL / MEDIUM / LOW / NIT).
   - If the verdict is **CLEAN**, proceed to step g.
   - If **FLAGS PRESENT**, surface the findings to the user, propose one-line fixes for each, and revise after they confirm. Re-dispatch the fact-checker on the revised drafts if any CRITICAL finding was edited. Loop until CLEAN.
   - If **BLOCK** (a fabricated metric or banned framing slipped in), do not proceed to render — fix the underlying claim first.

g. **On final approval, call render()** by running this in the repo's venv. **Pass `open_browser=False`** because step h dispatches the autofill subagent, which drives its own Playwright-controlled browser.

   Two forms, because the two surfaces differ. **Windows / Claude Code** (the repo
   venv has `job_finder` installed and every dependency):

   ```
   .venv/Scripts/python.exe -c "
   from job_finder import job_apply, db
   import json
   posting_row = json.loads('''<POSTING_ROW_JSON>''')  # build from DB row or hand-construct if DB is empty
   resume_data = json.loads('''<RESUME_DATA_JSON>''')
   cover_letter = json.loads('''<COVER_LETTER_JSON>''')
   why = json.loads('''<WHY_JSON>''')
   out = job_apply.render(posting_row=posting_row, resume_data=resume_data,
                          cover_letter=cover_letter, why_this_matches=why,
                          open_browser=False)
   print(out)
   "
   ```

   **A Linux device VM / Cowork** (no editable install, so `job_finder` is not
   importable and `.venv/Scripts/` does not exist). Same call, different prefix:

   ```
   PYTHONPATH=".cowork-deps:src" python3 -c "
   ...the identical body...
   "
   ```

   Build `.cowork-deps/` first with `sh scripts/bootstrap_cowork_deps.sh` if it is
   missing. `render()` needs `reportlab`, which an import-only check will not
   catch.

   `posting_row` must contain at minimum: `external_id`, `title`, `url`, `company_name`. Optional but used in `apply.md`: `total_score`, `queue`, `location`. If you're hand-constructing because the DB is empty (CI doesn't preserve `data/jobs.db` across runs), include all of these so the rendered `apply.md` is complete.

   Use the `Bash` tool. For large JSON payloads, write them to the scratchpad directory and load via `json.load(open(path))` to avoid awkward command-line escaping.

h. **Dispatch the `application-autofiller` subagent** (Sonnet) with `application_url` (the posting URL) and `folder_path` (the per-job folder returned by render()) inline in the prompt. If you drafted any short-answer text in step d that should be typed verbatim (cover-letter paste boxes, "Why this company" essay), include it as `short_answer_drafts` in the prompt.

   The autofiller drives the Playwright MCP through the form, fills every mappable field, uploads the PDFs, and **stops without submitting**. It reports back what was filled and what's blank. Surface that report to the user verbatim.

   **If the form can't be autofilled, the package still ships.** Autofill is a convenience layered on top of the deliverable, never a gate on it. When the application is behind an account wall (SuccessFactors, Workday, iCIMS, and Phenom-style portals usually are), requires a login, or presents a CAPTCHA, skip or recall the autofiller and write `APPLY_NOTES.md` into the per-job folder instead:
   - what exactly is blocked and why (account creation, login, CAPTCHA — the autofiller never creates accounts or enters passwords)
   - what's ready in the folder (resume, cover letter, `standard_answers.md`, `apply.md`)
   - the posting URL, req id, and any file-type limits the portal states
   - a short ordered list of the manual steps left

   Then tell the user directly that this one needs a hand-submit and point them at the folder. Known-walled ATSes can skip the autofill attempt entirely and go straight to `APPLY_NOTES.md`.

   **If the Playwright MCP isn't loaded** (the session isn't rooted in `projects/job-finder/`), the autofiller will report this and stop. Write the same `APPLY_NOTES.md` handoff — do not fall back to another browser tool.

i. **Handoff.** Tell the user:
   - Folder path (markdown link)
   - That the resume + cover letter PDFs are inside
   - To review every field in the open browser window before submitting
   - To run `.venv/Scripts/job-finder.exe mark-applied <external_id>` from the repo root after submitting

### 3. Batching

If the user said `all` or multiple ids, process them sequentially. Between roles, summarize what you did (one line per role) and pause briefly to let them interject.

## Rules

- **The ATS never gates prep — only who pushes Submit.** Every role with a readable JD gets the full loop (tailor, fact-check, render). Autofill runs when the form is reachable; when it isn't, the loop ends with a complete package plus an `APPLY_NOTES.md` handoff, never with a skipped role.
- **Honor the no-auto-apply list.** `job-finder no-auto list` names companies the user handles through their own contacts. Never draft, render, or autofill an application for any role whose company is on that list — surface it for awareness and stop. This gate is non-negotiable even if they pass the role's `external_id` directly.
- **Never invent facts.** Every claim must be in `resume_master.md` or `personal_statement.md` or something the user said in this conversation.
- **Anti-overstatement.** Read the session-context file named in `profile/profile.toml [paths]` and apply every rule in it literally (per-claim framing rules, the fixed skill-category count, the skill source pool). The `materials-fact-checker` subagent will also enforce these — they're belt-and-suspenders.
- **Show before render.** Always show the user the RESUME_DATA changes and cover letter draft, then run the fact-checker, then surface findings. They get the last word on every revision before render() fires.
- **Don't auto-mark applied.** The user submits by hand and runs `mark-applied` after.
- **Never submit the form.** The autofiller subagent has hard guardrails against clicking Submit / Apply / Send. Salary fields always stay blank.
- **One role at a time** unless he explicitly says `all`.

## Subagent quick reference

| Subagent | Purpose | Inputs | Model |
|---|---|---|---|
| `digest-triager` | Rank pending roles by fit | `top_n`, optional filters | Sonnet |
| `materials-fact-checker` | Cross-check drafted resume + cover letter against ground truth | `resume_data`, `cover_letter`, `jd_text`, `company` | Sonnet |
| `application-autofiller` | Drive Playwright autofill, stop before submit | `application_url`, `folder_path`, optional `short_answer_drafts` | Sonnet |
