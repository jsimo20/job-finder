---
description: Tailor resume + cover letter for pending roles and prep apply package
argument-hint: [external_id or --top N]
---

You are driving the apply-prep loop for the user. The pipeline that picks the roles is `job-finder`; the tailoring ground truth lives in the profile driving docs (`resume_master.md`, `personal_statement.md`, and the session-context file named by `profile/profile.toml` `[paths]`). The deterministic render lives in `src/job_finder/job_apply.py`.

## What to do

Three subagents (all Sonnet) handle the mechanical phases of this command so the main Opus-tier conversation can focus on drafting work that benefits from Opus voice and judgment. Dispatch them via the `Agent` tool with the indicated `subagent_type`. Each starts with cold context — pass the inputs it needs inline in the prompt.

### 1. Pick role(s)

Argument: `$ARGUMENTS`.

- **A specific external_id** → jump straight to that role.
- **`all`** → process every role in the pending queue, one at a time, in score order.
- **Empty, `--top N`, or "what should I apply to"** → **Dispatch the `digest-triager` subagent** (Sonnet) with `top_n` = N (default 5). The agent reads the latest digest in `digests/`, ranks pending roles against the fit profile in `profile/fit_profile.md`, and returns a ranked list with one-sentence reasoning per role. Surface the triager's list verbatim to the user and ask which to work — one external_id, several, or `all`.

  Fallback if the digest subagent dispatch fails: query `data/jobs.db` directly for the top N pending unapplied roles (`applied_at IS NULL` and `dismissed_at IS NULL`), sorted by `total_score DESC`, using the same SQL shape as `review.py:PENDING_SQL`.

- **No-auto-apply gate (runs for every chosen role, no exceptions).** After a role is picked but before drafting any materials, check its `company_name` (case-insensitive) against the `companies[].name` entries in `data/no_auto_apply.json`. If it matches, **do not enter the apply loop for that role** — skip steps 2a–2i entirely. Instead, tell the user: the company is on the no-auto-apply list, surface the `reason` from the file and the posting URL, and remind them to apply through their own channel. These companies stay in the digest on purpose (they want the signal); only the agent-driven apply is blocked. If the user said `all` or passed multiple ids, silently skip the blocked ones and process the rest, then note which were skipped in the batch summary.

### 2. For each chosen role, do this loop:

a. **Load context** (read these files once and keep in memory for the whole session):
   - `<inputs_dir>/resume_master.md`
   - `<inputs_dir>/personal_statement.md`
   (inputs_dir comes from `profile/profile.toml` `[paths]`; default `profile/`)
   - `~/.claude/ai_skills/SESSION_CONTEXT_Jobsearch.md`
   - `~/.claude/ai_skills/resume_generator/SKILL.md` (design rules)
   - `~/.claude/ai_skills/cover_letter_skill/SKILL.md` (cover-letter rules)
   - The full row for this posting from `data/jobs.db` — including `jd_text`. If the DB is empty (CI rebuilds it each run, doesn't commit) or `jd_text` is null, fetch the JD via WebFetch on the posting URL.

b. **Show the user a one-paragraph read of the JD** — what they're hiring for, the 3–5 keywords/frames that genuinely map to the user's resume, anything that risks overstatement. Ask the user for any orientation before you draft (sometimes they'll have a specific angle).

c. **Draft `RESUME_DATA`** as a Python dict, following the tailoring workflow in `resume_generator/SKILL.md`:
   - Reorder current-role bullets to lead with the strongest JD match
   - Adjust title subtitle (e.g., "Mobile, AI & SaaS Growth"; "AI, Developer Platforms & Trusted Automation"; "AI, Platforms & Zero-to-One Consumer Products"). Use "zero-to-one" spelled out — never the "0→1" glyph.
   - Re-prioritize/rename skill categories per `SESSION_CONTEXT` rules
   - Rotate the fourth clause in the fun bullet
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

f. **Dispatch the `materials-fact-checker` subagent** (Sonnet) with `resume_data`, `cover_letter`, `jd_text`, `company` inline in the prompt. The agent cross-checks every claim against `resume_master.md`, `personal_statement.md`, and `SESSION_CONTEXT_Jobsearch.md` anti-overstatement rules; returns severity-tagged findings (CRITICAL / MEDIUM / LOW / NIT).
   - If the verdict is **CLEAN**, proceed to step g.
   - If **FLAGS PRESENT**, surface the findings to the user, propose one-line fixes for each, and revise after they confirm. Re-dispatch the fact-checker on the revised drafts if any CRITICAL finding was edited. Loop until CLEAN.
   - If **BLOCK** (a fabricated metric or banned framing slipped in), do not proceed to render — fix the underlying claim first.

g. **On final approval, call render()** by running this in the repo's venv. **Pass `open_browser=False`** because step h dispatches the autofill subagent, which drives its own Playwright-controlled browser.

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

   `posting_row` must contain at minimum: `external_id`, `title`, `url`, `company_name`. Optional but used in `apply.md`: `total_score`, `queue`, `location`. If you're hand-constructing because the DB is empty (CI doesn't preserve `data/jobs.db` across runs), include all of these so the rendered `apply.md` is complete.

   Use the `Bash` tool. For large JSON payloads, write them to the scratchpad directory and load via `json.load(open(path))` to avoid awkward command-line escaping.

h. **Dispatch the `application-autofiller` subagent** (Sonnet) with `application_url` (the posting URL) and `folder_path` (the per-job folder returned by render()) inline in the prompt. If you drafted any short-answer text in step d that should be typed verbatim (cover-letter paste boxes, "Why this company" essay), include it as `short_answer_drafts` in the prompt.

   The autofiller drives the Playwright MCP through the form, fills every mappable field, uploads the PDFs, and **stops without submitting**. It reports back what was filled and what's blank. Surface that report to the user verbatim.

   **If the Playwright MCP isn't loaded** (the session isn't rooted in `projects/job-finder/`), the autofiller will report this and stop. Tell the user to fill the form by hand using the folder + URL — do not fall back to another browser tool.

i. **Handoff.** Tell the user:
   - Folder path (markdown link)
   - That the resume + cover letter PDFs are inside
   - To review every field in the open browser window before submitting
   - To run `.venv/Scripts/job-finder.exe mark-applied <external_id>` from the repo root after submitting

### 3. Batching

If the user said `all` or multiple ids, process them sequentially. Between roles, summarize what you did (one line per role) and pause briefly to let them interject.

## Rules

- **Honor the no-auto-apply list.** `data/no_auto_apply.json` names companies the user handles through their own contacts. Never draft, render, or autofill an application for any role whose company is on that list — surface it for awareness and stop. This gate is non-negotiable even if they pass the role's `external_id` directly.
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
