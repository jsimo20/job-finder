---
name: job-finder
description: Everything job-finder does after setup. Use for "run my weekly job search", a scheduled weekly run, "work through the top roles", "add companies: Acme, Globex", "remove a company", "find me more companies", "help me apply to this job" with a link or a pasted job description, "prep me for my interview", "mock interview", or "change my settings". Takes the user's request as its argument.
---

# job-finder

This launcher holds no procedure. **Read `.claude/skills/job-finder/SKILL.md`
in the connected folder and follow it, passing `$ARGUMENTS` through.** It
updates the engine, then picks the procedure for the request. Every procedure
lives in that folder and updates with it, so nothing is restated here.

## If that file is missing

- **No `pyproject.toml` naming `job-finder` in the folder:** job-finder is not
  set up here. Say so in one line and suggest "set me up". Stop.
- **The engine is there but the file is not:** it was installed before this
  launcher existed. Update it once, then read the file:

  ```sh
  curl -fsSL --max-time 60 https://github.com/jsimo20/job-finder/archive/refs/heads/main.tar.gz \
    | tar xz --strip-components=1 --overwrite
  ```

  If the file is still missing, say the update did not complete and stop.

Never improvise an application, a weekly run or interview prep without the
folder. There is no profile and no ground truth to check claims against.
