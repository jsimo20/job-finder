"""Probe candidate companies for a public ATS board and emit company rows.

The durable answer to "how do I expand the tracked-company list to a new geography or
industry": build a candidate list of employer names (from a regional tech
site, a VC portfolio page, a chamber-of-commerce list — anywhere), feed it
in, and this verifies which ones expose a Greenhouse, Lever, or Ashby board
the pipeline can actually poll. Zero LLM tokens; a few HTTP calls per name
against the same public endpoints the adapters use.

Companies on Workday/ICIMS/Taleo/SuccessFactors have no public API and will
simply report "no board found" — that is the answer, not a bug.

Usage:
    python scripts/discover_companies.py --names "Company A" "Company B" ...
    python scripts/discover_companies.py --file candidates.txt          # one name per line
    python scripts/discover_companies.py --file candidates.txt --json out.json

Verify each hit's careers page before adding it to data/companies.json
(slug collisions exist: an acquirer's board can answer for a dead brand).
The manage-companies skill adds curated rows from this output.
"""
from __future__ import annotations

import argparse
import json
import sys


import httpx

from job_finder.ats_probe import probe_name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--names", nargs="*", default=[])
    ap.add_argument("--file", help="candidate names, one per line, # comments ok")
    ap.add_argument("--json", help="write matched company rows to this path")
    args = ap.parse_args()

    names = list(args.names)
    if args.file:
        for line in open(args.file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(line)
    if not names:
        ap.error("no candidate names given")

    found, missed, failed = [], [], []
    with httpx.Client(timeout=30, follow_redirects=True,
                      headers={"User-Agent": "job-finder-seed-probe"}) as client:
        for name in names:
            hits, errors = probe_name(client, name)
            if hits:
                best = hits[0]
                print(f"FOUND  {name:32s} {best['provider']:10s} slug={best['slug']:24s} "
                      f"{best['count']} live postings")
                for other in hits[1:]:
                    print(f"       {'':32s} {other['provider']:10s} slug={other['slug']:24s} "
                          f"{other['count']} live postings  (second board: verify which is current)")
                found.append({"name": name, "ats_provider": best["provider"],
                              "ats_slug": best["slug"], "careers_url": "", "sector_tags": [],
                              "size_band": "", "_live_postings": best["count"],
                              "_other_boards": [{k: h[k] for k in ("provider", "slug", "count")} for h in hits[1:]]})
            elif errors:
                failed.append(name)
                print(f"ERROR  {name:32s} {'; '.join(errors[:3])}")
            else:
                missed.append(name)
                print(f"none   {name}")

    print(f"\n{len(found)} found, {len(missed)} without a public board "
          f"(likely Workday/ICIMS/Taleo — no API), {len(failed)} errored (re-run those).")
    if args.json and found:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(found, f, indent=2)
        print(f"wrote {args.json} — curate sector_tags/size_band and VERIFY each "
              "careers page before merging into data/companies.json")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
