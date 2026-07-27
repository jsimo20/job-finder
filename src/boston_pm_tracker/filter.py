"""Hard filters. Stage 1 runs on raw posting metadata before any LLM call.
Stage 3 runs on the extracted JSON after extract.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .taxonomy import COMP_FLOOR_USD, YOE_MAIN_QUEUE_MAX

BOSTON_RE = re.compile(
    r"\b(boston|cambridge|somerville|watertown|waltham|burlington|brookline|newton|medford|massachusetts|MA)\b",
    re.IGNORECASE,
)
NYC_RE = re.compile(r"\b(new york|nyc|manhattan|brooklyn|queens|NY)\b", re.IGNORECASE)
HARTFORD_RE = re.compile(r"\b(hartford|connecticut|CT)\b", re.IGNORECASE)
# US-region phrases that wholly contain our target metros. "West coast" is
# intentionally excluded — out of scope per spec.
EAST_COAST_RE = re.compile(r"\b(east coast|northeast(?:ern)?)\b", re.IGNORECASE)

# City names that would otherwise be missed when a posting omits the state.
# "New Haven" or "Providence" alone matched nothing before; only "CT" or "RI"
# did. Springfield and Worcester already matched via "MA", but are listed here
# so the metro tiers below can place them.
CT_CITIES_RE = re.compile(
    r"\b(anytown|new haven|stamford|greenwich|norwalk|bridgeport|"
    r"danbury|waterbury|middletown|new london|shelton|trumbull|milford)\b",
    re.IGNORECASE,
)
RI_RE = re.compile(r"\b(providence|rhode island|RI|pawtucket|warwick)\b", re.IGNORECASE)
WEST_MA_RE = re.compile(r"\b(springfield|worcester|holyoke|chicopee|amherst|northampton)\b",
                        re.IGNORECASE)
# Southern NH and the Capital District: same ~2h drive as Boston, so they fit
# the same tolerance. "Nashua" is unambiguous; Manchester, Concord and
# Portsmouth all collide with other states (and Manchester with the UK), so
# they only qualify via an explicit NH token.
NH_RE = re.compile(r"\b(new hampshire|NH|nashua)\b", re.IGNORECASE)
# "Albany, NY" already cleared the gate through the NY token but had no tier,
# so it would never have produced a commute warning.
ALBANY_RE = re.compile(r"\b(albany|schenectady)\b", re.IGNORECASE)

# Drive-time tiers measured from Anytown, CT, which is where James
# actually lives. He targets Boston deliberately and accepts the drive when the
# schedule is hybrid; a 4-5 day onsite requirement at that distance is the thing
# he rules out, which is why this feeds a flag rather than the location gate.
NEAR_METRO_RE = re.compile(
    r"\b(hartford|anytown|new haven|springfield|waterbury|middletown|"
    r"holyoke|chicopee|amherst|northampton|connecticut|CT)\b", re.IGNORECASE)
MID_METRO_RE = re.compile(
    r"\b(worcester|providence|rhode island|RI|stamford|new london|"
    r"pawtucket|warwick|danbury)\b", re.IGNORECASE)
FAR_METRO_RE = re.compile(
    r"\b(boston|cambridge|somerville|watertown|waltham|burlington|brookline|"
    r"newton|medford|new york|nyc|manhattan|brooklyn|queens|greenwich|norwalk|"
    r"bridgeport|albany|schenectady|nashua|new hampshire|NH)\b", re.IGNORECASE)


def metro_tier(location: str | None) -> str | None:
    """near | mid | far | None, by drive time from Anytown.

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

    Deliberately a warning and not a discard: James asked to keep seeing these
    and decide himself, since days-per-week is often negotiable and the posting
    is not always accurate about it.
    """
    if remote_us_ok or onsite_days is None:
        return None
    tier = metro_tier(location)
    if tier == "far" and onsite_days >= 4:
        return f"{onsite_days} days onsite, ~2h each way from Anytown"
    if tier == "mid" and onsite_days >= 5:
        return f"{onsite_days} days onsite, ~1-1.5h each way from Anytown"
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
    r")[,\s]+remote"
    r")\b",
    re.IGNORECASE,
)

PM_TITLE_RE = re.compile(
    r"\b(product manager|product management|head of product|product lead)\b",
    re.IGNORECASE,
)

EXCLUDE_TRACK_RE = re.compile(
    r"\b(product marketing|PMM|project manager|program manager|TPM|technical program|product owner|scrum master|product designer|UX designer|UI designer)\b",
    re.IGNORECASE,
)

# Engineering / IC titles that contain "product" but aren't PM roles.
EXCLUDE_ROLE_RE = re.compile(
    r"\b(engineer|engineering|developer|scientist|analyst|architect|researcher|data engineer|software engineer|security engineer|full[- ]?stack)\b",
    re.IGNORECASE,
)

SENIORITY_KEEP_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|group|head of product)\b",
    re.IGNORECASE,
)

SENIORITY_REJECT_RE = re.compile(
    r"\b(associate product manager|associate pm|APM|junior|jr\.?|intern|product manager (i|ii)\b|PM I+\b)\b",
    re.IGNORECASE,
)

DIRECTOR_PLUS_RE = re.compile(
    r"\b(director|VP|vice president|chief|SVP|EVP|head of (?!product\b))",
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
    if not PM_TITLE_RE.search(title):
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
    if not (
        BOSTON_RE.search(loc_text)
        or NYC_RE.search(loc_text)
        or HARTFORD_RE.search(loc_text)
        or CT_CITIES_RE.search(loc_text)
        or RI_RE.search(loc_text)
        or WEST_MA_RE.search(loc_text)
        or NH_RE.search(loc_text)
        or ALBANY_RE.search(loc_text)
        or EAST_COAST_RE.search(loc_text)
        or is_remote
    ):
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
