# profile.example/

The committed template for your private `profile/` directory. Copy it and fill
it in:

```sh
cp -r profile.example profile
```

`profile/` is gitignored. Everything personal lives there: who you are, your
EEO answers, your master resume, your writing voice. The pipeline (CI) never
reads it; only the local apply workflow does.

## What each file is for

| File | Used by | What it drives |
|---|---|---|
| `profile.toml` | everything apply-side | Identity on PDFs, autofill contact values, EEO defaults, paths |
| `resume_master.md` | tailoring + fact-checker | Ground truth: every resume bullet must trace to it |
| `personal_statement.md` | tailoring + fact-checker | Your narrative voice; cover letters are checked against its tone |
| `writing-style.md` | cover-letter drafting + fact-checker + `letter_linter` | The voice rules for anything written as you; the fact-checker runs its self-check list, the linter enforces a fixed subset in code |
| `standard_answers.md` | form autofill + autofill agent | Contact block plus your stock answers to common screening questions |
| `fit_profile.md` | digest-triager agent | What "a great role for you" means, so triage can rank the digest |
| `qa_checklist.md` | `job_apply.render()` | Per-application checklist written into every apply.md |
| `claims_ground_truth.md` | tailoring | Per-claim framing rules, skill source pool, and metrics the LLM must not inflate |
| `generate_resume.py` | `job_apply.render()` | Resume PDF generator; edit only the RESUME_DATA block |

Only `profile.toml` is strictly required to run the pipeline-side tooling.
The apply workflow needs the rest, and tells you which file is missing when it
needs one.

## Rules

- Never commit `profile/`. The `.gitignore` already excludes it; leave that be.
- Fill `resume_master.md` with facts you can defend in an interview. The
  fact-checker treats it as ground truth, so anything overstated here gets
  faithfully overstated everywhere.
- EEO values in `profile.toml` are voluntary. Leave them `""` to answer by
  hand on every form.
