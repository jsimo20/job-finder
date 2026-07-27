"""Deterministic Greenhouse application autofill.

Fills the standard Greenhouse section (contact, work auth, EEO, uploads) with
plain Playwright — zero LLM tokens. Anything it can't confidently map is left
blank and listed in the printed report. The browser window stays open after
filling so James can review, fill leftovers, and submit by hand.

Usage (single):
    python -m boston_pm_tracker.fill_greenhouse --url <application_url> \
        --folder "<per-app folder>" [--city "Boston"] [--no-hold]

Usage (batch): repeat --url and --folder in matching order. All applications
fill in ONE browser, one tab each, and every tab is left open for review.

    python -m boston_pm_tracker.fill_greenhouse \
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

from playwright.sync_api import Frame, Page, TimeoutError as PWTimeout, sync_playwright

from boston_pm_tracker import form_inventory
from boston_pm_tracker.form_inventory import has_selection, label_of

STEP_TIMEOUT_MS = 10_000

TEXT_FIELDS: list[tuple[str, str]] = [
    # (label regex, answers key) — order matters: "preferred first" before "first"
    (r"preferred\s*(first\s*)?name", "preferred_name"),
    (r"first\s*name", "first_name"),
    (r"last\s*name", "last_name"),
    (r"e-?mail", "email"),
    (r"linked\s*in", "linkedin"),
    (r"website|portfolio|github", "github"),
]

# (label regex, text to type into the react-select filter before Enter).
# Substrings chosen to uniquely match the standard Greenhouse option labels.
COMBO_FIELDS: list[tuple[str, str]] = [
    # authorization first — its label contains the word "country"
    (r"authori[sz]", "no restriction"),
    (r"country", "United States"),
    (r"sponsor", "No"),
    (r"hear about", "Careers Page"),
    (r"gender", "Male"),
    (r"hispanic", "No"),
    (r"race", "White"),
    (r"veteran", "not a protected"),
    (r"disabilit", "no, i do not have"),
    (r"certify", "Yes"),
    (r"privacy|acknowledg", "Yes"),
    (r"pronoun", "He/"),
]

SKIP_PATTERN = re.compile(r"salary|compensation|desired pay|expected pay", re.I)

CITY_PATTERN = re.compile(r"cities.*available|available.*cities", re.I)


def parse_answers(folder: Path) -> dict[str, str]:
    """Pull contact values out of the per-app standard_answers.md."""
    text = (folder / "standard_answers.md").read_text(encoding="utf-8")

    def grab(key: str) -> str:
        m = re.search(rf"\*\*{key}:\*\*\s*\(?([^)\n]+)\)?", text, re.I)
        return m.group(1).strip() if m else ""

    full_name = grab("Full name")
    first, _, last = full_name.partition(" ")
    return {
        "first_name": first,
        "last_name": last,
        "preferred_name": grab("Preferred name") or first,
        "email": grab("Email"),
        "phone": grab("Phone"),
        "linkedin": grab("LinkedIn"),
        "github": grab("GitHub"),
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


def fill_text_inputs(root, answers: dict[str, str], report: dict) -> None:
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
        if el.get_attribute("type") == "tel" or re.search(r"phone", label, re.I):
            el.fill(answers["phone"])
            report["filled"].append(f"{label}: {answers['phone']}")
            continue
        for pattern, key in TEXT_FIELDS:
            if re.search(pattern, label, re.I):
                el.fill(answers[key])
                report["filled"].append(f"{label}: {answers[key]}")
                break
        else:
            report["unmapped"].append(label)


def fill_combo(root, combo, type_text: str, seen_options: list[str] | None = None) -> bool:
    """React-select pattern: open, type to filter, click the matching option.

    Enter alone doesn't commit on Greenhouse's react-select build, so click
    the option element directly, then verify the selection actually landed.
    Returns True only when the selection is confirmed in the DOM.

    react-select renders its menu only while open, so the option list is
    unreachable from a static inventory pass. This is the one moment it is
    visible; `seen_options` collects it for the audit manifest.
    """
    # click doesn't always open the menu (hydration races) — verify and retry
    for _ in range(3):
        combo.click()
        combo.page.wait_for_timeout(300)
        if combo.get_attribute("aria-expanded") == "true":
            break
    else:
        return False

    # Harvest before typing: press_sequentially filters the menu, and a
    # filtered list would misrepresent what the form actually offers. Async
    # lists (city autocomplete) come up empty here and get picked up below.
    if seen_options is not None:
        opened = root.locator("[role='option']")
        for _ in range(4):
            if opened.count():
                break
            combo.page.wait_for_timeout(250)
        for i in range(opened.count()):
            raw = (opened.nth(i).text_content() or "").strip()
            if raw and raw not in seen_options:
                seen_options.append(raw)

    combo.press_sequentially(type_text, delay=20)

    # options can load async (city autocomplete hits an API) — poll up to 3s
    options = root.locator("[role='option']")
    for _ in range(6):
        combo.page.wait_for_timeout(500)
        if options.count():
            break
    want = type_text.lower().strip()
    best = None
    for i in range(options.count()):
        opt = options.nth(i)
        if not opt.is_visible():
            continue
        if seen_options is not None:
            raw = (opt.text_content() or "").strip()
            if raw and raw not in seen_options:
                seen_options.append(raw)
        text = (opt.text_content() or "").lower().strip()
        if text == want:            # exact beats contains ("Male" vs "Female")
            best = opt
            break
        if want in text and best is None:
            best = opt
    if best is not None:
        best.click()
    else:
        combo.press("ArrowDown")
        combo.press("Enter")

    combo.page.wait_for_timeout(200)
    return has_selection(combo)


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
                type_text = city
            else:
                for pattern, candidate in COMBO_FIELDS:
                    if re.search(pattern, label, re.I):
                        type_text = candidate
                        break
                else:
                    done.add(label)
                    report["unmapped"].append(f"{label[:60]} (combobox)")
                    continue
            tries[label] = tries.get(label, 0) + 1
            bucket = harvested.setdefault(label, []) if harvested is not None else None
            try:
                ok = fill_combo(root, el, type_text, bucket)
            except PWTimeout:
                ok = False
            if ok:
                done.add(label)
                report["filled"].append(f"{label[:60]}: {type_text}")
            elif tries[label] >= MAX_TRIES:
                done.add(label)
                report["unmapped"].append(f"{label[:60]} (selection did not commit)")


def upload_files(root, folder: Path, report: dict) -> None:
    resume = next(folder.glob("Sample_User_Resume_*.pdf"), None)
    cover = next(folder.glob("Sample_User_CoverLetter_*.pdf"), None)
    file_inputs = root.locator("input[type='file']")
    unmatched: list[int] = []
    for i in range(file_inputs.count()):
        el = file_inputs.nth(i)
        context = el.evaluate(
            "(node) => (node.closest('div[class], fieldset, section')?.textContent"
            " || '') + ' ' + (node.getAttribute('aria-label') || '')"
        )
        if re.search(r"cover", context, re.I):
            if cover:
                el.set_input_files(str(cover))
                report["filled"].append(f"Cover letter upload: {cover.name}")
        elif re.search(r"resume|cv", context, re.I):
            if resume:
                el.set_input_files(str(resume))
                report["filled"].append(f"Resume upload: {resume.name}")
        else:
            unmatched.append(i)
    # Greenhouse convention when labels aren't reachable: first file input is
    # the resume, second (if present) is the cover letter.
    if unmatched and resume:
        file_inputs.nth(unmatched[0]).set_input_files(str(resume))
        report["filled"].append(f"Resume upload (by position): {resume.name}")
        if len(unmatched) > 1 and cover:
            file_inputs.nth(unmatched[1]).set_input_files(str(cover))
            report["filled"].append(f"Cover letter upload (by position): {cover.name}")


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
    report["required_empty"] = empty


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


def fill_one(browser, url: str, folder: Path, city: str, *,
             slug: str | None = None, no_audit: bool = False,
             shot: Path | None = None) -> tuple[Page, dict]:
    """Fill one application in its own tab. Returns the page and its report.

    The page is deliberately left open; the caller decides when to hold or exit.
    """
    slug = slug or re.sub(r"^\d{4}-\d{2}-\d{2}_", "", folder.name)
    answers = parse_answers(folder)
    report: dict = {"filled": [], "skipped": [], "unmapped": [],
                    "required_empty": [], "audits": []}
    harvested: dict[str, list[str]] = {}

    page = browser.new_page()
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
    capture_audit(root, slug, "pre", url, report, skip=no_audit)
    fill_text_inputs(root, answers, report)
    fill_combos(root, city, report, harvested)
    upload_files(root, folder, report)
    page.wait_for_timeout(1000)
    # repair pass: React hydration can wipe values filled too early;
    # this refills any text input that came up empty (skips filled ones)
    fill_text_inputs(root, answers, report)
    try:
        audit_required(root, report)
    except Exception as exc:  # audit is best-effort; never block the report
        report["required_empty"] = [f"(audit failed: {exc})"]
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
    ap.add_argument("--city", default="Boston")
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

    with sync_playwright() as p:
        # One browser, one tab per application. James reviews the batch as tabs
        # in a single window, so never launch a browser per app.
        browser = p.chromium.launch(headless=False)
        reports: list[tuple[str, dict]] = []
        for url, folder, slug in jobs:
            label = folder.name
            try:
                _, report = fill_one(browser, url, folder, args.city, slug=slug,
                                     no_audit=args.no_audit, shot=args.shot)
            except Exception as exc:
                # One bad form must not cost the whole batch its filled tabs.
                print(f"\n!!! {label} FAILED: {type(exc).__name__}: {exc}")
                reports.append((label, {"filled": [], "skipped": [], "unmapped": [],
                                        "required_empty": [f"(fill failed: {exc})"],
                                        "audits": [], "dom_values": []}))
                continue
            reports.append((label, report))
            print(f"[{len(reports)}/{len(jobs)}] filled {label}")
            sys.stdout.flush()

        for label, report in reports:
            print_report(label, report)

        blockers = sum(len(r["required_empty"]) for _, r in reports)
        print(f"\n{'=' * 70}")
        print(f"{len(reports)} tab(s) filled. NOTHING SUBMITTED.")
        print(f"{blockers} required field(s) still empty across the batch — see above.")
        print("Review every answer in the open window and submit each yourself.")
        sys.stdout.flush()

        if not args.no_hold:
            while browser.is_connected():
                time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
