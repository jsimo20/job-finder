"""Find companies hiring the target role on Built In that the tracked list misses.

The tracked list is a fixed seed, and companies that post one or two roles a
year never make it in. Built In's regional sites list every company posting in
a category, so a weekly pass over one category page is a cheap way to see who
is hiring that the pipeline is not watching.

This proposes companies; it never adds them. A candidate is recorded as
`pending` only when one of its ATS boards lists the same role Built In showed,
because slug guessing collides ("relay", "general") and a title match is what
proves the board belongs to the company. The digest lists pending candidates
for a yes/no, and `job-finder discover add|dismiss` records the answer.

Zero LLM tokens. Built In's robots.txt allows its /jobs category pages; each
page is one request, paced a second apart.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from . import filter as filters
from . import state
from .ats_probe import probe_name
from .settings import pipeline_config

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; job-finder/1.0)"

_SUFFIX_RE = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|company|the|group|holdings|technologies|"
    r"technology|labs|hq)\b")


@dataclass
class Listing:
    company: str
    title: str
    url: str
    age_days: int | None
    source: str


def settings() -> dict:
    """[discovery] from the pipeline config; an absent table disables discovery."""
    cfg = pipeline_config().get("discovery", {})
    return {
        "sites": list(cfg.get("builtin_sites", [])),
        "category": cfg.get("builtin_category", "product-management"),
        "max_age_days": int(cfg.get("max_age_days", 7)),
        "max_pages": int(cfg.get("max_pages", 60)),
    }


def normalize_company(name: str) -> str:
    n = name.lower().replace("&", " and ")
    n = re.sub(r"\(.*?\)", " ", n)
    n = _SUFFIX_RE.sub(" ", n)
    return re.sub(r"[^a-z0-9]", "", n)


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def parse_age_days(text: str) -> int | None:
    """Days since posting from Built In's age label ("3 Days Ago", "Reposted Yesterday")."""
    t = text.lower().replace("reposted", "").strip()
    if re.search(r"\b(minute|hour)s?\b", t):
        return 0
    if "yesterday" in t:
        return 1
    m = re.search(r"\b(\d+|one|a)\s+(day|week|month)s?\b", t)
    if not m:
        return None
    n = 1 if m.group(1) in ("one", "a") else int(m.group(1))
    return n * {"day": 1, "week": 7, "month": 30}[m.group(2)]


def parse_listing_page(html: str, site: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select('[data-id="job-card"]'):
        title = card.select_one('[data-id="job-card-title"]')
        company = card.select_one('[data-id="company-title"]')
        if not title or not company:
            continue
        age = card.select_one("span.bg-gray-01")
        out.append(Listing(
            company=company.get_text(" ", strip=True),
            title=title.get_text(" ", strip=True),
            url=site.rstrip("/") + title.get("href", ""),
            age_days=parse_age_days(age.get_text(" ", strip=True)) if age else None,
            source=site,
        ))
    return out


# Built In's own posted-date filter; the page order is not newest-first, so the
# window has to be applied server-side rather than by stopping at an old card.
_DAYS_FILTER = (1, 3, 7, 30)


def fetch_listings(client: httpx.Client, site: str, category: str, max_age_days: int,
                   max_pages: int, pause: float = 1.0) -> list[Listing]:
    """Listings from one site's category posted within `max_age_days`, read until
    an empty page. HTTP failures raise to the caller."""
    days = next((d for d in _DAYS_FILTER if d >= max_age_days), _DAYS_FILTER[-1])
    found: list[Listing] = []
    for page in range(1, max_pages + 1):
        r = client.get(f"{site.rstrip('/')}/jobs/{category}",
                       params={"daysSinceUpdated": days, "page": page})
        r.raise_for_status()
        cards = parse_listing_page(r.text, site)
        if not cards:
            break
        found.extend(c for c in cards if c.age_days is None or c.age_days <= max_age_days)
        time.sleep(pause)
    return found


def title_passes(title: str) -> bool:
    """The pipeline's own Stage 1 title rules. A regional Built In site only lists
    roles in its metro or remote, so location is treated as in scope."""
    return filters.stage1(title=title, location=None, workplace_type="remote").keep


def candidates(listings: list[Listing], known: set[str]) -> dict[str, list[Listing]]:
    """Untracked companies with at least one target-role listing, keyed by display name."""
    out: dict[str, list[Listing]] = {}
    for item in listings:
        key = normalize_company(item.company)
        if not key or key in known or not title_passes(item.title):
            continue
        out.setdefault(item.company, []).append(item)
    return out


def is_generic_title(title: str) -> bool:
    """True for a title that is only a level and the role noun ("Senior Product
    Manager"): many unrelated boards list it, so matching it proves little."""
    core = filters.SENIORITY_KEEP_RE.sub(" ", title)
    role_noun = pipeline_config().get("extraction", {}).get("role_noun", "product manager")
    return _normalize_title(core) == _normalize_title(role_noun)


def board_match(board_titles: list[str], role_titles: list[str]) -> str | None:
    """'specific' or 'generic' when the board lists one of the roles Built In
    showed for the company, preferring a specific title; None when it lists none."""
    board = {_normalize_title(t) for t in board_titles}
    strength = None
    for role in role_titles:
        r = _normalize_title(role)
        if len(r) < 8:
            continue
        if r in board or any(r in b or b in r for b in board if len(b) >= 8):
            if not is_generic_title(role):
                return "specific"
            strength = "generic"
    return strength


def run(*, state_db: Path = state.DEFAULT_STATE_DB, client: httpx.Client | None = None,
        today: str | None = None, config: dict | None = None,
        page_pause: float = 1.0, probe_pause: float = 0.2) -> dict:
    cfg = config or settings()
    stats = {"sites": len(cfg["sites"]), "listings": 0, "candidates": 0,
             "pending": 0, "no_board": 0, "errors": []}
    if not cfg["sites"]:
        return stats
    today = today or date.today().isoformat()
    known = {normalize_company(c["name"]) for c in state.list_companies(state_db)}
    known |= {normalize_company(d["name"]) for d in state.list_discovered(db_path=state_db)}

    own_client = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True,
                                    headers={"User-Agent": USER_AGENT})
    try:
        listings: list[Listing] = []
        for site in cfg["sites"]:
            try:
                listings.extend(fetch_listings(client, site, cfg["category"],
                                               cfg["max_age_days"], cfg["max_pages"],
                                               pause=page_pause))
            except httpx.HTTPError as e:
                log.warning("discovery: %s failed: %s", site, e)
                stats["errors"].append(f"{site}: {type(e).__name__}")
        stats["listings"] = len(listings)
        found = candidates(listings, known)
        stats["candidates"] = len(found)

        for name, roles in sorted(found.items()):
            hits, errors = probe_name(client, name, pause=probe_pause)
            titles = [r.title for r in roles]
            ranked = sorted(((board_match(h["titles"], titles), h) for h in hits),
                            key=lambda m: {"specific": 0, "generic": 1, None: 2}[m[0]])
            strength, matched = ranked[0] if ranked and ranked[0][0] else (None, None)
            if matched is None and errors:
                # A failed probe says nothing about the company; ask again next week.
                stats["errors"].append(f"{name}: {'; '.join(errors[:2])}")
                continue
            status = "pending" if matched else "no_board"
            state.record_discovered({
                "name": name, "status": status,
                "ats_provider": matched["provider"] if matched else None,
                "ats_slug": matched["slug"] if matched else None,
                "live_postings": matched["count"] if matched else None,
                "title_match": strength,
                "sample_title": roles[0].title, "sample_url": roles[0].url,
                "source": roles[0].source, "first_seen": today,
            }, db_path=state_db)
            stats[status] += 1
    finally:
        if own_client:
            client.close()
    return stats


def promote(name: str, db_path: Path = state.DEFAULT_STATE_DB) -> dict:
    """Track a pending discovered company and mark it added."""
    rows = [d for d in state.list_discovered("pending", db_path)
            if d["name"].lower() == name.lower()]
    if not rows:
        raise KeyError(f"no pending discovered company named {name!r}")
    d = rows[0]
    company = {"name": d["name"], "ats_provider": d["ats_provider"],
               "ats_slug": d["ats_slug"], "careers_url": None, "sector_tags": [],
               "size_band": "unknown"}
    state.upsert_company(company, db_path)
    state.set_discovered_status(d["name"], "added", db_path)
    return company


def track_specific(db_path: Path = state.DEFAULT_STATE_DB) -> list[str]:
    """Track every pending discovery whose board lists a specific role title.

    A specific match is the proof the board is the company's own, so these
    need no human yes. Generic matches ("Senior Product Manager" on a board
    that may belong to someone else) stay pending for the digest.
    """
    names = [d["name"] for d in state.list_discovered("pending", db_path)
             if d.get("title_match") == "specific"]
    for name in names:
        promote(name, db_path)
    return names
