# Setup

**Cowork users never need this file.** Install the plugin (README) and say
"set me up" in a chat with an empty folder connected; the setup skill does the
rest.

This file holds two things:

- the developer setup for Claude Code, below;
- the profile starting files that `profile_init` writes. The setup skill runs
  it on every install, so they are the defaults every user starts from.

## Developer setup (Claude Code)

Python 3.10 or newer, `git`, and Claude Code.

```sh
git clone https://github.com/jsimo20/job-finder.git && cd job-finder
python -m venv .venv
.venv/Scripts/activate              # .venv/bin/activate outside Windows
pip install uv && uv pip install -e ".[dev]"
python -m pytest -q                 # passes with no profile, config or keys
```

To fill Greenhouse forms with the deterministic script:

```sh
uv pip install -e ".[apply]" && playwright install chromium
```

Set `--output-dir` in `.mcp.json` to this checkout's absolute
`.playwright-mcp` path; the Playwright server rejects uploads from anywhere
else.

Then build the profile, search settings and company list by following
`.claude/skills/job-finder-setup/SKILL.md` from step 2, the same interview
Cowork runs. Run the weekly cycle by saying "run my weekly job search"; it
needs no API key. Changing code, prompts, tests or the plugin: read
`DEVELOPMENT.md`.

## What lives where

Everything personal is gitignored and never committed: `profile/`,
`config/pipeline.toml`, `.env`, `data/` and `digests/`.

| File in `profile/` | Used by | What it drives |
|---|---|---|
| `profile.toml` | everything apply-side | Identity on PDFs, autofill values, EEO defaults, `[paths]` |
| `resume_master.md` | tailoring, fact-checker | Ground truth: every resume claim traces to it |
| `personal_statement.md` | tailoring, fact-checker | The user's voice; letters are checked against its tone |
| `writing-style.md` | drafting, fact-checker, `letter_linter` | Voice rules for anything written as the user |
| `standard_answers.md` | autofill | Contact block and stock screening answers |
| `fit_profile.md` | `digest-triager` | What a great role is, for ranking the digest |
| `qa_checklist.md` | `job_apply.render()` | Checklist written into every `apply.md` |
| `claims_ground_truth.md` | tailoring, fact-checker | Exact metrics, framing rules, skill source pool |
| `story_bank.md` (optional) | drafting, fact-checker | STAR stories; a detail tagged `[confirm]` is never used |
| `generate_resume.py` | `job_apply.render()` | Resume PDF generator; edit only `RESUME_DATA` |
| `CLAUDE.md` | every procedure | The user's own rules, learned from their corrections |
| `corrections.md` | every procedure | Change requests seen once, waiting for a repeat |

With no `[paths]` table every file sits directly in `profile/`. Name a path in
`[paths]` to keep a file elsewhere; relative paths resolve against the repo
root. Nothing outside `profile.toml` may assume a layout: prompts and scripts
resolve paths through `job_apply.load_config()`. `python -m
job_finder.profile_check` exits 0 only when no placeholder remains.

## Profile starting files

`python -m job_finder.profile_init` writes each block below to the file its
first line names, and never overwrites a file that exists. Keep those first
lines intact.

```toml profile/profile.toml
# Edit every value. profile/ is gitignored and holds all of your context: the
# pipeline never reads it and it never lands in git.
#
# The apply tooling refuses to fill a real form until profile/profile.toml
# exists, so placeholders below can never reach an application.

[identity]
name = "Alex Sample"
# One-line positioning shown under your name on the cover letter header.
title_subtitle = "Your Title | Your Positioning Line"
email = "alex.sample@example.com"
phone = "555-555-0100"
linkedin = "https://www.linkedin.com/in/your-handle/"
github = "https://github.com/your-handle"
# What autofill types into "which cities are you available to work in" fields.
city = "Your City"
# Street address for forms that demand a full mailing address. Leave "" to
# fill those by hand.
address = ""

[answers]
# Only when BOTH are true does autofill answer authorization/sponsorship
# questions (as "authorized, no sponsorship needed"). Any other combination
# leaves those questions blank for you — a wrong answer is unrecoverable.
work_authorized = true
requires_sponsorship = false
country = "United States"
# Candidates tried in order against "how did you hear about us" dropdowns.
hear_about = ["Careers Page", "Company Website"]

# Uncomment and fill to have Education sections (School/Degree/Discipline/
# dates) filled on forms that ask. Values are matched against each dropdown's
# option text; years go into plain text inputs.
# Any value may be a list of ordered fallbacks, tried until one matches the
# form's options (useful when a major list lacks your exact discipline).
# [education]
# school = "Your University"
# degree = "Bachelor's Degree"
# discipline = ["Your Major", "Broader Fallback Major"]
# start_month = "September"
# start_year = "2014"
# end_month = "June"
# end_year = "2018"

# Recurring screening dropdowns you want answered automatically. `label` is a
# regex matched against the question text; `candidates` are tried in order
# against the option texts (exact, then whole-word, then substring — an
# ambiguous match is refused and the field is left for you). These run before
# the built-in mappings, so they can override them.
# [[custom_combos]]
# label = 'export.control'
# candidates = ["US Passport or US birth certificate"]

# Same idea for plain text inputs: label regex -> literal value typed in.
# [[custom_text]]
# label = 'zip.{0,10}code|postal code'
# value = "02101"

[eeo]
# Voluntary self-identification defaults. Each value is matched against the
# option text on the form (exact, then whole-word, then substring — ambiguous
# matches are refused). Leave a value "" and autofill will skip that question
# entirely so you can answer it by hand. Any value may also be a list of
# ordered fallbacks, for questions whose phrasing varies between ATSes.
# Typical option phrasings on Greenhouse forms:
#   gender      = "Male" / "Female" / "Decline To Self Identify"
#   transgender = "Yes" / "No" (some vendors ask it as its own question)
#   hispanic    = "Yes" / "No"
#   race        = one of the form's race/ethnicity options
#   veteran     = ["not a protected", "not a veteran"] (covers both common phrasings)
#   disability  = "No, I do not have a disability" (fragment: "no, i do not have")
#   pronouns    = "He/Him" / "She/Her" / "They/Them" (fragment like "He/" works)
gender = ""
transgender = ""
hispanic = ""
race = ""
veteran = ""
disability = ""
pronouns = ""

[letters]
# Optional. When set, every cover letter uses exactly these and letter_linter
# blocks one that does not.
# closing = "Thanks,"
# final_line = "I look forward to talking with you."

[paths]
# All optional. Without overrides, every driving doc is expected inside
# profile/ itself and rendered applications land in profile/applications/.
# Uncomment to keep any of them elsewhere (cloud-synced folders work fine).
# inputs_dir = "~/Documents/job-search/inputs"
# applications_dir = "~/Documents/job-search/applications"
# resume_skill_path = "~/Documents/job-search/generate_resume.py"
# claims_ground_truth_path = "~/Documents/job-search/claims_ground_truth.md"
# writing_style_path = "~/Documents/job-search/writing-style.md"
```

```markdown profile/resume_master.md
# Master resume — ground truth

Everything the tailoring step is allowed to claim lives here. The
fact-checker flags any resume bullet or cover-letter claim it cannot trace to
this file or to personal_statement.md, so write only what you can defend.

## Experience

### Current Company — Your Title (Jan 2023 – present)
- Bullet with the real metric and the real scope.
- Another bullet.

### Previous Company — Your Previous Title (Jun 2020 – Jan 2023)
- ...

## Skills source pool

List every skill the tailoring step may use, grouped however you like.
Anything not listed here gets flagged as invented.

## Education

- Degree, school, dates.

## Certifications / patents / awards

- One line each.
```

```markdown profile/personal_statement.md
# Personal statement — voice sample

Write a page in your own voice about who you are and what you want from the
next role. This is the style model: cover letters are checked against its
tone, and the tailoring step borrows its phrasing. The closer this reads to
how you actually write, the less AI-flavored the output.
```

<details>
<summary><code>profile/writing-style.md</code> (long)</summary>

```markdown profile/writing-style.md
# Writing style

How anything written *as you* should read: cover letters, recruiter emails,
LinkedIn messages. The `materials-fact-checker` reads this whole file and runs
the self-check list at the bottom against every letter; the cover-letter step in
`/job-apply` reads it before drafting. Edit it freely, and make it yours.

Two things to know before you do:

- `.claude/agents/materials-fact-checker.md` cites the rules below by section
  number (§1, §2, §3, §5, §8, §9, §12, §13, §14). Reword any section, but if you
  renumber or delete one, update that prompt too.
- `letter_linter` enforces a fixed subset of this file in code, so removing a
  rule here does not lift it there: no em-dashes, no opening that announces a
  reaction, no feeling verbs, the trope ban list, no sentence that volunteers a
  gap, no paragraph that disowns the text before it ("None of that is why I am
  writing"), and the sign-off and final sentence when `profile.toml`
  `[letters]` sets them.
  Change those in `src/job_finder/letter_linter.py` alongside this file.

The style sample is `personal_statement.md`: when a draft does not sound like
you, that file is the reference, not this one.

---

## Universal rules

### 1. No em-dashes, ever

`—` is banned in any prose written as you. Its presence is the single loudest
tell that a machine wrote the text. Use periods, commas, semicolons, colons, or
parentheses; rewrite the sentence if you have to.

### 2. No AI tropes

Non-exhaustive ban list. Add your own as you catch them.

- "uniquely positioned"
- "spearhead" / "leverage" (as a verb, unless literally financial) / "delve"
- "navigate the landscape" / "cutting-edge" / "robust" / "comprehensive" / "seamless"
- "at the intersection of X and Y"
- "passionate about"
- "would love to connect" / "would love the opportunity to"
- "excited to explore"
- "hope this finds you well"
- "worth saying up front" (any "worth saying/naming/noting up front" variant)
- "mostly" (a hedge adverb; cut it or commit to the statement)
- Triadic lists built for rhythm, not substance (three items where two would do)
- "Label: explanation" sentence stubs in prose (for example, "The goal: ...").
  Write the sentence. Keep the label-and-colon form only inside a table.

### 3. No punchy confidence statements

Short standalone sentences that close a paragraph with rhetorical conviction
read as machine-written. Never write lines like:

- "That's the trade I want to make."
- "That's exactly the kind of work I want to do."
- "The math is simple."
- "The rest writes itself."
- Any one-sentence paragraph engineered to hit hard

Trust the prior sentence to carry the point, or let the paragraph end quieter
than you want it to.

### 4. No melodrama, no overstatement

Do not dramatize stakes or inflate what happened. Understate slightly; when a
claim can go two ways, pick the smaller one. Never round numbers up. Never
present a projection as a delivered outcome, or a role responsibility as a
shipped result. If the work is in a pilot, say pilot. If a metric is modeled,
say modeled.

### 5. No self-grading

Never write "I think my experience makes me a great fit" or any variant. Show
the fit with one specific detail and let the reader draw the conclusion.

### 6. Specificity beats abstraction

"Jira automation, status emails, and customer-context summaries" beats
"AI workflows across the business." Every abstract framing earns its place by
pointing at one concrete example immediately.

### 7. Slight imperfection beats polish

Machines over-optimize prose; people do not. Prefer one example over three,
uneven sentence lengths, the occasional flat sentence, and plain words like
"basically" or "honestly" where they fit.

### 8. Show the work; do not claim the match

Never assert that your experience maps to what the reader needs. State what
you did and let them draw the connection. Any sentence that editorializes the
overlap between your background and their need is the tell.

**Before (claims the match):**
> Your platform role is close to the exact problem I have been working on.

**After (shows the work):**
> For the last two years I have owned the developer console at my current
> company, including the first-run experience for new accounts.

The "After" never says "this fits you." It states one thing you did and trusts
the reader to see why it matters.

### 9. Plain words over writerly ones

Reach for the ordinary word, not the clever one. Metaphor-nouns dropped in to
sound sharp ("a role exactly this shape", "the surface I want to work on",
"the layer that matters") are polish that reads as generated. If a plainer word
says the same thing, use it.

### 10. State risks and tradeoffs plainly; keep the fix out of the risk

Name the exposure and stop. Do not staple the mitigation onto the same
sentence; if the fix matters, it belongs where the work is described.

**Before:** "Adding a validation pass adds latency; keep it a lightweight
lookup and hold a p95 budget so the slower path is not abandoned."
**After:** "Adding a validation pass adds latency, and a slower path may be
abandoned."

### 11. Review for stereotypical bias before presenting

Before presenting any persona, segment, or example, check whether a trait
(competence, need, newcomer status) is being tied to a demographic group. A
correlation such as "fast-growing segment" is not a characteristic such as
"new to the activity." When unsure, remove the demographic framing; the point
almost always stands without it.

### 12. Paragraphs move in one line; sentences connect

Concision is not compression. A paragraph squeezed until every sentence is a
self-contained fact reads as a list wearing sentence clothes.

The test: if the sentences can be reordered without losing anything, the
paragraph is not written yet. Each one should pick up something from the one
before it, so the paragraph arrives somewhere it could not have started.

- One paragraph, one idea, developed. Not four facts bundled by topic.
- Set up before you land: the concrete scene runs first and the observation
  comes out of it, never the reverse.
- Keep the connective words ("which is what", "it wasn't until"). Cut a whole
  fact instead of cutting the joins.
- Short sentences are beats, not the default. One lands inside a flowing
  paragraph; five in a row is a list.

**Before** (four facts, no joins):
> We moved to Farport in June for my partner's new job. My employer does not
> support remote work. Our dog had no opinion on it. Outside work I ski and
> cycle.

**After**:
> We moved to Farport in June for my partner's new job, and our dog came with
> us. My employer does not support remote work, which is what started my
> search. The move did not change the part of the job I actually like, which is
> being close enough to the product to argue about it.

At the sentence level, four failures account for most of it:

- You do the verb, not an abstraction. "What is left of the week goes to skis"
  makes the week the actor; "what is left of the week I spend skiing" does not.
- Every short aside needs a referent in the sentence before it. When an aside
  lands wrong, check what its pronoun now points at.
- No summary phrases standing in for a fact: "so the decision made itself",
  "that was enough". Cut them; do not replace them.
- Do not assert a trait about yourself ("I cannot leave a new tool alone").
  Name the thing you did, or cut the claim.

Chaining clauses with "and / so / though / which" is accumulation, not
transition. A real transition sets up a turn, and it usually starts a new
sentence.

### 13. No trailing gloss

A clause tacked onto the end of a sentence that restates what was just said in
more abstract terms, usually opening "which is", "which means", "meaning", or
"that is". **The test: delete the tail. If no fact is lost, it was a gloss.**

Cut:
> The console has to earn trust before anyone has an account, ~~which is a
> harder place to earn it.~~

Keep a relative clause that carries a fact the sentence did not already have:
> My employer does not support remote work, which is what started my search.

### 14. Every paragraph opens on the one before it

Four paragraphs are one argument, not four exhibits. Open with what the reader
already has and close on what is new. **The diagnostic: read only the first
sentence of each paragraph, in order. If they do not chain, there are no
transitions.**

Three ways to make the link, strongest first:

- Reinterpret the previous paragraph as the premise for this one.
- Name it, with a plain pronoun or noun phrase, before introducing anything.
- Follow the consequence: "Getting to work on any of that means leaving my
  current role."

Never open a paragraph on a fresh topic with no backward reference.

---

## Voice mode (writing as you)

### Stay in first person

Write as yourself, with yourself as the subject. "I" is the default, including
as the first word of a paragraph. Openers handed to an abstraction or a
demonstrative pronoun are the failure to watch for. Vary the openers among
first-person shapes ("I taught myself...", "My first move was...", "Following
my time at <previous employer>, I...") rather than away from first person.

### One number does the heavy lifting

Pick the single strongest metric and let it stand alone. Stat-stacking reads
as a resume pasted into prose.

### Undersell the ask

One plain, low-pressure line, then stop. "If you're open to a short
conversation, let me know." No stacked hedge, no thank-you trailer.

### Writing the opening

Open on yourself, at your current employer, with a quantified claim about the
thing the posting is about:

> At [employer], [a proportion] of my job involved [the posting's subject]
> across [scope].

The reader knows who is writing, where, and how much of your work maps to the
role before they have to work it out. Then "Specifically," and the mechanism:
what you handled (standards or tools in parentheses), the detail that proves
you did it yourself, then one figure.

- **Three paragraphs.** What you own that matches the posting, a second body of
  work, then everything else (patents, certificates, the move) and the close.
- **You do the verb.** "I handled", "I launched". Never "the platform was
  separate work".
- **Say why you are leaving, and keep it positive.** Without it the reader
  supplies their own reason.

A contrast opening (how the category usually works, then how this product
differs) is still available when the product genuinely does something unusual.
It is never the default and never worth delaying your first sentence for.

Two ways this goes wrong. **Opening on your reaction** ("your posting caught my
attention", "I came across", "I'm reaching out because") announces that you
noticed something instead of saying the thing. **Naming the feeling**: any
sentence whose main verb is "excited", "passionate", "thrilled" or "drawn to".
The specificity carries the enthusiasm; the word never does.

**Test: could this opening be pasted into a letter for a different posting? If
yes, it is not about this role's subject yet.**

### Closing

- End the final paragraph on a plain, forward-looking sentence, not a curiosity
  question; across a stack of letters the constructed question is the tell. To
  use the same final sentence every time, set `[letters] final_line` in
  `profile.toml` and the linter enforces it verbatim.
- Never name a gap. No sentence whose content is the absence of experience:
  not a domain that is not your background, not a requirement you miss, not a
  part of the role you would be learning. The reader has the resume and the
  posting and will find the delta themselves. Put the next strongest piece of
  real work in the slot instead. This bans volunteering the gap, not accuracy:
  a direct question on a form still gets a direct answer, and nothing may imply
  experience you do not have.
- Let paragraphs end flat, on the limitation. "It is still in pilot, so there
  are no results to point at yet." Resist adding "but the early signal is
  strong."
- Describe the mechanism, not the achievement. Explaining how the thing works
  proves depth with no adjectives.
- Split numbers across sentences. Three figures in one sentence reads as
  resume regurgitation.
- Logistics as a human line, never a selling point.
- First person singular. Work you directed is "I", even when the source says
  "we" about the team.
- One sign-off for every letter. Set `[letters] closing` in `profile.toml` to
  have the linter enforce it.

---

## Self-check before sending prose written as you

1. Any em-dashes? Remove.
2. Any AI trope from §2, including a "Label: ..." colon stub? Rewrite.
3. Any punchy confidence line from §3? Cut.
4. Any melodrama or overstatement from §4? Dial back.
5. Any self-grading (§5)? Rewrite.
6. Any sentence that claims the match instead of showing the work (§8)?
   Replace with a concrete example.
7. Any writerly metaphor-noun where a plain word works (§9)? Swap it back.
8. Do the risks state exposure plainly, with no mitigation attached (§10)?
9. Bias pass: does any persona, segment, or example tie a trait to a
   demographic group (§11)? Remove or rewrite.
10. Can any paragraph's sentences be reordered without loss (§12)? Write the
    connections back in.
11. Does any sentence chain clauses, put an abstraction in the subject, or
    leave a pronoun pointing at the wrong noun (§12, sentence level)?
12. Any trailing gloss (§13)? Delete the tail and check whether a fact was lost.
13. Do the first sentences of the paragraphs chain when read alone (§14)?
14. Cover letters: does the opening name their product rather than the posting?
    Does the letter end on the fixed closing line, verbatim, with no curiosity
    question near it?
15. Is the ask one plain, low-pressure line?
16. Would this fit as a LinkedIn growth-hack post? If yes, rewrite.
17. Would you actually type this? If no, rewrite.

## When feedback says "sounds AI-generated"

The fix is almost never more personality words. It is usually:

- Delete a triad, keep the strongest single detail
- Cut a polished transitional phrase, let the sentences bump
- Cut a punchy resolution line, let the paragraph end quieter
- Replace abstract framing with a concrete example
- Undersell where you were selling
```

</details>

```markdown profile/standard_answers.md
# Standard application answers

Copied into every per-application folder by `job_apply.render()`. The
deterministic Greenhouse filler and the autofill agent both read it. Keep the
`**Key:** value` format for the contact block — the filler parses it with that
exact shape (any value here overrides `profile.toml [identity]`).

## Contact

- **Full name:** Alex Sample
- **Preferred name:** Alex
- **Email:** alex.sample@example.com
- **Phone:** 555-555-0100
- **LinkedIn:** https://www.linkedin.com/in/your-handle/
- **GitHub:** https://github.com/your-handle
- **Location:** Your City, ST
- **Address:** 123 Example St, Your City ST 00000

## Work authorization

- Authorized to work in the US: Yes
- Require visa sponsorship now or in the future: No

## Common screening questions

Add your stock answers here — the autofill agent quotes them verbatim when a
form asks. Examples of questions worth pre-answering:

- How did you hear about this role? Company careers page.
- Willing to work hybrid/onsite: (your answer)
- Earliest start date: (your answer)

## Never answered automatically

Salary and compensation fields are always left blank, whatever a form says.
Legal questions (non-competes, prior agreements, export control) are always
left for you.
```

```markdown profile/fit_profile.md
# Fit profile

Read by the `digest-triager` agent when ranking digest roles. Describe what a
great role looks like for you, in ranked buckets. Be concrete — the triager
applies these signals mechanically on top of the digest's numeric score.

## Strong positive — surface aggressively

- (domains, levels, locations, or company types you actively want)
- (e.g. "AI/LLM platform roles at Series B-D companies")
- (e.g. "Comp floor at or above $X")

## Mild positive

- (adjacencies that match your background story)

## Mild negative — deprioritize but don't drop

- (things you'd accept reluctantly: a less-preferred metro, lower comp band)

## Strong negative — drop unless the score is overwhelming

- (dealbreakers: out-of-country, comp below your floor, seniority mismatches)
```

<details>
<summary><code>profile/generate_resume.py</code> (long)</summary>

```python profile/generate_resume.py
"""
Canonical resume generator. Edit ONLY the RESUME_DATA dict below with your
own history. Never modify styles, layout, or spacing
constants; job_apply.render() swaps the RESUME_DATA block per application and
relies on the two block markers staying exactly as they are.
"""

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)

# ---------- DESIGN TOKENS (LOCKED — DO NOT EDIT) ----------
NAVY = HexColor("#1B2A4A")
CHARCOAL = HexColor("#2D3436")
ACCENT = HexColor("#2C5F8A")
LIGHT = HexColor("#A3BAC3")

# ---------- RESUME DATA (EDIT ONLY THIS BLOCK) ----------
RESUME_DATA = {
    "name": "Alex Sample",
    "title": "Your Title  |  Your Positioning Line",
    "contact": '<font color="#2C5F8A">555-555-0100</font>  |  <a href="mailto:alex.sample@example.com" color="#2C5F8A">alex.sample@example.com</a>  |  <a href="https://www.linkedin.com/in/your-handle/" color="#2C5F8A">LinkedIn</a>',

    "experience": [
        {
            "company": "Current Company",
            "role": "Your Title",
            "dates": "JAN 2023 – PRESENT",
            "bullets": [
                "One outcome-focused bullet with a concrete metric you can defend in an interview.",
                "Another bullet: what you built or decided, and what changed because of it.",
            ],
        },
        {
            "company": "Previous Company",
            "role": "Your Previous Title",
            "dates": "JUN 2020 – JAN 2023",
            "bullets": [
                "Keep bullets outcome-first and traceable to your resume_master.md.",
            ],
        },
    ],

    "skills": [
        ("Category One", "comma-separated skills that appear in your master resume"),
        ("Category Two", "keep categories few and honest"),
        ("Category Three", "tools and methods you actually use"),
        ("Category Four", "no skills you could not discuss in an interview"),
    ],

    "education": {
        "degree": "Bachelor of Science — Your Major",
        "minor": "Minor: Your Minor",
        "school": "Your University",
        "dates": "SEP 2014 – JUN 2018",
    },

    "certifications": [
        "Certifications, patents, or awards worth a line each",
    ],
}

# ---------- STYLES (LOCKED) ----------
styles = {
    "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=18,
                           textColor=NAVY, alignment=TA_CENTER, leading=20, spaceAfter=1),
    "title": ParagraphStyle("title", fontName="Helvetica", fontSize=10,
                            textColor=ACCENT, alignment=TA_CENTER, leading=12,
                            spaceBefore=7, spaceAfter=1),
    "contact": ParagraphStyle("contact", fontName="Helvetica", fontSize=8.5,
                              textColor=CHARCOAL, alignment=TA_CENTER, leading=11, spaceAfter=4),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11,
                              textColor=NAVY, alignment=TA_LEFT, leading=13,
                              spaceBefore=7, spaceAfter=2),
    "role_left": ParagraphStyle("role_left", fontName="Helvetica-Bold", fontSize=9,
                                textColor=CHARCOAL, alignment=TA_LEFT, leading=11),
    "role_right": ParagraphStyle("role_right", fontName="Helvetica", fontSize=8.5,
                                 textColor=LIGHT, alignment=TA_RIGHT, leading=11),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=8.5,
                             textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                             leftIndent=8, firstLineIndent=-8, spaceAfter=2),
    "skill_cat": ParagraphStyle("skill_cat", fontName="Helvetica-Bold", fontSize=9,
                                textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                                spaceBefore=7, spaceAfter=2),
    "skill_body": ParagraphStyle("skill_body", fontName="Helvetica", fontSize=8.5,
                                 textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                                 leftIndent=8, firstLineIndent=-8, spaceAfter=2),
    "edu_body": ParagraphStyle("edu_body", fontName="Helvetica", fontSize=8.5,
                               textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                               leftIndent=8, firstLineIndent=-8, spaceAfter=2),
    "cert_body": ParagraphStyle("cert_body", fontName="Helvetica", fontSize=8.5,
                                textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                                leftIndent=8, firstLineIndent=-8, spaceAfter=2),
}


def make_company_row(company, role, dates, first=False):
    """Two-col table for role/dates with hAlign='LEFT' to prevent phantom indent."""
    left = Paragraph(f"<b>{company}</b> &nbsp;|&nbsp; {role}", styles["role_left"])
    right = Paragraph(dates, styles["role_right"])
    t = Table([[left, right]], colWidths=[4.9 * inch, 2.3 * inch])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    t.hAlign = "LEFT"
    t.spaceBefore = 7
    return t


def build_story():
    s = []
    # Header
    s.append(Paragraph(RESUME_DATA["name"], styles["name"]))
    s.append(Paragraph(RESUME_DATA["title"], styles["title"]))
    s.append(Paragraph(RESUME_DATA["contact"], styles["contact"]))

    # Experience
    s.append(Paragraph("EXPERIENCE", styles["section"]))
    for i, job in enumerate(RESUME_DATA["experience"]):
        s.append(make_company_row(job["company"], job["role"], job["dates"], first=(i == 0)))
        for b in job["bullets"]:
            s.append(Paragraph(f"&bull;&nbsp;&nbsp;{b}", styles["bullet"]))

    # Skills
    s.append(Paragraph("SKILLS", styles["section"]))
    for cat, body in RESUME_DATA["skills"]:
        s.append(Paragraph(cat, styles["skill_cat"]))
        s.append(Paragraph(f"&bull;&nbsp;&nbsp;{body}", styles["skill_body"]))

    # Education
    s.append(Paragraph("EDUCATION", styles["section"]))
    edu = RESUME_DATA["education"]
    s.append(make_company_row(edu["school"], edu["degree"], edu["dates"], first=True))
    s.append(Paragraph(f"&bull;&nbsp;&nbsp;{edu['minor']}", styles["edu_body"]))

    # Certifications
    s.append(Paragraph("CERTIFICATIONS &amp; PATENTS", styles["section"]))
    s.append(Spacer(1, 5))
    for c in RESUME_DATA["certifications"]:
        s.append(Paragraph(f"&bull;&nbsp;&nbsp;{c}", styles["cert_body"]))

    return s


def build_pdf(path):
    doc = SimpleDocTemplate(
        path,
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=f"{RESUME_DATA['name']} — Resume",
        author=RESUME_DATA["name"],
        subject="Resume",
        creator=RESUME_DATA["name"],
    )
    doc.build(build_story())


if __name__ == "__main__":
    out = "resume.pdf"
    build_pdf(out)
    print(f"Built: {out}")
```

</details>

```markdown profile/qa_checklist.md
- [ ] Single page?
- [ ] All bullet dots at same x?
- [ ] No "orphan" wrapped word you can eliminate by tightening?
- [ ] Hyperlinks render in accent blue?
- [ ] Every metric traceable to resume_master.md?
- [ ] PDF metadata set (title, author, subject, creator)?
- [ ] (add your own fact-specific checks: metric baselines, framings to avoid,
      claims that must stay qualified)
```

```markdown profile/CLAUDE.md
# My rules

How I want the agent to work and write. The agent adds a line when I ask for
the same change twice, or when I tell it a rule directly, and prunes this file
each time. Edit it freely.
```

```markdown profile/corrections.md
# Corrections seen once

Change requests made one time. A second request of the same kind becomes a rule
in CLAUDE.md and its line here is deleted.
```

```markdown profile/claims_ground_truth.md
# Anti-overstatement rules

Rules the tailoring step must follow about YOUR facts. List every claim that
tends to drift when an LLM rewrites it, with the framing that must be kept.

Examples of the kind of rule that belongs here:

- Project X is in pilot, not shipped — always "Phase 1" / "business case
  projects", never "delivered".
- Metric Y is modeled, not measured — say so.
- Never claim credit for Z; it belongs to another team.
```
