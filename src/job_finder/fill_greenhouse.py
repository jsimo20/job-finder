"""Deterministic Greenhouse application autofill.

Fills the standard Greenhouse section (contact, work auth, EEO, uploads) with
plain Playwright — zero LLM tokens. Anything it can't confidently map is left
blank and listed in the printed report. The browser window stays open after
filling so the user can review, fill leftovers, and submit by hand.

Answers come from profile/profile.toml (identity, EEO, work authorization)
and the per-app folder's standard_answers.md.

Usage (single):
    python -m job_finder.fill_greenhouse --url <application_url> \
        --folder "<per-app folder>" [--city "Anytown"] [--no-hold]

Usage (batch): repeat --url and --folder in matching order. All applications
fill in ONE browser, one tab each, and every tab is left open for review.

    python -m job_finder.fill_greenhouse \
        --url <url_a> --folder "<folder_a>" \
        --url <url_b> --folder "<folder_b>"

Never clicks Submit. Salary fields are always skipped.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import (Frame, Page, TimeoutError as PWTimeout,
                                     sync_playwright)
except ImportError:  # fill_grader imports the pattern constants and needs no browser
    Frame = Page = sync_playwright = None  # type: ignore[assignment]
    PWTimeout = TimeoutError  # type: ignore[assignment,misc]

from job_finder import form_inventory, settings
from job_finder.form_inventory import has_selection, label_of

STEP_TIMEOUT_MS = 10_000

TEXT_FIELDS: list[tuple[str, str]] = [
    # (label regex, answers key) — order matters: "preferred first" before
    # "first", and "e-mail" before the bare "address" ("Email Address").
    (r"preferred\s*(first\s*)?name", "preferred_name"),
    (r"first\s*name", "first_name"),
    (r"last\s*name", "last_name"),
    (r"e-?mail", "email"),
    (r"linked\s*in", "linkedin"),
    # A GitHub profile is not a portfolio. Claiming "portfolio" for the
    # github answer puts a code-hosting link in a field asking for personal
    # work, and claims the field for a user who has no portfolio at all.
    (r"github", "github"),
    (r"portfolio|personal\s*site|(?<!e-)(?<!e)\bwebsite\b", "portfolio"),
    (r"start\s*(date\s*)?year", "start_year"),
    (r"end\s*(date\s*)?year", "end_year"),
    (r"address", "address"),
]

# Options that must never be selected for a field, whatever the match says.
# The sponsorship veto is the important one. Some forms phrase the correct
# answer as a positive statement, not a negation:
#     "I am legally authorized to work in this country for any employer."
#     "I require sponsorship now or in the future."
# so none of the negation candidates match, and a bare "no" resolves cleanly and
# uniquely to the wrong option through the "no" in "now". No string-similarity
# rule catches that. Naming the answer that must never be chosen does.
VETO: dict[str, str] = {
    # ^yes$ is vetoed on sponsorship questions: "Do you require sponsorship?
    # Yes/No" makes a bare Yes the needs-sponsorship answer. A longer option
    # that merely contains "yes" ("Yes, I am authorized and do not require
    # sponsorship") stays selectable.
    r"sponsor": r"\bi\s+require\s+sponsorship\b|\bwill\s+require\s+sponsorship\b|"
                r"\bh-?1-?b\b|\bopt\b|\bvisa\s+sponsorship\s+(is\s+)?required\b|"
                r"^\s*yes\s*[.!]?\s*$",
    r"authori[sz]": r"\bnot\s+authorized\b|\bi\s+require\s+sponsorship\b",
}

def build_combo_fields(profile: dict) -> list[tuple[str, list[str]]]:
    """(label regex, candidate texts tried in order), from the user's profile.

    Ordered most-specific first; short answers like "no" are last resorts
    because sentence-phrased options make them ambiguous or, worse, uniquely
    wrong.

    Authorization and sponsorship candidates are only emitted when the profile
    says the user is authorized and needs no sponsorship — any other situation
    is left blank for the user to answer, because a wrong answer either way is
    unrecoverable after submit. EEO rows are emitted only for values the
    profile actually sets; an empty value means "leave it for me."
    """
    answers = profile.get("answers", {})
    eeo = profile.get("eeo", {})
    education = profile.get("education", {})
    combos: list[tuple[str, list[str]]] = []
    # User-defined [[custom_combos]] go first so they can override any
    # built-in mapping for the same label.
    for custom in profile.get("custom_combos", []):
        if custom.get("label") and custom.get("candidates"):
            combos.append((custom["label"], list(custom["candidates"])))
    authorized_no_sponsor = (answers.get("work_authorized")
                             and not answers.get("requires_sponsorship", True))
    if authorized_no_sponsor:
        # Order is load-bearing. sponsor BEFORE authorization: a live form's
        # "Do you ... require immigration sponsorship for work authorization?"
        # contains both words, and matching the authorization row first
        # committed its "yes" candidate — the one answer that must never land
        # on a sponsorship question (caught in a post-fill audit). A sponsorship label that mentions authorization is still a
        # sponsorship question; a plain authorization question never says
        # "sponsor". Then authorization before country, whose label contains
        # the word "country".
        combos.append((r"sponsor", ["legally authorized to work", "do not require sponsorship",
                                    "will not require", "no"]))
        combos.append((r"authori[sz]", ["legally authorized to work", "no restriction", "yes"]))
    combos.append((r"country", [answers.get("country", "United States")]))
    combos.append((r"hear about", list(answers.get("hear_about",
                                                   ["Careers Page", "Company Website"]))))
    for pattern, key in ((r"school", "school"), (r"degree", "degree"),
                         (r"discipline|field of study|major", "discipline"),
                         (r"start\s*(date\s*)?month", "start_month"),
                         (r"end\s*(date\s*)?month", "end_month")):
        value = education.get(key)
        if value:
            # A list means ordered fallbacks, for forms whose option list has
            # no entry for the first-choice answer.
            combos.append((pattern, list(value) if isinstance(value, list) else [value]))
    # transgender before gender: "I identify as transgender" contains the
    # substring "gender", and the gender row once tried "Male" against its
    # Yes/No options on a live form (fail-closed left it blank, but only by
    # luck of the option texts).
    for pattern, key in ((r"transgender", "transgender"),
                         (r"(?<!trans)gender", "gender"), (r"hispanic", "hispanic"),
                         (r"race", "race"), (r"veteran", "veteran"),
                         (r"disabilit", "disability")):
        value = eeo.get(key)
        if value:
            combos.append((pattern, list(value) if isinstance(value, list) else [value]))
    combos.append((r"certify", ["Yes"]))
    combos.append((r"privacy|acknowledg", ["Yes"]))
    if eeo.get("pronouns"):
        combos.append((r"pronoun", [eeo["pronouns"]]))
    return combos


# Module-level default for tests and callers that pass no combos explicitly.
# Falls back to profile.example/ on a fresh clone, whose [answers] defaults
# keep the structure intact while its empty [eeo] emits no EEO rows. main()
# rebuilds this from the user's real profile before touching a form.
COMBO_FIELDS: list[tuple[str, list[str]]] = build_combo_fields(settings.load_profile())


def veto_for(label: str) -> str | None:
    for pattern, veto in VETO.items():
        if re.search(pattern, label, re.I):
            return veto
    return None

# Labels that contain a name word but are asking about somebody who is not
# the applicant. "…please indicate their first and last name" once matched the
# last-name rule and filled in the applicant's own surname, asserting an
# employee referral that never happened.
# Word-anchored on purpose: a bare "referr" also matches "P-referred First Name",
# which would block a field that fills correctly today.
# "manager" on its own cannot be trapped the way the other role words can. A
# product-management application is full of self-referential job titles, so a
# bare match fires on questions about the applicant: "Have you been a product
# manager of a product line or a major feature set?" is not a request for
# somebody else's name, but it was graded as one. Trap the word only where the
# label actually asks for a manager's identity. "supervisor" and "recruiter"
# stay bare because neither doubles as a title the applicant would claim here.
_MANAGER_TRAP = r"\bmanagers?(?:['\u2019]s)?\s+(?:name|e-?mail|phone|contact|title)\b"

NAME_TRAP_PATTERN = re.compile(
    r"\brefer(r|red|ence|ral)|\bemergency\b|\bsupervisor\b|"
    + _MANAGER_TRAP +
    r"|\bspouse\b|\bguardian\b|next of kin|who told you|\brecruiter\b",
    re.I,
)

SKIP_PATTERN = re.compile(r"salary|compensation|desired pay|expected pay", re.I)

CITY_PATTERN = re.compile(r"cities.*available|available.*cities", re.I)


def parse_answers(folder: Path, profile: dict | None = None) -> dict[str, str]:
    """Contact values from the per-app standard_answers.md, with profile.toml
    [identity] filling any key the markdown lacks. The markdown wins when both
    have a value, since it can carry per-application overrides."""
    sa_path = folder / "standard_answers.md"
    text = sa_path.read_text(encoding="utf-8") if sa_path.exists() else ""

    def grab(key: str) -> str:
        m = re.search(rf"\*\*{key}:\*\*\s*\(?([^)\n]+)\)?", text, re.I)
        return m.group(1).strip() if m else ""

    ident = (profile or {}).get("identity", {})
    education = (profile or {}).get("education", {})
    full_name = grab("Full name") or ident.get("name", "")
    first, _, last = full_name.partition(" ")
    return {
        "first_name": first,
        "last_name": last,
        "preferred_name": grab("Preferred name") or first,
        "email": grab("Email") or ident.get("email", ""),
        "phone": grab("Phone") or ident.get("phone", ""),
        "linkedin": grab("LinkedIn") or ident.get("linkedin", ""),
        "github": grab("GitHub") or ident.get("github", ""),
        "address": grab("Address") or ident.get("address", ""),
        "start_year": str(education.get("start_year", "") or ""),
        "end_year": str(education.get("end_year", "") or ""),
    }


def find_form_root(page: Page) -> Frame | Page:
    """Greenhouse forms are either the page itself or embedded in an iframe."""
    if "greenhouse.io" in page.url:
        return page
    handle = page.query_selector("iframe#grnhse_iframe")
    if handle:
        frame = handle.content_frame()
        if frame:
            return frame
    for frame in page.frames:
        if "greenhouse" in frame.url:
            return frame
    # Company careers pages wrap the board under their own domain, so neither
    # the URL nor the iframe id gives it away — fall back to control count.
    return form_inventory.find_form_root(page)


def build_custom_text(profile: dict) -> list[tuple[str, str]]:
    """User-defined [[custom_text]] rules: label regex -> literal value.
    The text-field counterpart of [[custom_combos]]."""
    return [(c["label"], c["value"]) for c in profile.get("custom_text", [])
            if c.get("label") and c.get("value")]


def fill_text_inputs(root, answers: dict[str, str], report: dict,
                     custom_text: list[tuple[str, str]] | None = None) -> None:
    inputs = root.locator("input[type='text'], input[type='email'], input[type='tel']")
    for i in range(inputs.count()):
        el = inputs.nth(i)
        if not el.is_visible():
            continue
        if el.get_attribute("role") == "combobox" or el.get_attribute("aria-autocomplete"):
            continue  # react-select filter input — the combo pass owns it
        label = label_of(el)
        if not label or SKIP_PATTERN.search(label):
            if label:
                report["skipped"].append(f"{label} (salary/comp — always manual)")
            continue
        if el.input_value():
            continue
        if NAME_TRAP_PATTERN.search(label):
            report["unmapped"].append(f"{label[:60]} (asks about someone else — never autofilled)")
            continue
        if el.get_attribute("type") == "tel" or re.search(r"phone", label, re.I):
            el.fill(answers["phone"])
            report["filled"].append(f"{label}: {answers['phone']}")
            continue
        for pattern, key in TEXT_FIELDS:
            if re.search(pattern, label, re.I):
                value = answers.get(key, "")
                if value:
                    el.fill(value)
                    report["filled"].append(f"{label}: {value}")
                else:
                    report["unmapped"].append(f"{label[:60]} (no value in answers)")
                break
        else:
            for pattern, value in (custom_text or []):
                if re.search(pattern, label, re.I):
                    el.fill(value)
                    report["filled"].append(f"{label}: {value}")
                    break
            else:
                report["unmapped"].append(label)


def match_option(texts: list[str], want: str) -> int | None:
    """Index of the ONE option matching `want`, or None if none or several do.

    Tiered so a precise match always beats a loose one: exact, then whole-word,
    then substring. Ambiguity at the winning tier returns None on purpose.

    Failing closed matters more than filling the field. One live form's
    sponsorship options were "I do not require sponsorship" and "I require
    sponsorship now or in the future"; a substring search for "no" matches both
    (via "not" and "now"), and the old code took whichever came first in the
    DOM. It picked the wrong one. A blank field is recoverable at review time; a submitted
    application claiming the applicant needs visa sponsorship is not.
    """
    w = want.lower().strip()
    for hits in (
        [i for i, t in enumerate(texts) if t == w],
        [i for i, t in enumerate(texts) if re.search(rf"\b{re.escape(w)}\b", t)],
        [i for i, t in enumerate(texts) if w in t],
    ):
        if len(hits) == 1:
            return hits[0]
        if hits:
            return None          # several options match this precisely; do not guess
    return None


def _open_menu(combo) -> bool:
    # click doesn't always open the menu (hydration races) — verify and retry
    for _ in range(3):
        combo.click()
        combo.page.wait_for_timeout(300)
        if combo.get_attribute("aria-expanded") == "true":
            return True
    return False


def _visible_option_texts(root, combo, *, poll: int = 6) -> list[str]:
    options = root.locator("[role='option']")
    for _ in range(poll):
        combo.page.wait_for_timeout(500)
        if options.count():
            break
    out = []
    for i in range(options.count()):
        opt = options.nth(i)
        out.append((opt.text_content() or "").strip() if opt.is_visible() else "")
    return out


def fill_combo(root, combo, candidates: list[str],
               seen_options: list[str] | None = None,
               veto: str | None = None) -> tuple[bool, str]:
    """React-select pattern: open, type to filter, click the one matching option.

    Tries each candidate in order and commits the first that resolves to exactly
    one option. Enter alone doesn't commit on Greenhouse's react-select build, so
    the option element is clicked directly and the selection is then verified in
    the DOM. Returns (committed, reason).

    react-select renders its menu only while open, so the option list is
    unreachable from a static inventory pass. This is the one moment it is
    visible; `seen_options` collects it for the audit manifest.
    """
    ambiguous_on: list[str] = []
    vetoed_on: list[str] = []
    for attempt, want in enumerate(candidates):
        if not _open_menu(combo):
            return False, "menu never opened"

        # Harvest before typing: press_sequentially filters the menu, and a
        # filtered list would misrepresent what the form actually offers. Async
        # lists (city autocomplete) come up empty here and get picked up below.
        if seen_options is not None and attempt == 0:
            for raw in _visible_option_texts(root, combo, poll=2):
                if raw and raw not in seen_options:
                    seen_options.append(raw)

        combo.press_sequentially(want, delay=20)
        texts = _visible_option_texts(root, combo)
        if seen_options is not None:
            for raw in texts:
                if raw and raw not in seen_options:
                    seen_options.append(raw)

        idx = match_option([t.lower() for t in texts], want)
        if idx is not None and veto and re.search(veto, texts[idx], re.I):
            # Resolved cleanly, but to an answer that must never be given.
            vetoed_on.append(texts[idx][:50])
            idx = None
        if idx is not None:
            root.locator("[role='option']").nth(idx).click()
            combo.page.wait_for_timeout(200)
            if has_selection(combo):
                return True, want
        elif [t for t in texts if want.lower() in t.lower()]:
            ambiguous_on.append(want)

        # Clear the filter so the next candidate starts from the full list.
        try:
            combo.press("Escape")
            for _ in range(len(want)):
                combo.press("Backspace")
        except PWTimeout:
            pass

    if vetoed_on:
        return False, f"VETOED — only match was {vetoed_on[0]!r}; answer this one yourself"
    if ambiguous_on:
        return False, f"ambiguous: {', '.join(ambiguous_on)} matched multiple options"
    return False, "no option matched"


def fill_combos(root, city: str, report: dict,
                harvested: dict[str, list[str]] | None = None) -> None:
    # Multiple passes: the Race dropdown only appears after Hispanic/Latino is
    # answered, and failed commits (hydration races) get retried next pass.
    done: set[str] = set()       # committed or confirmed unmappable
    tries: dict[str, int] = {}
    MAX_TRIES = 2
    for _ in range(3):
        combos = root.locator("[role='combobox']")
        for i in range(combos.count()):
            el = combos.nth(i)
            if not el.is_visible():
                continue
            label = label_of(el)
            if not label or label in done or SKIP_PATTERN.search(label):
                continue
            if has_selection(el):
                done.add(label)
                continue
            if CITY_PATTERN.search(label):
                candidates = [city]
            else:
                for pattern, opts in COMBO_FIELDS:
                    if re.search(pattern, label, re.I):
                        candidates = list(opts)
                        break
                else:
                    done.add(label)
                    report["unmapped"].append(f"{label[:60]} (combobox)")
                    continue
            tries[label] = tries.get(label, 0) + 1
            bucket = harvested.setdefault(label, []) if harvested is not None else None
            try:
                ok, reason = fill_combo(root, el, candidates, bucket, veto_for(label))
            except PWTimeout:
                ok, reason = False, "timed out"
            if ok:
                done.add(label)
                report["filled"].append(f"{label[:60]}: {reason}")
            elif reason.startswith(("ambiguous", "VETOED")) or tries[label] >= MAX_TRIES:
                # Ambiguity is final: retrying re-derives the same options and
                # would only risk committing a guess on the next pass.
                done.add(label)
                report["unmapped"].append(f"{label[:60]} ({reason})")
                if reason.startswith("VETOED"):
                    # Surface next to the other submission blockers, not buried
                    # in the unmapped list — a wrong answer here is unrecoverable.
                    report["required_empty"].append(f"{label[:60]} — {reason}")


def _upload_landed(root, path: Path, *, timeout_ms: int = 4000) -> bool:
    """Whether the form is showing this file as attached.

    Checked against the rendered filename, NOT input.files. Greenhouse consumes
    the file on change, removes the input node, and renders a filename chip in
    its place, so reading files.length back finds either a detached node or the
    next empty input and reports 0 on a perfectly good upload.
    """
    waited = 0
    while waited < timeout_ms:
        try:
            if root.evaluate("(name) => document.body.innerText.includes(name)", path.name):
                return True
        except Exception:
            return False
        root.wait_for_timeout(400) if hasattr(root, "wait_for_timeout") else None
        waited += 400
    return False


def _try_upload(el, path: Path, what: str, report: dict, *, how: str = "",
                root=None) -> bool:
    """Attach one file and VERIFY it stuck. Never reports an upload it can't see.

    Two distinct failures, both observed live:

    A non-actionable file input (a hidden drag-drop target, or a cover-letter
    slot the company disabled) raises a timeout. Letting that propagate cost
    three of five applications their entire fill, including work that had
    already succeeded, so it is caught.

    Worse, set_input_files can return cleanly while the file does not attach --
    Greenhouse re-renders the input and the selection is dropped. The filler
    reported "Resume upload (by position)" on four applications that had no
    resume attached. A report claiming an upload that did not happen is more
    dangerous than a visible failure, because the form looks ready to submit.
    """
    try:
        el.set_input_files(str(path), timeout=5000)
    except Exception as exc:
        report["unmapped"].append(f"{what} upload failed ({type(exc).__name__})")
        return False
    if root is not None and not _upload_landed(root, path):
        report["unmapped"].append(f"{what} upload did not register on the form")
        return False
    report["filled"].append(f"{what} upload{how}: {path.name}")
    return True


def _upload_via_chooser(page, root, label_res: list[str], path: Path, what: str,
                        report: dict) -> bool:
    """Fallback: drive the visible Attach button through a real file chooser.

    JS-backed uploaders ignore a programmatic set_input_files on their hidden
    input but handle the browser's own file-chooser event, so this reaches the
    ones the direct path cannot.

    Tries each label pattern in order — some cover-letter widgets have no
    element whose text says "cover letter" (that's a section header); the
    clickable button just says "Attach". Success is only reported when the
    filename renders on the form, same as every other upload path.
    """
    for label_re in label_res:
        try:
            btn = root.get_by_text(re.compile(label_re, re.I)).first
            if not btn.count():
                continue
            with page.expect_file_chooser(timeout=5000) as fc:
                btn.click()
            fc.value.set_files(str(path))
            page.wait_for_timeout(800)
            if _upload_landed(root, path):
                report["filled"].append(f"{what} upload (file chooser): {path.name}")
                return True
        except Exception:
            continue
    return False


def upload_files(root, folder: Path, report: dict, page=None) -> None:
    resume = next(folder.glob("*_Resume_*.pdf"), None)
    cover = next(folder.glob("*_CoverLetter_*.pdf"), None)
    file_inputs = root.locator("input[type='file']")
    unmatched: list[int] = []
    placed = {"resume": False, "cover": False}
    for i in range(file_inputs.count()):
        el = file_inputs.nth(i)
        try:
            context = el.evaluate(
                "(node) => (node.closest('div[class], fieldset, section')?.textContent"
                " || '') + ' ' + (node.getAttribute('aria-label') || '')"
            )
        except Exception:
            context = ""
        if re.search(r"cover", context, re.I):
            if cover and not placed["cover"]:
                placed["cover"] = _try_upload(el, cover, "Cover letter", report, root=root)
        elif re.search(r"resume|cv", context, re.I):
            if resume and not placed["resume"]:
                placed["resume"] = _try_upload(el, resume, "Resume", report, root=root)
        else:
            unmatched.append(i)

    # Greenhouse convention when labels aren't reachable: first file input is
    # the resume, second (if present) is the cover letter. Only fill what the
    # labelled pass missed, so a stray extra input can't re-upload the resume.
    for idx in unmatched:
        if resume and not placed["resume"]:
            placed["resume"] = _try_upload(file_inputs.nth(idx), resume, "Resume",
                                           report, how=" (by position)", root=root)
        elif cover and not placed["cover"]:
            placed["cover"] = _try_upload(file_inputs.nth(idx), cover, "Cover letter",
                                          report, how=" (by position)", root=root)
        else:
            break
    # Last resort: drive the visible Attach button rather than the hidden input.
    if page is not None:
        if resume and not placed["resume"]:
            placed["resume"] = _upload_via_chooser(page, root, [r"attach|resume|upload"],
                                                   resume, "Resume", report)
        if cover and not placed["cover"]:
            # The bare "Attach" button is only safe once the resume is placed;
            # before that, the first Attach on the page is usually the
            # resume's, and clicking it would put the cover letter there.
            cover_labels = [r"cover letter"] + ([r"^attach$"] if placed["resume"] else [])
            placed["cover"] = _upload_via_chooser(page, root, cover_labels,
                                                  cover, "Cover letter", report)
    if resume and not placed["resume"]:
        report["required_empty"].append(
            "RESUME NOT ATTACHED — attach it by hand before submitting")


def audit_required(root, report: dict) -> None:
    empty = root.evaluate(
        """() => {
            const out = [];
            const labelFor = (el) => {
                const byId = el.id && document.querySelector(`label[for="${el.id}"]`);
                if (byId) return byId.textContent.trim();
                const ids = el.getAttribute('aria-labelledby');
                if (ids) return ids.split(' ')
                    .map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
                return (el.getAttribute('aria-label') || '').trim();
            };
            document.querySelectorAll('input[role="combobox"]').forEach(el => {
                const c = el.closest('[class*="select__control"], [class*="control"]');
                const has = c?.querySelector(
                    '[class*="single-value"], [class*="singleValue"], [class*="multi-value"]');
                const label = labelFor(el);
                if (!has && label) out.push(label.slice(0, 60) + ' (select)');
            });
            document.querySelectorAll(
                'input[type=text][required], input[type=email][required], input[type=tel][required],' +
                'input[type=text][aria-required="true"], input[type=email][aria-required="true"]'
            ).forEach(el => {
                if (el.getAttribute('role') === 'combobox') return;
                const label = labelFor(el);
                if (!el.value && label) out.push(label.slice(0, 60));
            });
            return out;
        }"""
    )
    report["required_empty"].extend(empty)   # extend: upload_files may have added to this


def capture_audit(root, slug: str, phase: str, url: str, report: dict, *,
                  skip: bool = False,
                  harvested: dict[str, list[str]] | None = None) -> None:
    """Write one field-inventory manifest for the eval seed data.

    Best-effort by design: the capture is read-only against the form, and any
    failure is recorded in the report rather than blocking the fill.
    """
    if skip:
        return
    try:
        inventory = form_inventory.capture(root)
        if harvested:
            form_inventory.merge_options(inventory, harvested)
        path = form_inventory.write_audit(inventory, slug=slug, phase=phase, url=url)
        report["audits"].append(f"{phase}: {len(inventory)} fields -> {path.name}")
    except Exception as exc:
        report["audits"].append(f"{phase}: capture failed ({exc})")


def fill_one(context, url: str, folder: Path, city: str, *,
             slug: str | None = None, no_audit: bool = False,
             shot: Path | None = None, report: dict | None = None,
             profile: dict | None = None) -> tuple[Page, dict]:
    """Fill one application in a new TAB of the caller's context.

    Takes a BrowserContext, never a Browser. `browser.new_page()` implicitly
    creates a fresh context per call, and Chromium renders one window per
    context — calling it in a loop produced five separate windows instead of
    five tabs. Pages sharing a context are tabs in a single window.

    The page is deliberately left open; the caller decides when to hold or exit.
    Pass `report` so a partially-filled application still reports what landed
    before an exception.
    """
    slug = slug or re.sub(r"^\d{4}-\d{2}-\d{2}_", "", folder.name)
    answers = parse_answers(folder, profile)
    if report is None:
        report = {"filled": [], "skipped": [], "unmapped": [],
                  "required_empty": [], "audits": []}
    harvested: dict[str, list[str]] = {}
    custom_text = build_custom_text(profile or {})

    page = context.new_page()
    page.set_default_timeout(STEP_TIMEOUT_MS)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    try:  # OneTrust cookie banner steals clicks until dismissed
        btn = page.locator("#onetrust-accept-btn-handler")
        if btn.count() and btn.first.is_visible():
            btn.first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass

    root = find_form_root(page)
    if form_inventory.control_count(root) == 0:
        # Company-wrapped boards can still be hydrating. One careers site
        # loaded a video embed and reCAPTCHA alongside the Greenhouse iframe;
        # under a multi-tab batch it lost the race and the whole application
        # filled zero fields. Give the slow case a second look
        # before declaring the form empty.
        page.wait_for_timeout(5000)
        root = form_inventory.find_form_root(page, settle_ms=20000)
    if form_inventory.control_count(root) == 0:
        report["required_empty"].append("FORM NEVER LOADED — no controls in any frame")
    capture_audit(root, slug, "pre", url, report, skip=no_audit)
    fill_text_inputs(root, answers, report, custom_text)
    fill_combos(root, city, report, harvested)
    upload_files(root, folder, report, page)
    page.wait_for_timeout(1000)
    # repair pass: React hydration can wipe values filled too early;
    # this refills any text input that came up empty (skips filled ones)
    fill_text_inputs(root, answers, report, custom_text)
    try:
        audit_required(root, report)   # appends; must not clobber earlier entries
    except Exception as exc:  # audit is best-effort; never block the report
        report["required_empty"].append(f"(audit failed: {exc})")
    capture_audit(root, slug, "post", url, report, skip=no_audit, harvested=harvested)
    if shot:
        page.screenshot(path=str(shot), full_page=True)

    report["dom_values"] = root.evaluate(DOM_VALUES_JS)
    return page, report


DOM_VALUES_JS = """() => {
    const out = [];
    document.querySelectorAll('input[type=text], input[type=email], input[type=tel]')
        .forEach(el => {
            if (el.getAttribute('role') === 'combobox') return;
            const lbl = el.id && document.querySelector(`label[for="${el.id}"]`)?.textContent;
            if (lbl) out.push(`${lbl.trim().slice(0, 50)} = ${el.value || '(empty)'}`);
        });
    document.querySelectorAll('[class*="single-value"]').forEach(sv => {
        const wrap = sv.closest('[class*="container"], div');
        const lbl = wrap?.parentElement?.querySelector('label')?.textContent || '(select)';
        out.push(`${lbl.trim().slice(0, 50)} = ${sv.textContent.trim()}`);
    });
    document.querySelectorAll('input[type=file]').forEach(f => {
        out.push(`FILE = ${f.files.length ? f.files[0].name : '(none)'}`);
    });
    return out;
}"""


def print_report(label: str, report: dict) -> None:
    print(f"\n{'=' * 70}\n=== {label}\n{'=' * 70}")
    print("\n--- ACTUAL DOM VALUES ---")
    for line in report.get("dom_values", []):
        print(f"  {line}")
    for section in ("filled", "skipped", "unmapped", "required_empty", "audits"):
        print(f"\n[{section}] ({len(report[section])})")
        for line in report[section]:
            print(f"  - {line}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True, action="append",
                    help="application URL; repeat for batch mode (paired with --folder)")
    ap.add_argument("--folder", required=True, type=Path, action="append",
                    help="per-app folder; repeat once per --url, in the same order")
    ap.add_argument("--city", default=None,
                    help="what to type into location fields; defaults to "
                         "[identity].city in profile/profile.toml")
    ap.add_argument("--no-hold", action="store_true",
                    help="exit after filling instead of holding the browser open")
    ap.add_argument("--shot", type=Path, default=None,
                    help="save a full-page screenshot here after filling")
    ap.add_argument("--slug", default=None, action="append",
                    help="audit slug; defaults to the folder name minus its date prefix")
    ap.add_argument("--no-audit", action="store_true",
                    help="skip the before/after field-inventory capture")
    args = ap.parse_args()

    if len(args.url) != len(args.folder):
        ap.error(f"got {len(args.url)} --url and {len(args.folder)} --folder; "
                 "pass one --folder per --url, in matching order")
    if args.slug and len(args.slug) != len(args.url):
        ap.error("when --slug is given it must be repeated once per --url")
    # A screenshot path is a single file, so it only makes sense for a single app.
    if args.shot and len(args.url) > 1:
        ap.error("--shot takes a single path; omit it in batch mode")

    jobs = list(zip(args.url, args.folder, args.slug or [None] * len(args.url)))

    # A real profile is required before touching a form: it carries the EEO
    # answers and the authorization/sponsorship stance. The example profile's
    # placeholders must never land on an actual application.
    profile = settings.require_profile()
    global COMBO_FIELDS
    COMBO_FIELDS = build_combo_fields(profile)
    city = args.city or profile.get("identity", {}).get("city", "")
    if not city:
        ap.error("no city: pass --city or set [identity].city in profile/profile.toml")

    with sync_playwright() as p:
        # One browser, one tab per application. The user reviews the batch as
        # tabs in a single window, so never launch a browser per app.
        browser = p.chromium.launch(headless=False)
        # ONE context for the whole batch, so every application is a tab in a
        # single window rather than a window of its own.
        context = browser.new_context()
        reports: list[tuple[str, dict]] = []
        for url, folder, slug in jobs:
            label = folder.name
            # Owned out here so a throw mid-fill still reports what landed.
            report: dict = {"filled": [], "skipped": [], "unmapped": [],
                            "required_empty": [], "audits": []}
            try:
                fill_one(context, url, folder, city, slug=slug,
                         no_audit=args.no_audit, shot=args.shot, report=report,
                         profile=profile)
            except Exception as exc:
                # One bad form must not cost the whole batch its filled tabs.
                print(f"\n!!! {label} FAILED: {type(exc).__name__}: {exc}")
                report["required_empty"].append(f"(fill aborted: {type(exc).__name__}: {exc})")
            reports.append((label, report))
            print(f"[{len(reports)}/{len(jobs)}] {len(report['filled'])} fields — {label}")
            sys.stdout.flush()

        for label, report in reports:
            print_report(label, report)

        blockers = sum(len(r["required_empty"]) for _, r in reports)
        print(f"\n{'=' * 70}")
        print(f"{len(reports)} tab(s) filled. NOTHING SUBMITTED.")
        print(f"{blockers} required field(s) still empty across the batch — see above.")
        print("Review every answer in the open window and submit each yourself.")

        if not args.no_audit:
            # Close the loop: grade the manifests this batch just wrote, so
            # every run ends with its own scorecard and improvement backlog.
            # Lazy import — fill_grader imports this module.
            from . import fill_grader
            manifests = sorted(fill_grader.AUDITS_DIR.glob("*.post.json"),
                               key=lambda p: p.stat().st_mtime)[-len(jobs):]
            try:
                for m in manifests:
                    fill_grader.print_report(
                        fill_grader.grade_manifest(m, profile), suggest=True)
                print("\nTurn [no_rule] entries into [[custom_combos]] answers in "
                      "profile/profile.toml, or run /fill-review to do it "
                      "conversationally.")
            except Exception as exc:   # grading must never cost a filled batch
                print(f"(grading skipped: {exc})")
        sys.stdout.flush()

        if not args.no_hold:
            while browser.is_connected():
                time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
