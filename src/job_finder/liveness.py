"""Check whether a posting is still listed on its board, before spending tokens on it.

A digest is a snapshot. By the time a batch runs against it some postings have
closed, and tailoring one costs a full draft, fact-check and render for a form
that no longer exists.

HTTP status does not answer the question. Ashby serves a single-page app that
returns 200 with no "not found" marker for a closed posting; only the board
listing distinguishes them. So a posting is live when its external_id still
appears in what its board returns.

These are the listing endpoints, not the collect adapters: the adapters pull
full JD text for every posting on the board, which takes minutes per company.
The listings answer the same question in well under a second.

**Unknown means live.** A network failure, an unrecognised provider, or a
company absent from the tracked list all return None, and callers treat that as
live. Skipping a real posting costs an application; tailoring a dead one costs
tokens.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

import httpx

from . import state

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0


def _greenhouse(slug: str, client: httpx.Client) -> set[str]:
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    r.raise_for_status()
    return {str(j["id"]) for j in r.json().get("jobs", [])}


def _ashby(slug: str, client: httpx.Client) -> set[str]:
    r = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    r.raise_for_status()
    return {str(j["id"]) for j in r.json().get("jobs", [])}


def _lever(slug: str, client: httpx.Client) -> set[str]:
    r = client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    r.raise_for_status()
    return {str(j["id"]) for j in r.json()}


# Workday has no cheap listing endpoint; its board is a paged POST. Left out on
# purpose so a Workday role reads as undetermined and still gets tailored.
LISTERS: dict[str, Callable[[str, httpx.Client], set[str]]] = {
    "greenhouse": _greenhouse,
    "ashby": _ashby,
    "lever": _lever,
}


def live_ids(provider: str, slug: str, client: httpx.Client) -> set[str] | None:
    """External ids currently listed on one board, or None if it cannot be read."""
    lister = LISTERS.get((provider or "").lower())
    if lister is None:
        return None
    try:
        return lister(slug, client)
    except Exception as exc:  # network, schema drift, board removed
        log.warning("liveness: could not read %s board %r: %s", provider, slug, exc)
        return None


def check(roles: Iterable[dict[str, Any]], *, db_path=state.DEFAULT_STATE_DB,
          timeout: float = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    """Annotate each role with `live`: True, False, or None when undetermined.

    `roles` are dicts carrying at least `company` and `external_id`. Each board
    is read once, so several roles at one company cost one request.
    """
    companies = {c["name"].lower(): c for c in state.list_companies(db_path)}
    roles = list(roles)
    boards: dict[tuple[str, str], set[str] | None] = {}

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for role in roles:
            company = companies.get((role.get("company") or "").lower())
            if company is None:
                role["live"], role["liveness_note"] = None, "company not tracked"
                continue

            key = (company["ats_provider"], company["ats_slug"])
            if key not in boards:
                boards[key] = live_ids(*key, client=client)
            ids = boards[key]

            if ids is None:
                role["live"] = None
                role["liveness_note"] = f"no cheap listing for {key[0]}"
            elif str(role.get("external_id")) in ids:
                role["live"], role["liveness_note"] = True, ""
            else:
                role["live"] = False
                role["liveness_note"] = "no longer listed on the board"
    return roles


def partition(roles: Iterable[dict[str, Any]], **kwargs
              ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(worth_tailoring, dead). Undetermined roles are worth tailoring."""
    checked = check(roles, **kwargs)
    return ([r for r in checked if r.get("live") is not False],
            [r for r in checked if r.get("live") is False])
