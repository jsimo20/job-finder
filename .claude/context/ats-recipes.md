# ATS Form Recipes

Known field layouts per ATS. The autofiller reads this before navigating so it can batch-fill after one snapshot instead of rediscovering the layout interactively.

Each recipe lists: direct URL pattern, known fields in fill order, EEO section notes, and upload field names. Recipes are derived from verified runs — update this file when a new ATS variation is encountered.

---

## Greenhouse

**Direct URL pattern:** `https://job-boards.greenhouse.io/<company>/jobs/<gh_jid>`

Always use the direct Greenhouse URL. Never navigate via a company careers portal (e.g., `careers.datadoghq.com`) — the portal adds a click-through that costs extra snapshots for no gain. When the dispatching prompt supplies a `gh_jid` param or the `application_url` contains `gh_jid=<id>`, derive the direct URL as:
`https://job-boards.greenhouse.io/<company_slug>/jobs/<gh_jid>`

**Known fields (fill order):**

1. First Name *(text)*
2. Last Name *(text)*
3. Email *(text)*
4. Phone — country code dropdown (select "United States +1") then phone number text field
5. LinkedIn Profile *(text)* — label varies: "LinkedIn Profile", "LinkedIn URL", "LinkedIn"
6. Website *(text)* — use GitHub URL (`https://github.com/jsimo20`)
7. Resume/CV — file upload button (label: "Attach", "Resume/CV", "Upload resume")
8. Cover Letter — separate file upload (label: "Attach", "Cover Letter") — present on most Greenhouse forms; absent on some minimal ones
9. "How did you hear about this opportunity" — react-select dropdown; pick the careers-page option
10. Location / "In what cities are you available to work?" — multi-select or text; type city name and select
11. Work authorization radio — "Yes, no restriction" or "Yes, I am authorized"
12. Visa sponsorship radio — "No"
13. Privacy/certification acknowledgment checkboxes — check all required
14. EEO section — see EEO notes below

**EEO notes (Greenhouse standard):**
- Gender → Male
- Hispanic or Latino → No
- Race — **conditional field**: appears only after Hispanic/Latino is answered. After clicking No on Hispanic/Latino, take one targeted snapshot of the EEO section to catch whether Race appeared. Race → White.
- Veteran status → "I am not a protected veteran"
- Disability → "No, I do not have a disability and have not had one in the past"

**Snapshot strategy:**
1. One full-page snapshot after navigate — map all visible fields.
2. One targeted snapshot per react-select before clicking option (to get option refs). With ~10 dropdowns on a full form this alone accounts for 10-15 snapshots — it's unavoidable with react-select; don't add extra ones.
3. One targeted snapshot of EEO section after Hispanic/Latino answer (Race conditional).
4. One final targeted snapshot on any section that showed an error or unexpected state.
Total realistic range: 15–25 snapshots for a full Greenhouse form (many react-select dropdowns). The ≤7 budget in old versions of this file was wrong — do not aim for it.

**Known variations:**
- Some Greenhouse forms omit the Cover Letter upload (Maven AGI, Datadog portal forms).
- "In what cities are you available to work?" is a multi-select; type the city name, wait for autocomplete, click the match.
- The phone field is two parts: a country-code react-select + a separate text input. Fill in order.
- "I certify that all information provided is true" checkbox — required; check it.

**Portal exceptions (direct URL rule does NOT apply):**
- **Datadog** (`careers.datadoghq.com`): `job-boards.greenhouse.io/datadoghq/jobs/<id>` returns 404. Use the careers portal URL directly — the Greenhouse iframe loads inside the portal page with no extra click needed after navigating to the portal URL.

---

## Ashby

**Direct URL pattern:** `https://jobs.ashbyhq.com/<company>/<uuid>`

URLs are already direct — no portal wrapping.

**Known fields (fill order):**

1. Name — may be a single "Full Name" field or split First/Last
2. Email *(text)*
3. Phone *(text)*
4. LinkedIn *(text)* — label: "LinkedIn Profile", "LinkedIn URL"
5. Location — text or dropdown; type "Boston, Massachusetts, United States" or select
6. Resume — file upload (label: "Upload resume", "Attach resume")
7. Cover Letter upload — **absent on most Ashby forms** (Maven AGI, Cyvl both lacked it); do not spend snapshots searching
8. Work authorization radio (if present) — "Yes"
9. Sponsorship radio (if present) — "No"
10. Office attendance / onsite radio (if present) — answer from standard_answers per-app copy
11. Short-answer questions (if present) — leave blank and flag if no draft provided

**EEO notes:**
Most Ashby forms do not have EEO sections. If one appears, apply the same defaults as Greenhouse.

**Snapshot strategy:**
1. One full-page snapshot after navigate — map all fields.
2. One targeted snapshot per react-select that needs option discovery.
Total target: 2–4 snapshots for a standard Ashby form.

**Known variations:**
- Cyvl had two required short-answer questions (3–5 sentences each); these need Opus drafts, not autofill.
- Maven AGI was 5 fields total — minimal form.

---

## Adding a new ATS

When you encounter an ATS not listed here, proceed with the standard snapshot-and-discover flow. After the run completes, note the ATS name, URL pattern, field list, and any gotchas in your report — the main conversation will update this file.

---

*Last verified: 2026-07-06 (Greenhouse: Starburst jobs/5252943008, Datadog jobs/7974481, jobs/7763117; Ashby: Maven AGI bbcd2fd7, Cyvl 2c32d055)*
