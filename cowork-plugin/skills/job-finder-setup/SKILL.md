---
name: job-finder-setup
description: Set up job-finder for a new person from inside Cowork, with no terminal, no git and no Python knowledge on their side. Installs the engine into the connected folder, builds their profile and search settings through a plain-language interview, builds and probes a company list they only have to prune, and proves the first collect runs. Use when someone says "set me up", "update me", "set up job finder", "get started", or has just installed this plugin.
---

# job-finder-setup

You are setting up a job-search tool for someone who may never have used a
terminal, git, or an AI tool before. They will not see the commands you run,
only your messages.

This launcher only gets the engine into their folder. **The setup itself is
`.claude/skills/job-finder-setup/SKILL.md` inside the engine, and it updates
with the engine;** step 2 hands over to it. Until then: plain words, one
question at a time, and never paste command output at them.

## Before anything

Confirm there is a connected folder named `job-finder`. If there is not, ask
them to make an empty folder called `job-finder` directly in their home folder
(on a Mac, open Finder and choose **Go > Home**; on Windows,
`C:\Users\<your name>`), not in Documents, connect it with the **+** next to
the message box, and wait. The form-filling browser can attach files only from
that spot. Everything below happens inside it. Call its path `$ROOT`.

Check the tools you need exist in your own environment, silently:

```sh
python3 --version      # needs 3.10 or newer
```

If Python is older than 3.10 or missing, stop and say the tool cannot run on
this setup yet. Do not improvise an install.

Then check that every site the engine needs is reachable from here. Any HTTP
answer, even a 404, means reachable; only a connection that never completes
counts as blocked:

```sh
for u in https://github.com/jsimo20/job-finder https://codeload.github.com \
         https://pypi.org/simple/httpx/ https://files.pythonhosted.org \
         https://api.greenhouse.io https://boards-api.greenhouse.io \
         https://api.lever.co https://jobs.ashbyhq.com https://api.ashbyhq.com \
         https://builtin.com; do
  curl -sS -o /dev/null --max-time 15 "$u" 2>/dev/null && echo "ok      $u" || echo "BLOCKED $u"
done
```

- **All ok:** say nothing about it and carry on.
- **Any blocked:** stop before touching the folder. Nothing below works
  without these sites, and a half-finished setup is harder to resume than one
  that never started. Send this, one message, then wait:

  > Before I can set anything up, Claude needs permission to reach the job
  > boards. Right now this account only lets me reach a short list of
  > websites. To change it, open **Settings** in the Claude app, go to
  > **Capabilities**, turn on **Allow network egress**, and set the domain
  > allowlist to **All domains**. Then start a new chat in this folder and
  > say "set me up" again. The change only applies to new chats.
  >
  > If your Claude account belongs to a company or team, only its
  > administrator can change this setting. If they'd rather allow specific
  > sites than all of them, send them this list: <every blocked host>.
  > Choosing **All domains** works better, because the weekly run also opens
  > companies' own careers pages.

  Name the hosts that failed, not the whole list. Never suggest a different
  settings path, a workaround, or a retry in this chat.


## 1. Put the engine in the folder

**Already installed** (`$ROOT/pyproject.toml` exists and names `job-finder`):
bring it up to date, then go to step 2. A failure here never stops setup.

```sh
cd "$ROOT" && if [ -f scripts/self_update.sh ]; then sh scripts/self_update.sh; else
  curl -fsSL --max-time 60 https://github.com/jsimo20/job-finder/archive/refs/heads/main.tar.gz \
    | tar xz --strip-components=1 --overwrite; fi
```

**Not installed:**

```sh
cd "$ROOT" && curl -fsSL --max-time 120 https://github.com/jsimo20/job-finder/archive/refs/heads/main.tar.gz | tar xz --strip-components=1
```

Never `git clone` here: on a Cowork folder mount the clone breaks partway and
leaves an unfinished `.git` behind.

Then install the Python packages the engine needs, into the folder:

```sh
cd "$ROOT" && sh scripts/bootstrap_cowork_deps.sh
```

Tell them the engine is in place. One line.

## 2. Hand over

Read `$ROOT/.claude/skills/job-finder-setup/SKILL.md` and follow it: its
"Updating an existing folder" section when `$ROOT/profile/profile.toml`
exists, otherwise from its step 1. Everything about the profile, the search, the companies, the
schedule and the hand-off is there.

If that file is missing after step 1, the download did not complete. Say
setup could not finish getting the engine and to try "set me up" again in a
new chat, and stop.
