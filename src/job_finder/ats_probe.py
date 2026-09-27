"""Find which public ATS boards answer for a company name.

Zero LLM tokens: a few GETs per name against the same public listing endpoints
the adapters use. Used by scripts/discover_companies.py and by Built In
discovery, which also needs each board's posting titles to confirm that a slug
belongs to the company it was guessed from.
"""
from __future__ import annotations

import re
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
PROVIDERS = ("greenhouse", "lever", "ashby")


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


def board_titles(client: httpx.Client, provider: str, slug: str) -> list[str] | None:
    """Posting titles on `slug`'s board at `provider`, or None if it has no board.

    Network and parse failures raise: a failed request says nothing about
    whether the board exists, so it must not read as "no board".
    """
    if provider == "greenhouse":
        r = client.get(GREENHOUSE.format(slug=slug))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        jobs = r.json().get("jobs")
        return [j.get("title") or "" for j in jobs] if isinstance(jobs, list) else None
    if provider == "lever":
        r = client.get(LEVER.format(slug=slug))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        body = r.json()
        return [p.get("text") or "" for p in body] if isinstance(body, list) else None
    r = client.post(ASHBY_URL, json={
        "operationName": "ApiJobBoardWithTeams",
        "query": ASHBY_QUERY,
        "variables": {"organizationHostedJobsPageName": slug},
    })
    r.raise_for_status()
    board = (r.json().get("data") or {}).get("jobBoard")
    return [p.get("title") or "" for p in board.get("jobPostings") or []] if board else None


def probe_name(client: httpx.Client, name: str, pause: float = 0.2) -> tuple[list[dict], list[str]]:
    """Every board `name` answers on, across all providers, plus any probe errors.

    Each hit is {provider, slug, count, titles}, busiest board first. All
    providers are checked because a company that moved ATS often leaves the old
    board up with a posting or two; stopping at the first answer reports the
    dead board. Within one provider the first slug variant that answers wins.
    """
    hits: list[dict] = []
    errors: list[str] = []
    for provider in PROVIDERS:
        for slug in slug_variants(name):
            try:
                titles = board_titles(client, provider, slug)
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"{provider}:{slug} {type(e).__name__}")
                continue
            finally:
                time.sleep(pause)
            if titles is not None:
                hits.append({"provider": provider, "slug": slug,
                             "count": len(titles), "titles": titles})
                break
    hits.sort(key=lambda h: h["count"], reverse=True)
    return hits, errors
