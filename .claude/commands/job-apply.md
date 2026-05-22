---
description: Tailor resume + cover letter for pending roles and prep apply package
argument-hint: [external_id or --top N]
---

You are driving the apply-prep loop for James. The pipeline that picks the roles is `boston-pm-tracker`; the tailoring rules live in `~/.claude/ai_skills/resume_generator/SKILL.md`, `~/.claude/ai_skills/cover_letter_skill/SKILL.md`, and `~/.claude/ai_skills/SESSION_CONTEXT_Jobsearch.md`. The deterministic render lives in `src/boston_pm_tracker/job_apply.py`.

## What to do

### 1. Pick role(s)

Argument: `$ARGUMENTS`.

- Empty or `--top N`: query `data/jobs.db` for the top N (default 5) pending unapplied roles, sorted by `total_score DESC`. Use the same SQL shape as `review.py:PENDING_SQL`. Print a compact list (idx, external_id, company, title, score, queue, location, age_days). Ask James which to work — one external_id, several, or `all`.
- A specific external_id: jump straight to that role.
- `all`: process every role in the pending queue, one at a time, in score order.

### 2. For each chosen role, do this loop:

a. **Load context** (read these files once and keep in memory for the whole session):
   - `~/path/to/job-search/inputs/resume_master.md`
   - `~/path/to/job-search/inputs/personal_statement.md`
   - `~/.claude/ai_skills/SESSION_CONTEXT_Jobsearch.md`
   - `~/.claude/ai_skills/resume_generator/SKILL.md` (design rules)
   - `~/.claude/ai_skills/cover_letter_skill/SKILL.md` (cover-letter rules)
   - The full row for this posting from `data/jobs.db` — including `jd_text`. If `jd_text` is null, fetch the JD via the URL with WebFetch.

b. **Show the user a one-paragraph read of the JD** — what they're hiring for, the 3-5 keywords/frames that genuinely map to James's resume, anything that risks overstatement. Ask James for any orientation before you draft (sometimes he'll have a specific angle).

c. **Draft `RESUME_DATA`** as a Python dict, following the tailoring workflow in `resume_generator/SKILL.md`:
   - Reorder Contoso bullets to lead with the strongest JD match
   - Adjust title subtitle (e.g., "Mobile, AI & SaaS Growth"; "AI, Platforms & Zero-to-One Consumer Products"). Use "zero-to-one" spelled out — never the "0→1" glyph.
   - Re-prioritize/rename skill categories per `SESSION_CONTEXT` rules
   - Rotate the fourth clause in the fun bullet
   - Honor the anti-overstatement rules. If a JD keyword tempts overstatement, find a different angle or flag the gap for the cover letter.

   **Show James a diff vs. the canonical `RESUME_DATA` in `~/.claude/ai_skills/resume_generator/generate_resume.py`.** Format as: changed-bullets-only. Wait for approval or edits.

d. **Draft the cover letter** as a dict matching `job_apply._render_cover_letter`'s schema:
   ```python
   {
     "date": "<today, written out like 'May 17, 2026'>",
     "recipient": "Hiring Team\n<Company>\n<City, State>",
     "salutation": "To the Hiring Team,",
     "paragraphs": ["...", "...", "..."],  # 3-5 paragraphs
     "closing": "Looking forward to talking,",
     "title_subtitle": "<must match the title subtitle in resume_data>",
   }
   ```
   Voice: James's. Source: personal statement + master resume. Every claim must be traceable. Show James the draft, accept feedback.

e. **Draft 3-5 `why_this_matches` bullets** — short, factual, JD-keyword aligned. These go into `apply.md` for future reference.

f. **On approval, call render()** by running this in the repo's venv:

   ```
   .venv/Scripts/python.exe -c "
   from boston_pm_tracker import job_apply, db
   from pathlib import Path
   with db.connect() as conn:
       row = dict(conn.execute(
           '''SELECT p.external_id, p.title, p.url, p.location, c.name AS company_name,
                     s.total_score, s.queue
              FROM postings p JOIN companies c ON c.id = p.company_id
              JOIN scores s ON s.posting_id = p.id
              WHERE p.external_id = ?''', ('<external_id>',)
       ).fetchone())
   import json
   resume_data = json.loads('''<RESUME_DATA_JSON>''')
   cover_letter = json.loads('''<COVER_LETTER_JSON>''')
   why = json.loads('''<WHY_JSON>''')
   out = job_apply.render(posting_row=row, resume_data=resume_data,
                          cover_letter=cover_letter, why_this_matches=why)
   print(out)
   "
   ```

   Use the `Bash` tool. Write the JSON payloads to temp files in `/tmp/` if they're large enough to be awkward on the command line — then read from the files instead.

g. **After render() returns**, the per-job folder path is printed to stdout. The browser should auto-open the apply URL. Tell James:
   - Folder path (markdown link)
   - That the resume + cover letter PDFs are inside
   - To run `boston-pm-tracker mark-applied <external_id>` after he hits submit
   - QA checklist items in `apply.md` to eyeball before submitting

### 3. Batching

If James said `all` or multiple ids, process them sequentially. Between roles, summarize what you did (one line per role) and pause briefly to let him interject.

## Rules

- **Never invent facts.** Every claim must be in `resume_master.md` or `personal_statement.md` or something James said in this conversation.
- **Anti-overstatement.** Read `SESSION_CONTEXT_Jobsearch.md` rules and apply them. Specifically: Connection Manager is not zero-to-one; AI agent is Phase 1 / business case projection; smart home is leading indicator + addressable market (not "delivered across 8M"); exactly 4 skill categories; no skills outside the source pool.
- **Show before render.** Always show James the RESUME_DATA changes and cover letter draft before invoking `render()`. He gets the last word.
- **Don't auto-mark applied.** James submits by hand. He runs `mark-applied` after.
- **One role at a time** unless he explicitly says `all`.
