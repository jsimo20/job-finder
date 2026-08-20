---
name: manage-companies
description: Add, remove, swap, or validate companies in the tracked-company list (data/state.db). Use whenever the user wants to expand the universe, drop a company, fix a broken ATS slug, audit sector coverage, or probe a new careers page to figure out which ATS it uses.
---

# manage-companies

The tracked-company list lives in `data/state.db` (gitignored, local-only)
and drives every pipeline run. Manage it through the CLI — never edit the
database file directly.

## The row shape

name, ats_provider (`greenhouse` | `lever` | `ashby` | `workday` | `manual`),
ats_slug (the company's identifier inside the ATS URL; often but not always
the lowercase name), careers_url, sector_tags (match
`config/pipeline.toml [domains]` keys where possible), size_band (`1-50`,
`51-200`, `201-500`, `500+`).

Workday slugs encode the board coordinates as `tenant/wdN/site` — read all
three from the careers URL, e.g.
`examplecorp.wd1.myworkdayjobs.com/External` → `examplecorp/wd1/External`.
Probe with a POST to
`https://<tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs`
(body `{"appliedFacets":{},"limit":1,"offset":0,"searchText":""}`); a 200
with a `total` confirms the coordinates, a 422 means the tenant exists but
the site name is wrong.

ICIMS/Taleo/SuccessFactors/Phenom/Eightfold have no adapter; track those
companies with `--provider manual --careers-url <url>` (no slug). They are
skipped by collect and surface in the digest's **Manual check** section for
a weekly hand check.

## Operations

### Add a company

1. **Probe before adding** so a bad slug doesn't 404 the next run:
   `python scripts/discover_companies.py --names "Company Name"` tries slug
   variants against all three ATS endpoints and reports live posting counts.
2. Verify the hit is really that company (slug collisions exist — check the
   posting titles/locations, not just the 200).
3. `job-finder companies add --name "..." --provider greenhouse --slug "..."
   [--careers-url ...] [--tags tag1,tag2] [--size-band 201-500]`
4. Don't auto-run the pipeline — it costs API tokens. The next scheduled run
   picks the company up.

### Remove / fix a company

- `job-finder companies remove --name "..."` — closed-role inference marks
  its postings closed on the next run.
- Broken slug: re-probe variants (name+`inc`/`hq`, no-spaces, the other
  ATSes), then `companies add` with the same name to upsert in place.

### Bulk expansion (new geography or industry)

1. Build a candidate list of employer names from any regional source.
2. `python scripts/discover_companies.py --file candidates.txt --json hits.json`
3. Curate hits (verify boards, fill tags/size), then
   `job-finder companies import hits.json`.

### Audit / validate

- `job-finder companies list` for the current universe; count tags per
  sector against the weights in `config/pipeline.toml` and suggest fills for
  under-represented high-weight sectors.
- Full validation: `job-finder companies export /tmp/list.json`, then probe
  every row with discover_companies and report 200s vs 4xxs — catches
  companies that switched ATSes.

### Quiet down a noisy board

A company with hundreds of open reqs can dominate the digest without ever
producing a fresh match. Rather than dropping it, narrow its window:

`job-finder companies add --name "..." --provider greenhouse --slug "..." --max-age-days 14`

The digest then shows only that company's postings made within N days; every
other company stays on the global `STALE_DAYS`. Re-running `companies add`
without the flag clears the override. Postings with no post date are hidden
while an override is active, so verify the ATS supplies dates before relying
on it (Greenhouse `first_published`, Ashby `publishedDate`, Lever `createdAt`,
Workday `startDate`).

### No-auto-apply blocklist

Companies that stay in the digest but must never be auto-applied to (e.g.
where the user has an inside contact): `job-finder no-auto list|add|remove`.
The /job-apply command hard-blocks these.

## What this skill should NOT do

- **Don't run `cli collect` or `cli run` automatically** — API tokens.
- **Don't edit data/state.db or data/jobs.db directly** — CLI only.
- **Don't commit anything under data/** — it is gitignored personal state.
