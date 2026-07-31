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
import re
import sys
import time

import httpx

GREENHOUSE = "https://api.greenhouse.io/v1/boards/{slug}/jobs"
LEVER = "https://api.lever.co/v0/postings/{slug}?mode=json"
ASHBY_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"
ASHBY_QUERY = (
    "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {"
    " jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {"
    " jobPostings { id title } } }"
)


def slug_variants(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    joined = base.replace(" ", "")
    hyphenated = re.sub(r"\s+", "-", base)
    variants = [joined, hyphenated]
    # drop common suffixes: "Acme Health Inc" -> "acmehealth", "acme"
    words = base.split()
    if len(words) > 1:
        variants.append("".join(words[:-1]))
        variants.append(words[0])
    seen: list[str] = []
    for v in variants:
        if v and len(v) >= 3 and v not in seen:
            seen.append(v)
    return seen


def probe(client: httpx.Client, slug: str) -> tuple[str, int] | None:
    """(provider, live_posting_count) if slug answers on any ATS, else None."""
    try:
        r = client.get(GREENHOUSE.format(slug=slug))
        if r.status_code == 200 and isinstance(r.json().get("jobs"), list):
            return "greenhouse", len(r.json()["jobs"])
    except Exception:
        pass
    try:
        r = client.get(LEVER.format(slug=slug))
        if r.status_code == 200 and isinstance(r.json(), list):
            return "lever", len(r.json())
    except Exception:
        pass
    try:
        r = client.post(ASHBY_URL, json={
            "operationName": "ApiJobBoardWithTeams",
            "query": ASHBY_QUERY,
            "variables": {"organizationHostedJobsPageName": slug},
        })
        board = r.status_code == 200 and (r.json().get("data") or {}).get("jobBoard")
        if board:
            return "ashby", len(board.get("jobPostings") or [])
    except Exception:
        pass
    return None


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

    found, missed = [], []
    with httpx.Client(timeout=10, follow_redirects=True,
                      headers={"User-Agent": "job-finder-seed-probe"}) as client:
        for name in names:
            hit = None
            for slug in slug_variants(name):
                hit = probe(client, slug)
                if hit:
                    provider, count = hit
                    print(f"FOUND  {name:32s} {provider:10s} slug={slug:24s} {count} live postings")
                    found.append({"name": name, "ats_provider": provider, "ats_slug": slug,
                                  "careers_url": "", "sector_tags": [], "size_band": "",
                                  "_live_postings": count})
                    break
                time.sleep(0.2)
            if not hit:
                missed.append(name)
                print(f"none   {name}")

    print(f"\n{len(found)} found, {len(missed)} without a public board "
          "(likely Workday/ICIMS/Taleo — no API).")
    if args.json and found:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(found, f, indent=2)
        print(f"wrote {args.json} — curate sector_tags/size_band and VERIFY each "
              "careers page before merging into data/companies.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
