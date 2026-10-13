---
name: interview-prep
description: Prepare the user for an interview on a role they applied to, then run a mock interview with feedback after every answer. Re-reads the job description, the resume and cover letter they sent, and their ground truth, so nothing they rehearse goes beyond what they can defend. Use when the user says "prep me for my interview", "I have an interview with <company>", "mock interview", "practice the panel", or "help me get ready for the call".
---

# interview-prep

The user has an interview coming. Your job is a prep document they can read
the night before and a mock interview that grades each answer against what
they actually did.

**`$PY` below means `PYTHONPATH=".cowork-deps:src" python3` on Cowork and
`.venv/Scripts/python.exe` on Windows, run from the repo root.**

## 1. Find the application

Resolve every path through the profile; never assume a folder layout:

```sh
$PY -c "
from job_finder import job_apply
c = job_apply.load_config()
for k in ('applications_dir', 'claims_ground_truth', 'resume_master_md',
          'personal_statement_md', 'story_bank_md', 'writing_style'):
    print(k, getattr(c, k))
"
```

List the folders under `applications_dir` whose name carries the company.
More than one role there: ask which. None: they applied outside this tool, so
ask them to paste the job description and say which resume they sent, then
carry on with what exists and say once what is missing.

## 2. Read what they sent

| File in the folder | What it is |
|---|---|
| `jd.md` | The job description as it stood when they applied |
| `cover_letter.json` | The letter they sent |
| `*_Resume_*.py` | The resume they sent; its `RESUME_DATA` block is the content (the PDF is not readable input) |
| `apply.md` | Why the role matched, and the gaps named at the time |
| `skill_substitutions.json` | Job-description terms written onto the resume in place of their own wording; each one is a likely "how have you used X?" question, and the file records what it stands on |
| `APPLY_NOTES.md` | Anything noted at submit time, if present |

No `jd.md` (folders made before it existed): fetch the URL in `apply.md`. If
the posting has closed, ask them to paste the description if they kept it;
otherwise build from the letter and resume and say the prep has no job
description behind it.

Then read the ground truth: the claims file, `resume_master.md`, the
personal statement, and the story bank if it exists. **Anything they say in
the interview is held to the same rules as the letter.** A number is quoted
exactly as the claims file has it, a projection stays a projection, and a
detail tagged `[confirm]` in the story bank is not usable.

## 3. Ask about the round

One question at a time:

1. Which round: recruiter screen, hiring manager, panel, case or technical,
   final.
2. Who: names and titles of everyone in the room.
3. When, and whether it is video, phone or onsite.
4. Any assignment or presentation they were asked to bring.
5. Anything from earlier rounds: what was asked, what landed, what did not.

## 4. Research

With web search: the company's recent news, products, strategy and, for a
public company, the latest earnings themes; each interviewer's public
professional background (current role and tenure, prior companies, public
talks or posts). Professional record only; never their personal life.
Without search, say so in one line and build from the job description.

From that, decide what each interviewer is likely testing. A leader building
a new team tests judgment and ownership; a peer tests how the work gets done
day to day; a recruiter tests motivation, logistics and pay.

## 5. Write the prep document

Write `<folder>/interview_prep_<round>.md` (add the interviewer's name when
the round is one person). Read it back after writing. Sections, in order:

1. **The role.** One paragraph: what they are really hiring for.
2. **The interviewers.** One short block each: background, and what they
   will likely test.
3. **Likely questions.** Eight to twelve. For each: the story or resume line
   to answer with, the honest framing, and the trap (where an answer would
   overstate).
4. **Gaps they will probe.** From `apply.md`'s named gaps and the
   substitutions file. For each: state the gap plainly, the closest real
   experience, and how they would close it. Never coach them to hide one.
5. **Numbers to keep exact.** Every figure from the claims file this role
   will touch, with its required framing.
6. **Questions to ask them.** Three to five, specific to this company and
   these interviewers.
7. **Before the call.** Pay: if the posted range sits below `comp_floor` in
   `config/pipeline.toml [filters]`, say so and tell them to decide whether
   it is viable before the call, not during it. Plus any assignment due.

Any answer drafted in their voice follows the writing-style file.

## 6. Mock interview

Offer it once the document is written. They may answer by voice-to-text;
ignore transcription noise.

- **Play the interviewer, in character**, from step 4. Short turns; real
  interviewers do not monologue.
- **One question at a time**, then wait. Open the way this round opens
  ("tell me about yourself" for most). About six questions for one
  interviewer. For a panel, rotate between the panelists, each asking from
  their own angle, about eight in all.
- **After every answer, break character** under a `Feedback` heading:
  - what landed;
  - what this interviewer would catch or push on;
  - any claim beyond the ground truth, quoted, with the correct framing;
  - a tightened version of the answer, built only from their own material.

  Then return in character with the next question.
- **Probe one real gap** the way this interviewer would, and grade how they
  handle it.
- **Never invent experience** for a tightened answer. If the best answer
  needs a fact the ground truth does not hold, ask them whether it is true.
- **Close with a scorecard**: the strongest answers, the two or three to
  rework, and any phrase to stop saying. Append it to the prep document.

A feedback turn, for a fictional candidate (an operations analyst
interviewing at Northfold Freight, whose claims file says delivery delays
fell 18% in a two-region pilot):

> **Feedback**
> - Landed: you named the problem before the fix, and the pilot scope.
> - She would push on: who owned the routing change, you or the vendor.
> - Overstated: "we cut delays by about a third across the network." Your
>   record says 18%, in a two-region pilot. Say exactly that.
> - Tighter: "I ran a two-region pilot on the new routing rules and delays
>   fell 18%. The network rollout was planned for the following quarter."

## 7. After the round

If they come back after the interview, ask what was asked and append it to
the prep document under `Asked in round <n>`, so the next round's prep starts
from it. A new fact they mention goes into the story bank only with their
explicit yes, and tagged `[confirm]` until they confirm the details.

## Never

- Contact an interviewer or the company, or post anything anywhere.
- Write anything outside the application folder.
- Coach an answer the ground truth does not support.
