---
name: job-finder-setup
description: The setup procedure for job-finder, from the profile interview onward. Read by the plugin's setup launcher once the engine is in the folder, and directly when a user wants to change their profile, resume, voice, titles, places, pay or schedule. Builds the profile, the search settings and the company list through a plain-language interview, proves the first collect, and schedules the weekly run.
---

# job-finder-setup

The user may never have used a terminal or an AI tool. They see your messages,
not your commands. Everything technical is yours; everything personal is
theirs to tell you.

- `$ROOT` is the connected folder, the repo root. The launcher has already
  checked the network and installed the engine there.
- **Python:** `PYTHONPATH=".cowork-deps:src" python3` from `$ROOT` on Cowork;
  `.venv/Scripts/python.exe` with no prefix in Claude Code on Windows.
- Every step skips what already exists, so a second run resumes. A user
  changing one thing starts at the step that covers it.

## How to talk

- Plain words: "folder", "copy", "pattern", "settings file". Never "repo",
  "clone", "regex", "TOML", "env var".
- One question at a time; wait for the answer.
- One line before an action, one line after. Never paste command output.
- Say once, near the start, that nothing they tell you leaves the folder.
- Never ask for a password, an API key or a payment detail.

## 1. The form-filling browser

Look through your own tool list for any tool whose name contains `playwright`.

- **Present:** say nothing; carry on.
- **Absent:** Node.js is missing on their computer. Send this, then stop and
  wait:

  > One small install first, so I can fill application forms for you later.
  > Open https://nodejs.org in your browser and click the big green button
  > marked **LTS** to download it. Open the downloaded file and click Next
  > until it finishes; the defaults are fine. Then quit the Claude app
  > completely and open it again, come back to this folder, and tell me
  > "set me up" again. I will pick up where we left off.

  Still absent on the second run: say form filling will not work on this
  computer yet and everything else will, and carry on.

Never ask what Node is, whether they have it, or to run anything.

## 2. Their profile

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.profile_init
```

It writes the starting files into `profile/` and never overwrites one that
exists. Replace every example value with their real answers, in the order
below. **Read back every file you write.**

### 2a. Resume, the ground truth

Ask them to drop their current resume into the folder (PDF, Word or text).
Draft `profile/resume_master.md` from it: every role, date, bullet and skill
as written, nothing added, nothing rounded. Show the draft, ask what is wrong
or missing, and write it only after they confirm. Tell them in one sentence
that every later claim is checked against this file.

Then fill only the `RESUME_DATA` block of `profile/generate_resume.py` from the
same content.

### 2b. Identity and form answers

`profile/profile.toml`:

- `[identity]`: name, email, phone, LinkedIn, GitHub if any, city, and
  `title_subtitle` (ask: "how would you describe yourself in one line at the
  top of a cover letter?").
- `[answers]`: ask "Are you legally allowed to work in your country without a
  visa sponsor?" and "Would you need a company to sponsor a visa now or
  later?" Set `work_authorized`, `requires_sponsorship` and `country`.
- `[eeo]`: ask whether they want the voluntary questions (gender, ethnicity,
  veteran status, disability) answered automatically. If no, leave every
  value `""`.

`profile/standard_answers.md`: the contact block, the work-authorization
lines, and their answers to "how did you hear about us", "willing to work
hybrid or onsite" and "earliest start date". Ask for each.

### 2c. Their voice

Ask them to write a few unpolished paragraphs in chat: what they did, what
they want next, what they are proud of. Save them to
`profile/personal_statement.md` as written, fixing only obvious typos. Leave
`profile/writing-style.md` as shipped.

### 2d. What a good role looks like

Ask what kind of companies and work they want and what would make them say
no. Write `profile/fit_profile.md` in its four sections (strong positive, mild
positive, mild negative, strong negative).

### 2e. Claims they can defend

Seed `profile/claims_ground_truth.md` from the confirmed resume: every metric
with its exact figure, every skill under the source-pool headings. Ask about
any figure that looks rounded ("exactly 40%, or about 40%?") and record the
answer.

## 3. Their search

```sh
cp config/pipeline.example.toml config/pipeline.toml
```

Every value marked `REPLACE` is a placeholder that matches nothing. **Write
each one from their answers; leave none, and never fill one from the example
or from what you would guess.** Ask, in this order:

1. **Where they live** and the country they can work from: `[location]
   country` and the commute notes.
2. **Cities or regions** they would take an office job in, and roughly how far
   each is from home: `in_scope_patterns` and the three tiers, written from
   the place names they give, with the state or county abbreviations boards
   print.
3. **Remote roles.** In the US, leave `remote_exclude_patterns` as shipped.
   Elsewhere, exclude the US and markets they cannot work in, and set
   `remote_require_patterns` to the words boards use for their market (UK:
   `uk`, `united kingdom`, `europe`, `emea`).
4. **Job titles and level.** The titles they would apply to, adjacent titles
   that are a different job, and their level: every `[titles]` pattern,
   `[extraction] role_noun` and `senior_scope`, and `yoe_main_queue_max` /
   `untitled_min_yoe` from their years of experience.
5. **Industries and kinds of company**, each weighted 1 to 5: one
   `[domains.<key>]` table per industry and one `[stages.<key>]` per company
   type, replacing `replace_me`. Each definition is one concrete line.
6. **Pay.** Their lowest acceptable annual base and currency: `comp_floor`,
   `currency`, `currency_symbol`, and two `comp_score_thresholds` above the
   floor.

Leave `[discovery]` for step 4. Then check the patterns:

```sh
PYTHONPATH=".cowork-deps:src" python3 -c "
from job_finder import filter as f
for loc in ['<a city they named>', 'Remote', 'Remote - EMEA', '<a city they did not>']:
    print(loc, f.stage1(title='<a title they named>', location=loc, workplace_type=None).reason)
"
```

Tell them in plain words which roles would be kept and which dropped, and
adjust until it matches what they meant.

## 4. The companies

You build the list; they prune it.

1. Ask for up to five employers they admire or have applied to ("none" is
   fine).
2. Build 40 to 60 candidates from step 3 (industry, company size, region,
   remote stance), seeded by their names. Use web search where available.
   About half of any list has a board the engine can read, so over-generate.
3. Show the names grouped by what the companies do; ask them to strike any
   they would never work for.
4. Probe the survivors:

```sh
PYTHONPATH=".cowork-deps:src" python3 scripts/discover_companies.py --file candidates.txt --json hits.json
PYTHONPATH=".cowork-deps:src" python3 -c "
from pathlib import Path
from job_finder import state
print(state.import_companies(Path('hits.json')), 'companies tracked')
"
```

A company with no board is kept as a manual check. Find its careers page
yourself (web search "<Name> careers", or try `/careers`, `/jobs`,
`/join-us`, `/about/careers` on its site; open it with Playwright if a plain
fetch shows nothing). Take the first page that plainly lists roles; a
redirect to the home page does not count. Never ask them for a link.

```sh
PYTHONPATH=".cowork-deps:src" python3 -c "
from job_finder import state
state.upsert_company({'name': '<Name>', 'ats_provider': 'manual', 'ats_slug': None,
                      'careers_url': '<url>', 'sector_tags': [], 'size_band': None})
"
```

List any company whose careers page you cannot find in one line at the end.

**At least 25 companies must have a readable board** (`greenhouse`, `lever` or
`ashby`; manual checks do not count). Under 25, suggest and probe another
round, up to three, without asking them for names.

Then Built In, if a site covers their metro or they want remote roles: Austin,
Boston, Chicago, Colorado, Los Angeles, New York, San Francisco, Seattle
(`https://www.builtin<metro>.com`), or `https://builtin.com` for remote.

1. Fetch `<site>/jobs` and pick the category that names their role
   (`marketing`, `product-management`, `design-ux`, `sales`,
   `dev-engineering`, `data-analytics`, `finance`, `hr`, `operations`,
   `content`, ...). If the site does not answer, skip Built In.
2. Set `[discovery] builtin_sites = ["<site>"]` and `builtin_category =
   "<slug>"`.
3. Run it once (about five minutes, zero tokens):

```sh
PYTHONPATH=".cowork-deps:src" python3 -c "
import json
from job_finder import builtin_discovery
print(json.dumps(builtin_discovery.run(), indent=1))
print('tracked', builtin_discovery.track_specific())
"
```

Tell them how many companies are read automatically and how many are manual
checks. Delete `candidates.txt` and `hits.json`.

## 5. Prove it works, for free

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
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.profile_check
```

Tell them how many postings were read, how many passed, and the three biggest
reasons the rest were dropped. Zero kept means the title or location patterns
are wrong; hundreds kept from a short list means the titles are too loose.
Either way, go back to step 3. `profile_check` must exit 0 before you go on.

## 6. Schedule the weekly run

Ask which weekday morning they usually have the Claude app open. Then create
the scheduled task with:

| Field | Value |
|---|---|
| Name | Job finder weekly run |
| Prompt | `Read .claude/skills/job-finder-weekly/SKILL.md in this folder and follow it.` |
| Schedule | Weekly on their day and hour, in their time zone |
| Folders | This folder's path on their computer, as Cowork shows the connected folder |
| Requires local device | On |

**The folder is required.** A task without it runs in the cloud and cannot see
the engine, so nothing runs. A folder can only be set when a task is created:
to fix a task without one, delete it and create it again. After creating it,
list the scheduled tasks and confirm the folder shows on this one.

With no scheduled-task tool, tell them to say, in this folder: "every Monday
at 9am, read `.claude/skills/job-finder-weekly/SKILL.md` in this folder and
follow it, with this folder attached", with their day and hour.

Tell them it only runs while the Claude app is open, that they can say "run my
weekly job search" any time instead, and that each run updates the tool first.

## 7. Hand off

Tell them, in this order and nothing more:

1. What is in the folder now, and that none of it is shared anywhere.
2. That when they ask for the same change twice, or tell you a rule directly,
   Claude writes it to their own rules file and follows it from then on.
3. To run the search by hand: open this folder in a chat and say "run my
   weekly job search". The first run is the longest.
4. To come back: "change my settings", "add companies: Acme, Globex", "find me
   more companies".
5. Large employers usually post on their own careers sites, which the search
   cannot read. For one they care about, "add companies: <name>" lists its
   careers page in the digest under **Manual check**; when a role there
   interests them, they paste the link or description into a chat and ask for
   help applying.
6. When an application becomes an interview: "prep me for my interview with
   <company>" builds a prep sheet and runs a mock interview.

## Hard rules

- Never commit, push or create anything on GitHub.
- Never write personal data outside `$ROOT`.
- Never ask for, repeat or store a password, key or card number.
- Never write a fact they did not tell you; ask instead.
- A write you did not read back did not happen.
