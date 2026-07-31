"""ATS-agnostic form field inventory.

One pass over a form root emits a record per control — label, type, required
flag, current value, and the option list for anything select-like. Captured
before and after a fill, the two manifests diff into a coverage and
rule-compliance report with no screenshot and no model call. The design and the
two grading layers that read this output live in
`.claude/context/form-fill-evals.md`.

Both fill paths call this so their output is comparable: `fill_greenhouse.py`
imports it directly, and the `application-autofiller` subagent runs
`INVENTORY_JS` through `browser_evaluate` for ATSes the deterministic script
does not cover.

Audits carry James's contact details in the `value` column, so
`data/fill_audits/` is gitignored. Promoting a manifest into `tests/fixtures/`
requires `redact()` first — Layer 1 asserts on structure, never on contents.

Usage as a script (captures a blank form, before any fill):
    python -m job_finder.form_inventory --url <application_url> \
        --slug <company>-<role-slug> [--phase pre]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import TimeoutError as PWTimeout
except ImportError:  # the grader reads captured manifests and needs no browser
    PWTimeout = TimeoutError

DEFAULT_AUDIT_DIR =Path(__file__).resolve().parents[2] / "data" / "fill_audits"

# Value markers used by redact(); a fixture keeps the shape and drops the PII.
_REDACT_EMPTY = ""
_REDACT_PRESENT = "<filled>"

# Walks every control under the form root. Returns one record per field.
#
# Option lists: native <select> carries its options in the DOM, so those are
# always captured. react-select renders its menu only while open, so options
# come back null here and are backfilled during the fill by whatever opened the
# menu (see fill_greenhouse.fill_combo). Radio and checkbox groups report their
# sibling labels as options.
INVENTORY_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const text = (n) => clean(n && n.textContent);
  const esc = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : s);

  const labelFor = (el) => {
    if (el.id) {
      const byFor = document.querySelector(`label[for="${esc(el.id)}"]`);
      if (byFor) return text(byFor);
    }
    const ids = el.getAttribute('aria-labelledby');
    if (ids) {
      const joined = ids.split(/\s+/)
        .map((i) => text(document.getElementById(i))).join(' ');
      if (clean(joined)) return clean(joined);
    }
    const aria = clean(el.getAttribute('aria-label'));
    if (aria) return aria;
    const wrap = el.closest('label');
    if (wrap) return text(wrap);
    const group = el.closest('fieldset');
    const legend = group && group.querySelector('legend');
    if (legend) return text(legend);
    return clean(el.getAttribute('placeholder'));
  };

  // Stable enough to join pre/post manifests: id, then name, then a positional
  // path. Positional is last because it drifts when fields are revealed.
  const fieldId = (el) => {
    if (el.id) return `#${el.id}`;
    if (el.name) return `[name=${el.name}]`;
    const tag = el.tagName.toLowerCase();
    const peers = Array.from(document.querySelectorAll(tag));
    return `${tag}:nth(${peers.indexOf(el)})`;
  };

  const isRequired = (el, label) => {
    if (el.required || el.getAttribute('aria-required') === 'true') return true;
    // Greenhouse and Ashby both mark required fields with an asterisk in the
    // label rather than the attribute.
    return /\*\s*$/.test(label) || /\(required\)/i.test(label);
  };

  const selectedOf = (el) => {
    const control = el.closest('[class*="select__control"], [class*="control"]');
    const chosen = control && control.querySelectorAll(
      '[class*="single-value"], [class*="singleValue"], [class*="multi-value"]');
    if (!chosen || !chosen.length) return '';
    return Array.from(chosen).map(text).filter(Boolean).join(', ');
  };

  const out = [];
  const seen = new Set();
  const push = (rec) => {
    if (seen.has(rec.field_id)) return;
    seen.add(rec.field_id);
    out.push(rec);
  };

  const visible = (el) => {
    // react-select mounts a hidden proxy input per combobox purely so native
    // required-validation fires. It mirrors a field already inventoried, and
    // counting it inflates the required-and-blank total.
    if (el.getAttribute('aria-hidden') === 'true') return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    // File inputs are routinely zero-sized behind a styled button.
    if (el.type === 'file') return s.display !== 'none';
    return (r.width > 0 || r.height > 0) && s.visibility !== 'hidden';
  };

  // --- comboboxes (react-select and friends) --------------------------------
  document.querySelectorAll('input[role="combobox"], [role="combobox"]').forEach((el) => {
    if (!visible(el)) return;
    const label = labelFor(el);
    push({
      field_id: fieldId(el),
      label,
      type: 'react-select',
      required: isRequired(el, label),
      value: selectedOf(el),
      options: null,
    });
  });

  // --- native selects -------------------------------------------------------
  document.querySelectorAll('select').forEach((el) => {
    if (!visible(el)) return;
    const label = labelFor(el);
    push({
      field_id: fieldId(el),
      label,
      type: 'select',
      required: isRequired(el, label),
      value: el.selectedIndex >= 0 ? clean(el.options[el.selectedIndex].textContent) : '',
      options: Array.from(el.options).map((o) => clean(o.textContent)).filter(Boolean),
    });
  });

  // --- radio and checkbox groups -------------------------------------------
  const groups = {};
  document.querySelectorAll('input[type=radio], input[type=checkbox]').forEach((el) => {
    if (!visible(el)) return;
    const key = el.name || labelFor(el);
    (groups[key] = groups[key] || []).push(el);
  });
  Object.entries(groups).forEach(([key, els]) => {
    const first = els[0];
    const groupLabel = (() => {
      const fs = first.closest('fieldset');
      const legend = fs && fs.querySelector('legend');
      return legend ? text(legend) : key;
    })();
    const chosen = els.filter((e) => e.checked).map((e) => labelFor(e));
    push({
      field_id: fieldId(first),
      label: groupLabel,
      type: first.type,
      required: els.some((e) => isRequired(e, labelFor(e))),
      value: chosen.join(', '),
      options: els.map((e) => labelFor(e)),
    });
  });

  // --- free text ------------------------------------------------------------
  document.querySelectorAll(
    'input[type=text], input[type=email], input[type=tel], input[type=url],' +
    'input[type=number], input:not([type]), textarea'
  ).forEach((el) => {
    if (!visible(el)) return;
    if (el.getAttribute('role') === 'combobox') return;  // owned by the combo pass
    const label = labelFor(el);
    push({
      field_id: fieldId(el),
      label,
      type: el.tagName.toLowerCase() === 'textarea' ? 'textarea' : 'text',
      required: isRequired(el, label),
      value: el.value || '',
      options: null,
    });
  });

  // --- contenteditable rich-text (Ashby cover-letter boxes) -----------------
  document.querySelectorAll('[contenteditable="true"]').forEach((el) => {
    if (!visible(el)) return;
    const label = labelFor(el);
    push({
      field_id: fieldId(el),
      label,
      type: 'textarea',
      required: isRequired(el, label),
      value: text(el),
      options: null,
    });
  });

  // --- file inputs ----------------------------------------------------------
  document.querySelectorAll('input[type=file]').forEach((el) => {
    if (!visible(el)) return;
    let label = labelFor(el);
    if (!label) {
      const box = el.closest('div[class], fieldset, section');
      label = clean(box && box.textContent).slice(0, 80);
    }
    push({
      field_id: fieldId(el),
      label,
      type: 'file',
      required: isRequired(el, label),
      value: el.files && el.files.length ? el.files[0].name : '',
      options: null,
    });
  });

  return out;
}
"""


CONTROL_SELECTOR = (
    "input:not([type=hidden]), select, textarea, [role='combobox'], [contenteditable='true']"
)


def control_count(root) -> int:
    try:
        return root.evaluate(
            "(sel) => document.querySelectorAll(sel).length", CONTROL_SELECTOR
        )
    except Exception:
        return 0


def find_form_root(page, *, settle_ms: int = 8000):
    """The frame actually holding the application form.

    ATSes embed differently and the same ATS embeds differently per company:
    Greenhouse renders inline on its own job board but inside an iframe when a
    company careers page wraps it, and that wrapper page has zero controls of
    its own. Picking the frame with the most form controls covers every case
    without a per-ATS rule, and degrades to the page itself when nothing loads.
    """
    deadline = settle_ms
    while deadline > 0:
        best, best_count = page, control_count(page)
        for frame in page.frames:
            n = control_count(frame)
            if n > best_count:
                best, best_count = frame, n
        if best_count:
            return best
        page.wait_for_timeout(500)
        deadline -= 500
    return page


def capture(root) -> list[dict[str, Any]]:
    """Run the inventory over a Playwright Page or Frame."""
    return root.evaluate(INVENTORY_JS)


def label_of(el) -> str:
    """Resolve one element's label. Single-element counterpart to the label
    resolution inside INVENTORY_JS, for callers holding a locator."""
    try:
        return (el.get_attribute("aria-label") or _dom_label(el) or "").strip()
    except PWTimeout:
        return ""


def _dom_label(el) -> str:
    return el.evaluate(
        """(node) => {
            const byFor = node.id && document.querySelector(`label[for="${node.id}"]`);
            if (byFor) return byFor.textContent;
            const wrap = node.closest('label');
            if (wrap) return wrap.textContent;
            const labelled = node.getAttribute('aria-labelledby');
            if (labelled) {
                return labelled.split(' ')
                    .map(id => document.getElementById(id)?.textContent || '')
                    .join(' ');
            }
            return '';
        }"""
    )


def has_selection(el) -> bool:
    """Whether a react-select combobox has committed a value. The chosen option
    lives in a sibling single-value div, not in the input's own value."""
    return bool(
        el.evaluate(
            """(node) => {
                const c = node.closest('[class*="select__control"], [class*="control"]');
                return !!c?.querySelector(
                    '[class*="single-value"], [class*="singleValue"], [class*="multi-value"]');
            }"""
        )
    )


def merge_options(inventory: list[dict], harvested: dict[str, list[str]]) -> list[dict]:
    """Backfill react-select option lists gathered while their menus were open.

    Keyed by label rather than field_id because the harvest happens during the
    fill, where the label is what the fill loop already has in hand.
    """
    for field in inventory:
        if field["options"] is None and field["label"] in harvested:
            field["options"] = harvested[field["label"]]
    return inventory


def redact(inventory: list[dict]) -> list[dict]:
    """Strip PII so a manifest can be committed as a CI fixture.

    Keeps everything Layer 1 asserts on — label, type, required, options, and
    whether a value is present — and discards the contents of every value.
    """
    return [
        {**f, "value": _REDACT_PRESENT if f.get("value") else _REDACT_EMPTY}
        for f in inventory
    ]


def audit_path(slug: str, phase: str, *, when: date | None = None,
               base: Path = DEFAULT_AUDIT_DIR) -> Path:
    """data/fill_audits/<date>_<slug>.<phase>.json

    The slug carries company *and* role because two reqs at one company collide
    otherwise — the way both Datadog resumes once rendered to one filename.
    """
    if phase not in ("pre", "post"):
        raise ValueError("phase must be 'pre' or 'post'")
    stamp = (when or date.today()).isoformat()
    return base / f"{stamp}_{slug}.{phase}.json"


def write_audit(inventory: list[dict], *, slug: str, phase: str, url: str,
                when: date | None = None, base: Path = DEFAULT_AUDIT_DIR,
                **meta: Any) -> Path:
    """Write one manifest. Returns the path written."""
    path = audit_path(slug, phase, when=when, base=base)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "slug": slug,
        "phase": phase,
        "url": url,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "field_count": len(inventory),
        **meta,
        "fields": inventory,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture a form field inventory.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--slug", required=True, help="<company>-<role-slug>")
    ap.add_argument("--phase", default="pre", choices=("pre", "post"))
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        root = find_form_root(page)
        inventory = capture(root)
        path = write_audit(inventory, slug=args.slug, phase=args.phase, url=args.url)
        browser.close()

    print(f"{len(inventory)} fields -> {path}")
    required_blank = [f["label"] for f in inventory if f["required"] and not f["value"]]
    print(f"required and blank: {len(required_blank)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
