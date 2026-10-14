---
name: manage-companies
description: Add, remove, list, or find more companies in the tracked-company list (data/state.db). Use whenever the user wants to add an employer, drop one, see what is tracked, get more suggestions like the ones they have, fix a broken board, or quiet a noisy one. Works the same on Cowork and in Claude Code.
---

# manage-companies

The tracked-company list lives in `data/state.db` (gitignored, local-only)
and drives every weekly run. Change it only through the `state` functions
below, never by editing the database file.

**`$PY` below means `PYTHONPATH=".cowork-deps:src" python3` on Cowork and
`.venv/Scripts/python.exe` on Windows, run from the repo root.** The
`job-finder` console script does not exist on Cowork, so nothing here uses it.

Talk to the user in plain words: "company", "job board", "careers page".
Report results as names and counts, never as command output.

## The row shape

`name`, `ats_provider` (`greenhouse` | `lever` | `ashby` | `workday` |
`manual`), `ats_slug` (the company's identifier on that board; `None` for
`manual`), `careers_url`, `sector_tags` (keys of `config/pipeline.toml
[domains]` where they fit, else `[]`), `size_band` (`1-50`, `51-200`,
`201-500`, `500+`, or `None`), and optionally `max_age_days`.

A `manual` row is a careers-page link with no readable board. The weekly run
never searches it; the digest lists it under **Manual check** for a look by
hand. Say so whenever you add one.

## Operations

### List

```sh
$PY -c "
from job_finder import state
rows = state.list_companies()
for c in rows:
    print(c['ats_provider'], '|', c['name'], '|', c['careers_url'] or '')
print(len(rows), 'tracked')
"
```

Tell them how many are read automatically (any provider but `manual`) and how
many are manual checks. List names only if they asked to see them.

### Add named companies

1. Probe which job boards answer for each name:

   ```sh
   $PY scripts/discover_companies.py --names "Name One" "Name Two" --json hits.json
   ```

2. Check each hit is really that company: read the posting titles and
   locations it printed, not just the match. Slugs collide (`relay`,
   `general`). Drop a wrong hit from `hits.json`.
3. Track the verified hits:

   ```sh
   $PY -c "
   from pathlib import Path
   from job_finder import state
   print(state.import_companies(Path('hits.json')), 'tracked')
   "
   ```

4. A name with no board is not dropped and the user is never asked for a
   link. Find its careers page yourself: web search "<Name> careers" where
   the session has search, otherwise try `https://<domain>/careers`, `/jobs`,
   `/join-us`, `/about/careers` and take the first page that answers 200 and
   plainly lists roles (fetch it and look; a redirect to the home page is not
   a careers page). A page that comes back empty usually needs JavaScript:
   open it with the Playwright tools (any tool whose name contains
   `playwright`) before deciding it lists nothing. Track it as manual:

   ```sh
   $PY -c "
   from job_finder import state
   state.upsert_company({'name': '<Name>', 'ats_provider': 'manual', 'ats_slug': None,
                         'careers_url': '<url>', 'sector_tags': [], 'size_band': None})
   "
   ```

5. Delete `hits.json`. Report: which names are now read automatically, which
   are manual checks, and any you could not find a jobs page for.

Workday boards encode their coordinates as `tenant/wdN/site`, read from the
careers URL (`examplecorp.wd1.myworkdayjobs.com/External` →
`examplecorp/wd1/External`). Only add one when the user asks for it by name;
Workday polling is unreliable and is not offered by default.

### Find more like these

Build 15 to 25 candidates from what they already track, the industries and
company types in `config/pipeline.toml [domains]` and `[stages]`, and their
region. Leave out every name already tracked. Show the list grouped by what
the companies do, ask them to strike any they would never work for, then run
**Add named companies** on the rest.

### Remove

```sh
$PY -c "
from job_finder import state
print(state.remove_company('<Name>'))
"
```

`True` means it was tracked and is gone; its postings close on the next run.

### Fix a broken board

A company whose board stopped answering has usually moved boards. Re-probe
with **Add named companies** step 1, also trying the name with `inc`, `hq`,
or no spaces. `upsert_company` with the same name replaces the row in place.

### Quiet a noisy board

A company with hundreds of open roles can crowd the digest. Narrow its window
instead of dropping it: upsert the same row with `'max_age_days': 14`. The
digest then shows only that company's postings from the last N days, and
**hides any posting with no date**, so check the board supplies dates first.
Upserting without the key clears it.

### Companies found by discovery

The weekly run proposes untracked companies from Built In in the digest's
**New companies to review**. To track one:

```sh
$PY -c "
from job_finder import builtin_discovery
print(builtin_discovery.promote('<Name>'))
"
```

To stop one being proposed again:
`state.set_discovered_status('<Name>', 'dismissed')`.

### Never auto-apply

Companies that stay in the digest but must never get an automatic
application (an inside contact, a pause): `state.add_no_auto('<Name>',
reason='<why>')`, `state.remove_no_auto('<Name>')`, `state.list_no_auto()`.
The apply procedures refuse these.

## Never

- Run a collect or a weekly run to test a change; the next scheduled run
  picks it up.
- Edit `data/state.db` or `data/jobs.db` directly.
- Commit anything under `data/`.
