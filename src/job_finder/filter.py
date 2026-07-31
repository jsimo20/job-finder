"""Hard filters. Stage 1 runs on raw posting metadata before any LLM call.
Stage 3 runs on the extracted JSON after extract.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .settings import pipeline_config
from .taxonomy import COMP_FLOOR_USD, YOE_MAIN_QUEUE_MAX

# Location scope and title targeting live in config/pipeline.toml — per-user
# preferences. configure() compiles what a config declares; tests call it
# with a fictional fixture geography so no real region is baked in anywhere.

IN_SCOPE_RE = NEAR_METRO_RE = MID_METRO_RE = FAR_METRO_RE = None
ROLE_TITLE_RE = EXCLUDE_TRACK_RE = EXCLUDE_ROLE_RE = None
SENIORITY_KEEP_RE = SENIORITY_REJECT_RE = DIRECTOR_PLUS_RE = None
_COMMUTE: dict = {}


def configure(cfg: dict) -> None:
    """(Re)compile all config-driven matchers from a pipeline-config dict."""
    global IN_SCOPE_RE, NEAR_METRO_RE, MID_METRO_RE, FAR_METRO_RE, _COMMUTE
    global ROLE_TITLE_RE, EXCLUDE_TRACK_RE, EXCLUDE_ROLE_RE
    global SENIORITY_KEEP_RE, SENIORITY_REJECT_RE, DIRECTOR_PLUS_RE
    location = cfg["location"]
    IN_SCOPE_RE = re.compile(
        "|".join(f"(?:{p})" for p in location["in_scope_patterns"]), re.IGNORECASE)
    NEAR_METRO_RE = re.compile(location["tiers"]["near"], re.IGNORECASE)
    MID_METRO_RE = re.compile(location["tiers"]["mid"], re.IGNORECASE)
    FAR_METRO_RE = re.compile(location["tiers"]["far"], re.IGNORECASE)
    _COMMUTE = location["commute"]
    titles = cfg["titles"]
    ROLE_TITLE_RE = re.compile(
        "|".join(f"(?:{p})" for p in titles["role_patterns"]), re.IGNORECASE)
    EXCLUDE_TRACK_RE = re.compile(titles["exclude_track"], re.IGNORECASE)
    EXCLUDE_ROLE_RE = re.compile(titles["exclude_role"], re.IGNORECASE)
    SENIORITY_KEEP_RE = re.compile(titles["seniority_keep"], re.IGNORECASE)
    SENIORITY_REJECT_RE = re.compile(titles["seniority_reject"], re.IGNORECASE)
    DIRECTOR_PLUS_RE = re.compile(titles["above_band"], re.IGNORECASE)


configure(pipeline_config())


def metro_tier(location: str | None) -> str | None:
    """near | mid | far | None, by drive time from the configured home base.

    Checked most-distant first: a far-metro city string usually also matches
    the state tokens that place near-metro cities, and the far reading is the
    one that matters for commute.
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

@dataclass
class FilterResult:
    keep: bool
    reason: str  # 'keep' or 'discard:<short_reason>'


def stage1(*, title: str, location: str | None, workplace_type: str | None) -> FilterResult:
    """Apply hard filters to raw posting metadata. Cheap. Runs before any LLM call.

    Only the explicit `location` and `workplace_type` fields are used for the location
    check — earlier versions scanned the full raw JSON, which produced false positives
    because most ATS payloads embed company-wide office strings on every posting
    regardless of the role's actual location.
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
