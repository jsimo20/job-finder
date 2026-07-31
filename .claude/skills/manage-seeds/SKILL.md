---
name: manage-seeds
description: Add, remove, swap, or validate companies in the job-finder seed list (seeds/companies.json). Use whenever the user wants to expand the universe, drop a company, fix a broken ATS slug, audit sector coverage, or probe a new careers page to figure out which ATS it uses.
---

# manage-seeds

The seed list at `seeds/companies.json` drives every daily run. It's the single source of truth for which companies the pipeline polls. This skill is the canonical way to edit it from Claude in place of the CLI.

## Schema (one row per company)

```json
{
  "name": "Klaviyo",
  "ats_provider": "greenhouse",
  "ats_slug": "klaviyo",
  "careers_url": "https://www.klaviyo.com/careers",
  "sector_tags": ["martech", "saas"],
  "size_band": "500+"
}
```

- `ats_provider`: one of `greenhouse`, `lever`, `ashby` — all three adapters are live. Workday/ICIMS/Taleo/SuccessFactors have no public API; companies on those cannot be seeded.
- `ats_slug`: the company's identifier inside the ATS URL. Example: `https://boards.greenhouse.io/klaviyo` → slug `klaviyo`. Often matches the company name but **not always** (Proof's Lever slug is `proof`, not `notarize`).
- `sector_tags`: free-form list, matches the taxonomy in `src/job_finder/taxonomy.py` where possible (e.g. `ai_agentic`, `developer_platform`, `silicon`, `space`, `quantum`).
- `size_band`: one of `1-50`, `51-200`, `201-500`, `500+`. Curated manually; recheck monthly.

## Discovering candidates for a new geography or industry

The seed list only grows from verified boards. To expand into a new metro or
market:

1. Build a candidate list of employer names from any regional source (a
   builtin.com regional site, a VC portfolio page, a local tech council's
   member list).
2. Probe them: `python scripts/discover_seeds.py --file candidates.txt --json hits.json`
   checks every name against the Greenhouse, Lever, and Ashby public
   endpoints (several slug guesses each) and reports live posting counts.
3. Curate the hits — verify each careers page (slug collisions exist), fill
   `sector_tags` and `size_band` — then merge into `seeds/companies.json`.

Expect large legacy employers (insurers, banks, hospital systems) to come
back "no board found": they run Workday/ICIMS/Taleo, which have no public
API. That is a hard limit, not a probing failure.

## Operations

### Add a company

1. Find the company's careers page.
2. Identify the ATS by inspecting their job board URL:
   - `boards.greenhouse.io/<slug>` or `job-boards.greenhouse.io/<slug>` → Greenhouse
   - `jobs.lever.co/<slug>` → Lever
   - `jobs.ashbyhq.com/<slug>` → Ashby
   - `<company>.wd*.myworkdayjobs.com` → Workday (skip for now)
3. **Probe the public endpoint before adding** to avoid 404s in the next run:
   - Greenhouse: `https://api.greenhouse.io/v1/boards/<slug>/jobs`
   - Lever: `https://api.lever.co/v0/postings/<slug>?mode=json`
   - Ashby: `scripts/discover_seeds.py` probes it (GraphQL POST, no plain GET)
   ```powershell
   try { (Invoke-WebRequest "https://api.greenhouse.io/v1/boards/<slug>/jobs" -UseBasicParsing).StatusCode } catch { $_.Exception.Response.StatusCode.value__ }
   ```
   Only commit if you get a 200.
4. Append a new object to `seeds/companies.json` with all six fields populated. Keep the JSON well-formed (trailing comma rules).
5. Tell the user: "Added <name>. Next `cli collect` run will pick it up." Don't auto-run the pipeline — it costs Claude tokens.

### Remove a company

Just delete the row. No DB cleanup needed — closed-role inference will mark its postings as closed on the next run because they'll be absent from the feed (which is now empty for that company).

### Swap / fix a broken slug

User reports a company returns 404 or 0 jobs:
1. Re-probe candidate slugs. Common patterns to try when the obvious one fails: company name plus `inc`, `careers`, `hq`, no-spaces, no-hyphens. Also try the other ATS (Greenhouse ↔ Lever).
2. If you find the right slug, edit the row in place.
3. If you can't find any working slug, ask the user whether to drop the row or move it to a "needs-investigation" comment in `session-context.md` for later.

### Audit sector coverage

Run a quick scan over `seeds/companies.json` and report counts per `sector_tag` and per `size_band`. This is useful before bulk-expanding to confirm the seed isn't lopsided. The taxonomy weights in [src/job_finder/taxonomy.py](../../src/job_finder/taxonomy.py) are the reference for which sectors carry the most score weight (`ai_agentic` = 5, `developer_platform` / `consumer_at_scale` = 4, etc.). Suggest fills for under-represented high-weight sectors.

### Validate the entire seed in one pass

Loop through every row, probe its endpoint, report which return 200 vs which 4xx. This is the same first-pass we did when the pilot launched. Useful periodically to catch companies that switched ATSs.

## What this skill should NOT do

- **Don't run `cli collect` or `cli run` automatically.** Those make Claude API calls (extract step costs tokens). Always let the user trigger pipeline runs.
- **Don't edit `data/jobs.db` directly.** The DB is regenerated by the pipeline; seed-list edits propagate naturally on the next `collect`.
- **Don't add a Workable/Workday/ICIMS row** — no adapter, no public API. The collector silently skips unknown providers with an error in stats.
- **Don't commit on the user's behalf** unless they explicitly say "commit and push". This is a private repo but the global rule still applies: surface the diff, draft a plain imperative commit message (no type/scope prefixes), ask.

## Reference

- Seed file: [seeds/companies.json](../../seeds/companies.json)
- Taxonomy + weights: [src/job_finder/taxonomy.py](../../src/job_finder/taxonomy.py)
- Adapters (provider list lives here): [src/job_finder/adapters/__init__.py](../../src/job_finder/adapters/__init__.py)
- Session log of which companies were dropped from the original seed and why: [session-context.md](../../session-context.md)
