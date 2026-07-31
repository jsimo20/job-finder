"""Hard filters. Stage 1 runs on raw posting metadata before any LLM call.
Stage 3 runs on the extracted JSON after extract.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .settings import pipeline_config
from .taxonomy import COMP_FLOOR_USD, YOE_MAIN_QUEUE_MAX

# Location scope lives in config/pipeline.toml, not here — it is a per-user
# preference. This module only compiles what the config declares.
_LOCATION = pipeline_config()["location"]

IN_SCOPE_RE = re.compile(
    "|".join(f"(?:{p})" for p in _LOCATION["in_scope_patterns"]),
    re.IGNORECASE,
)

# Drive-time tiers measured from the user's home base. Distance alone never
# discards a role; a heavy onsite requirement at distance produces a flag,
# because days-per-week is often negotiable and postings misstate it.
NEAR_METRO_RE = re.compile(_LOCATION["tiers"]["near"], re.IGNORECASE)
MID_METRO_RE = re.compile(_LOCATION["tiers"]["mid"], re.IGNORECASE)
FAR_METRO_RE = re.compile(_LOCATION["tiers"]["far"], re.IGNORECASE)

_COMMUTE = _LOCATION["commute"]


def metro_tier(location: str | None) -> str | None:
    """near | mid | far | None, by drive time from the configured home base.

    Checked most-distant first: "Boston, MA" also matches the MA tokens that
    place Springfield, and the far reading is the one that matters for commute.
    """
    loc = location or ""
    if FAR_METRO_RE.search(loc):
        return "far"
    if MID_METRO_RE.search(loc):
        return "mid"
    if NEAR_METRO_RE.search(loc):
        return "near"
    return None


def commute_warning(location: str | None, onsite_days: int | None,
                    remote_us_ok: bool = False) -> str | None:
    """Warn when a role's onsite requirement makes its distance impractical.

    Deliberately a warning and not a discard: the user decides, since
    days-per-week is often negotiable and the posting is not always accurate
    about it.
    """
    if remote_us_ok or onsite_days is None:
        return None
    tier = metro_tier(location)
    if tier == "far" and onsite_days >= _COMMUTE["far_min_days"]:
        return f"{onsite_days} days onsite, {_COMMUTE['far_note']}"
    if tier == "mid" and onsite_days >= _COMMUTE["mid_min_days"]:
        return f"{onsite_days} days onsite, {_COMMUTE['mid_note']}"
    return None

# Country / region tokens that mark a remote role as out-of-scope. We *don't* try
# to detect US states by name (some collide with country names, e.g. Georgia) —
# instead we assume any remote role without an explicit non-US country tag is
# US-eligible by default. This matches how Greenhouse / Lever publish.
NON_US_REMOTE_RE = re.compile(
    r"\b("
    r"emea|apac|latam|"
    r"uk only|europe only|eu only|india only|canada only|"
    # "Remote - <country>" or "Remote-<country>"
    r"remote\s*[-,]\s*("
    r"uk|emea|eu|europe|india|canada|australia|new\s*zealand|"
    r"japan|philippines|vietnam|singapore|hong\s*kong|israel|"
    r"brazil|mexico|argentina|colombia|chile|costa\s*rica|"
    r"germany|france|spain|italy|netherlands|poland|portugal|"
    r"sweden|denmark|norway|finland|ireland|united\s*kingdom|switzerland"
    r")|"
    # "<country>, Remote" or "<country> Remote"
    r"("
    r"canada|united\s*kingdom|ireland|germany|france|spain|italy|netherlands|"
    r"poland|portugal|sweden|denmark|norway|finland|switzerland|"
    r"japan|philippines|vietnam|singapore|hong\s*kong|israel|india|"
    r"brazil|mexico|argentina|colombia|chile|costa\s*rica|"
    r"australia|new\s*zealand"
    r")[-,\s]+remote"   # dash separator: "Canada - Remote"
    r")\b",
    re.IGNORECASE,
)

# Title targeting is per-user market preference and lives in
# config/pipeline.toml [titles]; this module only compiles it.
_TITLES = pipeline_config()["titles"]

ROLE_TITLE_RE = re.compile(
    "|".join(f"(?:{p})" for p in _TITLES["role_patterns"]), re.IGNORECASE)
EXCLUDE_TRACK_RE = re.compile(_TITLES["exclude_track"], re.IGNORECASE)
# Titles that contain target words but are really a different job.
EXCLUDE_ROLE_RE = re.compile(_TITLES["exclude_role"], re.IGNORECASE)
SENIORITY_KEEP_RE = re.compile(_TITLES["seniority_keep"], re.IGNORECASE)
SENIORITY_REJECT_RE = re.compile(_TITLES["seniority_reject"], re.IGNORECASE)
DIRECTOR_PLUS_RE = re.compile(_TITLES["above_band"], re.IGNORECASE)


@dataclass
class FilterResult:
    keep: bool
    reason: str  # 'keep' or 'discard:<short_reason>'


def stage1(*, title: str, location: str | None, workplace_type: str | None) -> FilterResult:
    """Apply hard filters to raw posting metadata. Cheap. Runs before any LLM call.

    Only the explicit `location` and `workplace_type` fields are used for the location
    check — earlier versions scanned the full raw JSON, which produced false positives
    because most ATS payloads embed company-wide office strings ("Boston, MA") on
    every posting regardless of the role's actual location.
    """
    # Track filter
    if EXCLUDE_TRACK_RE.search(title):
        return FilterResult(False, "discard:wrong_track")
    # Director-tier rejection runs before PM check so "Director of Product"
    # returns the right reason.
    if DIRECTOR_PLUS_RE.search(title):
        return FilterResult(False, "discard:director_plus")
    # A clear "Product Manager" / "Head of Product" / "Product Lead" stem wins
    # over the engineering-role exclusion, since the engineering keywords often
    # appear as the *product area* (e.g. "Lead PM, Developer Experience") rather
    # than the role itself.
    if not ROLE_TITLE_RE.search(title):
        if EXCLUDE_ROLE_RE.search(title):
            return FilterResult(False, "discard:engineering_or_ic_role")
        return FilterResult(False, "discard:not_pm_title")

    # Seniority floor
    if SENIORITY_REJECT_RE.search(title):
        return FilterResult(False, "discard:too_junior")
    if not SENIORITY_KEEP_RE.search(title):
        return FilterResult(False, "discard:no_seniority_marker")

    # Location
    loc_text = location or ""
    is_remote = (workplace_type or "").lower() == "remote" or bool(
        re.search(r"\bremote\b", loc_text, re.IGNORECASE)
    )
    if is_remote and NON_US_REMOTE_RE.search(loc_text):
        return FilterResult(False, "discard:non_us_remote")
    if not (IN_SCOPE_RE.search(loc_text) or is_remote):
        return FilterResult(False, "discard:wrong_location")

    return FilterResult(True, "keep")


@dataclass
class Stage3Result:
    keep: bool
    queue: str  # 'main' | 'stretch' | 'discard'
    reason: str


def stage3(*, yoe_required: int | None, comp_base_min: int | None,
           comp_base_max: int | None, comp_source: str | None) -> Stage3Result:
    """Post-extraction hard filters. Routes to main vs stretch queue.

    Comp gating uses the *top* of the posted range. A wide range like $136-204K
    spans the floor; the actual offer can land anywhere inside it, so we only
    discard when even the ceiling is underwater.
    """
    if comp_source == "posted":
        ceiling = comp_base_max if comp_base_max is not None else comp_base_min
        if ceiling is not None and ceiling < COMP_FLOOR_USD:
            return Stage3Result(False, "discard", f"comp_ceiling_below_floor:{ceiling}")
    if yoe_required is not None and yoe_required > YOE_MAIN_QUEUE_MAX:
        return Stage3Result(True, "stretch", f"yoe_required:{yoe_required}")
    return Stage3Result(True, "main", "keep")
