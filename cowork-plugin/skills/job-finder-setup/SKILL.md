---
name: job-finder-setup
description: Set up job-finder for a new person from inside Cowork, with no terminal, no git and no Python knowledge on their side. Installs the engine into the connected folder, builds their profile and search settings through a plain-language interview, builds and probes a company list they only have to prune, and proves the first collect runs. Use when someone says "set me up", "set up job finder", "get started", or has just installed this plugin.
---

# job-finder-setup

You are setting up a job-search tool for someone who may never have used a
terminal, git, or an AI tool before. They will not see the commands you run,
only your messages. Everything technical is yours to do; everything personal
is theirs to tell you.

## How to talk

- Plain words. No "repo", "clone", "regex", "TOML", "env var". Say "folder",
  "copy", "pattern", "settings file".
- One question at a time. Wait for the answer before the next one.
- Say what you are about to do in one line, do it, then say what happened in
  one line. Never paste command output at them.
- Nothing they tell you leaves the connected folder. Say that once, near the
  start, in one sentence.
- Never ask for a password, an API key, or a payment detail in chat.

## Before anything

Confirm there is a connected folder. If there is not, ask them to connect an
empty folder (suggest a new one called `job-finder` in their Documents) and
wait. Everything below happens inside it. Call its path `$ROOT`.

Check the tools you need exist in your own environment, silently:

```sh
python3 --version      # needs 3.10 or newer
git --version || true  # optional; the tarball route below works without it
```

If Python is older than 3.10 or missing, stop and say the tool cannot run on
this setup yet. Do not improvise an install.

Then check the form-filling half. The browser that fills applications runs on
their computer, not in your environment, and it needs Node.js there. You
cannot see their computer, but you can see the result: **look through your
own tool list for any tool whose name contains `playwright`** (the exact
prefix varies by surface; match on the word, never on a fixed prefix).

- **Present:** say nothing about it and carry on.
- **Absent:** Node.js is not installed on their computer, and nothing you can
  run will install it for them. Walk them through it, one message, no jargon:

  > One small install first, so I can fill application forms for you later.
  > Open https://nodejs.org in your browser and click the big green button
  > marked **LTS** to download it. Open the downloaded file and click Next
  > until it finishes; the defaults are fine. Then quit the Claude app
  > completely and open it again, come back to this folder, and tell me
  > "set me up" again. I will pick up where we left off.

  Then stop and wait. Every step below skips what already exists, so the
  second run resumes rather than restarts. If the tools are still absent on
  the second run, say that form filling will not work on this computer yet
  and that everything else will, and carry on; the weekly run prepares every
  application either way and leaves the form for them to fill by hand.

Never ask them what Node is, whether they have it, or to run anything. The
tool list is the only check, and the install is the only ask.

## 1. Put the engine in the folder

Skip this step when `$ROOT/pyproject.toml` already exists and names
`job-finder`.

```sh
cd "$ROOT" && git clone --depth 1 https://github.com/jsimo20/job-finder.git . 
```

If git is unavailable or the clone fails, take the tarball route:

```sh
cd "$ROOT" && curl -fsSL https://github.com/jsimo20/job-finder/archive/refs/heads/main.tar.gz | tar xz --strip-components=1
```

Then install the Python packages the engine needs, into the folder:

```sh
cd "$ROOT" && sh scripts/bootstrap_cowork_deps.sh
```

**Every Python command from here on is prefixed
`PYTHONPATH=".cowork-deps:src" python3`, run from `$ROOT`.** Without the prefix
the engine's own modules are not importable here.

Tell them the engine is in place. One line.

## 2. Build their profile

Create the starting files:

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.profile_init
```

That writes `profile/profile.toml`, `profile/resume_master.md`,
`profile/personal_statement.md`, `profile/standard_answers.md`,
`profile/fit_profile.md`, `profile/claims_ground_truth.md`,
`profile/writing-style.md`, `profile/qa_checklist.md` and
`profile/generate_resume.py`, each holding example values. Your job is to
replace the examples with their real answers, file by file, through
conversation. The order below matters: later files are checked against
earlier ones.

**After every file you write, read it back and confirm the content landed.**
A write that silently fails here looks identical to one that worked.

### 2a. Resume, the ground truth

Ask them to drop their current resume into the folder (PDF, Word or text).
Read it. Draft `profile/resume_master.md` from it: every role, dates, bullets
and skills as written, nothing added, nothing rounded. Show them the draft in
chat and ask what is wrong or missing. Only after they confirm, write it.

This file is the fact-checker's authority: anything a later cover letter says
that is not in it gets flagged. Say that to them in one sentence, so they know
why you are being exact.

Then fill the `RESUME_DATA` block in `profile/generate_resume.py` from the
same confirmed content. Edit only that block.

### 2b. Identity and form answers

From the resume plus a few questions, fill `profile/profile.toml`:

- `[identity]`: name, email, phone, LinkedIn, GitHub if any, city, and the
  one-line `title_subtitle` (ask: "how would you describe yourself in one
  line at the top of a cover letter?").
- `[answers]`: ask two questions in plain words. "Are you legally allowed to
  work in your country without a visa sponsor?" and "Would you need a company
  to sponsor a visa now or later?" Set `work_authorized` and
  `requires_sponsorship` from the answers; set `country`.
- `[eeo]`: ask whether they want the voluntary self-identification questions
  (gender, ethnicity, veteran status, disability) answered automatically on
  forms. If no, leave every value `""`, which means they answer by hand.

Then `profile/standard_answers.md`: the contact block from the same values,
the work authorization lines, and their stock answers to "how did you hear
about us", "willing to work hybrid or onsite", "earliest start date". Ask for
each.

### 2c. Their voice

Ask them to write, in chat, in their own words, a few paragraphs about their
work: what they did, what they are looking for, what they are proud of. Tell
them not to polish it. Put it into `profile/personal_statement.md` as they
wrote it, fixing nothing but obvious typos. The cover letters are checked
against this for tone, so a polished version would make every letter sound
unlike them.

Leave `profile/writing-style.md` as shipped.

### 2d. What a good role looks like

Ask: what kind of companies, what kind of work, what would make them say no.
Write `profile/fit_profile.md` from the answers in the shipped file's four
sections (strong positive, mild positive, mild negative, strong negative).

### 2e. Claims they can defend

`profile/claims_ground_truth.md` holds the numbers and skills a draft may use
and how each must be framed. Seed it from the confirmed resume: every metric,
with its exact figure; every skill, under the shipped file's source-pool
headings. Ask about any figure that looks rounded ("is that exactly 40%, or
about 40%?") and record what they say.

### 2f. Prove the profile

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.profile_check
```

Exit 0 is the bar. Fix every listed issue before going on; the apply tooling
refuses to run on a profile with placeholders in it. The check also wants
`config/pipeline.toml` and a company list, which the next two steps create,
so run it again after step 4.

## 3. Their search

Copy `config/pipeline.example.toml` to `config/pipeline.toml` and edit it from
an interview. Ask, in this order:

1. **Where they live** and the country they can work from. Sets
   `[location] country` and the commute notes.
2. **Which cities or regions** they would take an office job in, and roughly
   how far each is from home. Sets `in_scope_patterns` and the three commute
   tiers. Write the patterns from the place names they give, including state
   or county abbreviations the way job boards print them.
3. **Remote roles.** Scope is always their geography plus remote roles they
   can take. If they are in the US, leave `remote_exclude_patterns` as
   shipped. If not, edit it to exclude the US and markets they cannot work in,
   and set `remote_require_patterns` to the words boards use for their market
   (a UK user: `uk`, `united kingdom`, `europe`, `emea`), because a bare
   "Remote" on most boards means US-only.
4. **Job titles.** Ask what titles they would apply to, what adjacent titles
   share words but are a different job, and what level they are at. Sets
   `[titles]` and `[extraction] role_noun` / `senior_scope`. Write the
   patterns from their words.
5. **Industries and company types** they want, weighted. Sets `[domains.*]`
   and `[stages.*]`; replace the shipped product-management examples
   entirely. Each definition is one concrete line, because the extraction
   prompt reads it.
6. **Pay.** The lowest annual base they would accept and its currency. Sets
   `comp_floor`, `currency`, `currency_symbol` and the two
   `comp_score_thresholds` above it.

Leave `[discovery]` as shipped for now; step 4 fills it.

Validate the file by importing the filter, which compiles every pattern:

```sh
PYTHONPATH=".cowork-deps:src" python3 -c "
from job_finder import filter as f
for loc in ['<a city they named>', 'Remote', 'Remote - EMEA', '<a city they did not>']:
    print(loc, f.stage1(title='<a title they named>', location=loc, workplace_type=None).reason)
"
```

Show them the four lines in plain words ("a role in X would be kept, a role
in Y would be dropped") and adjust until it matches what they meant.

## 4. The companies

They will not have 40 employer names in their head, so you build the list and
they prune it.

1. Ask for up to five employers they already admire or have applied to.
   Optional; "none" is fine.
2. Build 40 to 60 candidates yourself from what step 3 captured (industry,
   company size, region, remote stance), seeded by any names they gave. Use
   web search where this session has it; otherwise draw on what you know.
   Over-generate on purpose: only companies on Greenhouse, Lever or Ashby
   answer the probe below, and that is roughly half of any list.
3. Show the list as plain names, grouped by what they do, and ask them to
   strike any they would never want to work for. A yes or a no, never recall.
4. Write the survivors one per line to `candidates.txt` in `$ROOT` and probe
   which ones have a job board the engine can read:

```sh
PYTHONPATH=".cowork-deps:src" python3 scripts/discover_companies.py --file candidates.txt --json hits.json
PYTHONPATH=".cowork-deps:src" python3 -c "
from pathlib import Path
from job_finder import state
print(state.import_companies(Path('hits.json')), 'companies tracked')
"
```

A company with no public board is not dropped and the user is never asked
for a link. Find its careers page yourself: web search "<Name> careers" where
this session has search, otherwise try the company's own site:

```sh
for u in https://<domain>/careers https://<domain>/jobs https://<domain>/join-us https://<domain>/about/careers; do
  curl -fsSIL -o /dev/null -w "%{http_code} $u
" "$u" 2>/dev/null
done
```

Take the first page that answers 200 and plainly lists roles (fetch it and
look; a 200 on a redirect to the home page is not a careers page). Add it as
a manual check, which the digest surfaces every week for a hand look:

```sh
PYTHONPATH=".cowork-deps:src" python3 -c "
from job_finder import state
state.upsert_company({'name': '<Name>', 'ats_provider': 'manual', 'ats_slug': None,
                      'careers_url': '<url>', 'sector_tags': [], 'size_band': None})
"
```

Only a company whose careers page you genuinely cannot find is skipped, and
that goes in one line at the end ("I could not find a jobs page for X and
Y"), never as a question.

**The floor is 25 companies with a board the engine polls** (`greenhouse`,
`lever` or `ashby`; manual checks do not count). Three polled boards means an
empty digest for weeks and the user will not know why. Under 25, run another
round of suggestions and probe again, up to three rounds, without asking them
for names.

Then add the second source. Built In lists who is hiring by role in these
US metros: Austin, Boston, Chicago, Colorado, Los Angeles, New York, San
Francisco, Seattle (`https://www.builtin<metro>.com`, for example
`builtincolorado.com`, `builtinnyc.com`, `builtinsf.com`), plus
`https://builtin.com` nationally for remote roles. If one covers their
metro, or they are remote-first:

1. Fetch `<site>/jobs` and read the category links (`/jobs/marketing`,
   `/jobs/product-management`, `/jobs/design-ux`, `/jobs/sales`,
   `/jobs/dev-engineering`, `/jobs/data-analytics`, `/jobs/finance`,
   `/jobs/hr`, `/jobs/operations`, `/jobs/content`, ...). Pick the one that
   names their role.
2. Set `[discovery] builtin_sites = ["<site>"]` and `builtin_category =
   "<slug>"` in `config/pipeline.toml`.
3. Run discovery once now (about five minutes, zero tokens) and track every
   specific match:

```sh
PYTHONPATH=".cowork-deps:src" python3 -c "
import json
from job_finder import builtin_discovery, state
print(json.dumps(builtin_discovery.run(), indent=1))
print('tracked', builtin_discovery.track_specific())
"
```

From then on every weekly run repeats the scan, tracks every company whose
board lists the role by a specific title, and lists only the ambiguous ones
in the digest for a yes or no.

Tell them how many are tracked, split into boards the engine reads
automatically and sites it will list for a weekly look. Numbers only; the
mechanics above are yours.

Delete `candidates.txt` and `hits.json` when done.

## 5. Prove it works, for free

Run the collect stage once. It polls every tracked board and applies the
title and location filters; it spends nothing and needs no key:

```sh
PYTHONPATH=".cowork-deps:src" python3 -c "
import json
from job_finder import collect, db
db.init_db(db.DEFAULT_DB_PATH)
print(json.dumps(collect.run(db_path=db.DEFAULT_DB_PATH), indent=1))
"
PYTHONPATH=".cowork-deps:src" python3 -c "
from job_finder import db
with db.connect(db.DEFAULT_DB_PATH) as c:
    for verdict, n in c.execute('select hard_filter_verdict, count(*) from postings group by 1 order by 2 desc'):
        print(n, verdict)
"
```

Report in plain words: how many postings were read, how many passed the
filters, and the three biggest reasons the rest were dropped. If `keep` is
zero, the title or location patterns are wrong; go back to step 3 with them.
If it is in the hundreds for a short company list, the title patterns are too
loose.

Run `profile_check` again; it must now pass.

## 6. Schedule the weekly run

The weekly cycle is the `job-finder-weekly` skill: it polls the boards, reads
the new job descriptions here in Cowork, writes a digest, and prepares
applications for the top roles, leaving every form open and unsubmitted for
them to review. It needs no key and nothing installed. It is safe to call
every day: it only does the pipeline half when the last run is seven or more
days old.

Ask which weekday morning they usually have the Claude app open. Then, if a
scheduled-task tool is available in this session, create a task attached to
this folder, daily at that hour, with the prompt:

> Read `.claude/skills/job-finder-weekly/SKILL.md` in this folder and follow it.

If no such tool is available, tell them to say to Claude, in this folder:
"every weekday at 9am, read `.claude/skills/job-finder-weekly/SKILL.md` in
this folder and follow it", and that Cowork will set it up.

Say plainly: a task attached to a folder only runs while the Claude desktop
app is open on this computer. A missed day costs nothing; the next open day
catches up.

## 7. Hand off

Tell them, in this order and nothing more:

1. What is in the folder now and that none of it is shared anywhere.
2. How to run the weekly cycle by hand: open this folder in Cowork and say
   "run my weekly job search" (or `/job-finder-weekly`). The first run reads
   every job description the collect found, so it is the longest; later runs
   read only what is new.
3. How to come back: "set me up again" to change anything above; "add
   companies: Acme, Globex" to track named employers; "find me more
   companies" to run another round of suggestions. Say plainly that they
   never need to send a link: a company without a readable board gets its
   careers page found and listed for a weekly look.

## Hard rules

- Never commit, push, or create anything on GitHub. The folder is theirs and
  stays local.
- Never write personal data outside `$ROOT`.
- Never ask for, repeat, or store a password, key or card number.
- Never invent a fact for any profile file. If they did not say it, it is not
  written; ask instead.
- A write you did not read back did not happen.
