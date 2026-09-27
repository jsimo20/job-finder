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


PROVIDERS = ("greenhouse", "lever", "ashby")


def _probe_provider(client: httpx.Client, provider: str, slug: str) -> int | None:
    """Live posting count if `slug` has a board on `provider`, None if it has none.

    Network and parse failures raise: a failed request says nothing about
    whether the board exists, so it must not read as "no board".
    """
    if provider == "greenhouse":
        r = client.get(GREENHOUSE.format(slug=slug))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        jobs = r.json().get("jobs")
        return len(jobs) if isinstance(jobs, list) else None
    if provider == "lever":
        r = client.get(LEVER.format(slug=slug))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        body = r.json()
        return len(body) if isinstance(body, list) else None
    r = client.post(ASHBY_URL, json={
        "operationName": "ApiJobBoardWithTeams",
        "query": ASHBY_QUERY,
        "variables": {"organizationHostedJobsPageName": slug},
    })
    r.raise_for_status()
    board = (r.json().get("data") or {}).get("jobBoard")
    return len(board.get("jobPostings") or []) if board else None


def probe_name(client: httpx.Client, name: str, pause: float = 0.2) -> tuple[list[dict], list[str]]:
    """Every board `name` answers on, across all providers, plus any probe errors.

    All providers are checked because a company that moved ATS often leaves the
    old board up with a posting or two; stopping at the first answer reports the
    dead board. Within one provider the first slug variant that answers wins.
    """
    hits: list[dict] = []
    errors: list[str] = []
    for provider in PROVIDERS:
        for slug in slug_variants(name):
            try:
                count = _probe_provider(client, provider, slug)
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"{provider}:{slug} {type(e).__name__}")
                continue
            finally:
                time.sleep(pause)
            if count is not None:
                hits.append({"provider": provider, "slug": slug, "count": count})
                break
    hits.sort(key=lambda h: h["count"], reverse=True)
    return hits, errors


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
                              "_other_boards": hits[1:]})
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
