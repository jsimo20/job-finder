---
name: job-finder
description: Entry point for everything job-finder does after setup. Routes the request to the procedure that handles it - the weekly run, managing the company list, applying to one role the user found or pasted, interview prep and mock interviews, or changing their profile and search settings.
---

# job-finder

Every procedure lives in this folder and updates itself; this file only picks
one. Run from the repo root.

## 1. Update first

```sh
sh scripts/self_update.sh
```

It prints one line. A failure never stops the request: carry on with the
current files and mention it in one line at the end. It skips itself on a
developer checkout and when it already ran this hour.

## 2. Pick the procedure

| The user wants | Read and follow |
|---|---|
| The weekly run: "run my weekly job search", "work through the top roles", a scheduled run | `.claude/skills/job-finder-weekly/SKILL.md` |
| To add, remove, list or find more companies, or stop one being applied to | `.claude/skills/manage-companies/SKILL.md` |
| Help applying to one role: a pasted link, a pasted job description, a company from the digest's **Manual check** | `.claude/commands/job-apply.md`, for that one role |
| Interview prep, a mock interview, "I have an interview with..." | `.claude/skills/interview-prep/SKILL.md` |
| To change their profile, resume, voice, titles, places or pay | `.claude/skills/job-finder-setup/SKILL.md`, from the step that covers it |

Pass the user's own words through as the procedure's arguments. A request
that fits none: say in one line each what this can do, and ask which.

## 3. On Cowork

- **Every Python call is prefixed `PYTHONPATH=".cowork-deps:src" python3`.**
  On Windows use `.venv/Scripts/python.exe` with no prefix.
- **The `job-finder` console script does not exist on Cowork.** Where a
  procedure names one, call the module function instead:

  | Console command | Cowork equivalent |
  |---|---|
  | `job-finder no-auto list` | `state.is_no_auto('<company>')` |
  | `job-finder digest-archive show` | `state.get_digest()['body']` |
  | `job-finder mark-applied <id>` / `applied add` | `applied.record_applied('<id>', company=..., title=..., url=...)` |
  | `job-finder companies ...` | `manage-companies` above |

- **`fill_greenhouse` does not run on Cowork.** Every form goes through the
  `application-autofiller` agent.
- **Nothing is ever submitted.** Every form is left open for the user.
