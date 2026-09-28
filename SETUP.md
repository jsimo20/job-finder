# Setup — new user

Step-by-step setup for a fresh clone. Written so you can paste it into a
Claude Code session ("follow SETUP.md") and have it drive; every step also
works by hand. Nothing here requires the original owner's files, and the repo
carries no personal data at all: everything personal lives in three gitignored
places you create yourself — `config/pipeline.toml` (search preferences),
`profile/` (identity), and `data/state.db` (companies, ledgers, digest
archive). The pipeline runs locally on a weekly schedule; there is no cloud
pipeline to configure.

## 0. Prerequisites

- Python 3.10 or newer (on Debian/Ubuntu also `python3-venv`; the stock
  interpreter there cannot create a virtualenv)
- `git`, and the `gh` CLI logged into your GitHub account
- `uv` (`pip install uv`) — or plain pip, adjusting the commands below
- An Anthropic API key with credit (console.anthropic.com) — the pipeline's
  extraction stage bills against it
- A Gmail account with 2FA, for the digest email
- A Windows machine that's usually on (the weekly run is a Scheduled Task;
  on macOS/Linux use cron/launchd with the same command)

If a Claude Code session is driving this setup, four things still need a
human first — everything else it can do from this document:

1. Installing Claude Code itself (plus Python/git/gh above)
2. Access to this repo (a collaborator invite, or a copy from whoever
   handed it to you)
3. Creating the Anthropic API key and adding billing
4. Generating the Gmail app password (§2) — never paste it into chat;
   put it straight into `.env` yourself

## 1. Get a copy

```sh
git clone <repo-url> my-job-finder && cd my-job-finder
git remote set-url origin git@github.com:<your-user>/my-job-finder.git
gh repo create <your-user>/my-job-finder --private --source=. --push
```

Nothing to reset: the repo contains no one's search state. Everything
personal is created locally in the steps below and never committed.

## 2. Install

```sh
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install uv
uv pip install -e ".[dev]"
```

The browser-autofill workflow (optional, local-only):

```sh
uv pip install -e ".[apply]"
playwright install chromium
```

The Playwright MCP server accepts file uploads only from its `--output-dir` and
its cwd, so that argument has to be **this clone's** `.playwright-mcp` folder as
an absolute path; a wrong one rejects every resume as "outside allowed roots".
Set it in `.mcp.json` (Claude Code) and, if you will use Cowork, in
`cowork-plugin/.mcp.json` as well before building the plugin (§8).

Sanity check — the suite must pass on a fresh clone with no profile:

```sh
python -m pytest -q
```

Create a `.env` at the repo root — the pipeline and the digest email read
it (plain key=value, three lines):

```
ANTHROPIC_API_KEY=sk-ant-...
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
```

`GMAIL_APP_PASSWORD` is a 16-char app password from
myaccount.google.com/apppasswords (requires 2FA). `GMAIL_USER` is both the
sender and the recipient of the digest.

## 3. Create your profile

`profile/` is gitignored and holds everything personal: identity, EEO answers,
your master resume, your writing voice. Its starting files are the blocks at the
end of this section. Write them all at once:

```sh
python -m job_finder.profile_init
```

That creates `profile/` with every file below and never overwrites one that
already exists. Copying each block by hand works too. Every file starts with
example values, so edit them in this order:

1. **`profile/profile.toml`** — your name, email, phone, links, city;
   work-authorization stance; EEO defaults (leave `""` for any question you
   want to answer by hand on every form). Optionally point `[paths]` at
   folders outside the repo.
2. **`profile/resume_master.md`** — your real history. This is ground truth:
   the fact-checker flags anything in a draft that doesn't trace to it, so
   write only what you can defend in an interview.
3. **`profile/personal_statement.md`** — a page in your own voice.
4. **`profile/writing-style.md`** — the voice rules for anything written as
   you. The fact-checker reads all of it and runs its self-check list against
   every letter; `letter_linter` enforces a fixed subset in code (no em-dashes,
   no paragraph opening on "I", the closing "Thanks," and the fixed final
   sentence), so keep those or change the linter with them. The default is
   usable as-is; make it yours over time.
5. **`profile/standard_answers.md`** — contact block + stock screening answers.
6. **`profile/fit_profile.md`** — what a great role looks like for you.
7. **`profile/generate_resume.py`** — edit only the RESUME_DATA block.
8. **`profile/qa_checklist.md`** and **`profile/claims_ground_truth.md`** — grow
   these over time; the defaults work on day one.

| File | Used by | What it drives |
|---|---|---|
| `profile.toml` | everything apply-side | Identity on PDFs, autofill contact values, EEO defaults, paths |
| `resume_master.md` | tailoring, fact-checker | Ground truth: every resume bullet must trace to it |
| `personal_statement.md` | tailoring, fact-checker | Your narrative voice; cover letters are checked against its tone |
| `writing-style.md` | cover-letter drafting, fact-checker, `letter_linter` | The voice rules for anything written as you |
| `standard_answers.md` | form autofill, autofill agent | Contact block plus stock answers to common screening questions |
| `fit_profile.md` | digest-triager agent | What a great role is for you, so triage can rank the digest |
| `qa_checklist.md` | `job_apply.render()` | Per-application checklist written into every apply.md |
| `claims_ground_truth.md` | tailoring | Per-claim framing rules and metrics the drafter must not inflate |
| `story_bank.md` (optional, no starting block) | drafting, fact-checker, free-text answers | STAR stories from past interviews; untagged details count as ground truth, and a detail tagged `[confirm]` is never used until you confirm it |
| `generate_resume.py` | `job_apply.render()` | Resume PDF generator |

EEO values are voluntary; an empty value is always left for you to answer.

Every path above is where the tooling looks when `profile.toml` has no
`[paths]` table. Keep any of them elsewhere by naming it there
(`inputs_dir`, `writing_style_path`, `claims_ground_truth_path`,
`resume_skill_path`); relative paths resolve against the repo root. Nothing
outside `profile.toml` may assume a layout, so the Claude-side prompts resolve
these paths through `job_apply.load_config()` rather than naming them.

**Do not skip 2–5.** The tailoring, fact-checking, and autofill workflows all
read those files; with placeholders still in them you'd be submitting
applications carrying example data. When you think you're done, prove it:

```sh
python -m job_finder.profile_check
```

It flags every placeholder value and missing driving doc, and exits non-zero
until your profile is real. Run it again any time; the apply workflow assumes
it passes.

`profile/` is gitignored. Verify before your first push:

```sh
git check-ignore profile/ && git status --short
```

### The starting files

`profile_init` reads the blocks below, so each block's first line names the
file it becomes. Keep that line intact if you edit them.

```toml profile/profile.toml
# Edit every value. profile/ is gitignored and holds all of your context: the
# pipeline never reads it and it never lands in git.
#
# The apply tooling refuses to fill a real form until profile/profile.toml
# exists, so placeholders below can never reach an application.

[identity]
name = "Alex Sample"
# One-line positioning shown under your name on the cover letter header.
title_subtitle = "Senior Product Manager | Your Positioning Line"
email = "alex.sample@example.com"
phone = "555-555-0100"
linkedin = "https://www.linkedin.com/in/your-handle/"
github = "https://github.com/your-handle"
# What autofill types into "which cities are you available to work in" fields.
city = "Boston"
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

### Current Company — Senior Product Manager (Jan 2023 – present)
- Bullet with the real metric and the real scope.
- Another bullet.

### Previous Company — Product Manager (Jun 2020 – Jan 2023)
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
  rule here does not lift it there: no em-dashes, no paragraph opening on "I",
  no opening that announces a reaction, no feeling verbs, the trope ban list,
  the closing "Thanks," and the fixed final sentence in the Voice mode section.
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

### Never start a paragraph with "I"

Restructure the opening clause. Mid-sentence "I" is fine and expected.

### One number does the heavy lifting

Pick the single strongest metric and let it stand alone. Stat-stacking reads
as a resume pasted into prose.

### Undersell the ask

One plain, low-pressure line, then stop. "If you're open to a short
conversation, let me know." No stacked hedge, no thank-you trailer.

### Writing the opening

The opening is built, not brainstormed. Run these in order.

1. **Name the surface, not the mission.** The specific product or bet the JD is
   hiring for is the subject. A mission statement never is.
2. **Find the departure.** Write how the category normally works as a full
   sentence, then this product's version. Without the baseline the departure
   does not land.
3. **End that sentence on the consequence.** What the departure demands or
   costs, as a concrete noun. That noun is the pivot.
4. **Open the next sentence on the pivot noun, then state your work.** Plain
   fact, no commentary. Never explain the parallel; the repeated noun is the
   whole argument (§8).
5. **One more sentence on what your time actually goes to.**

The shape:

> [How the category normally works]. [Their departure], which [consequence].
> At [employer] that [pivot noun] lands on [your product]. [What your time
> goes to].

Two ways this goes wrong. **Opening on your reaction** ("your posting caught my
attention", "I came across", "I'm reaching out because") announces that you
noticed something instead of saying the thing. **Naming the feeling**: any
sentence whose main verb is "excited", "passionate", "thrilled" or "drawn to".
The specificity carries the enthusiasm; the word never does.

**Test: could this opening be pasted into a letter to a different company? If
yes, step 2 has not been done.**

### Closing

- The last sentence of the final paragraph is exactly:

  > I look forward to discussing this opportunity in greater detail with you.

  Verbatim, every time, nothing after it. It closes the final paragraph rather
  than standing as its own, so the rule against opening a paragraph on "I"
  still holds. Do not end on a curiosity question; across a stack of letters the
  constructed question is the tell.
- Name a disqualifying gap in paragraph 1, then drop it. No reframe, no
  mitigation (§10).
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
- Sign off "Thanks,". No "Sincerely," or "Best regards,".

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
- **Location:** Boston, MA
- **Address:** 123 Example St, Boston MA 02101

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
    "title": "Senior Product Manager  |  Your Positioning Line",
    "contact": '<font color="#2C5F8A">555-555-0100</font>  |  <a href="mailto:alex.sample@example.com" color="#2C5F8A">alex.sample@example.com</a>  |  <a href="https://www.linkedin.com/in/your-handle/" color="#2C5F8A">LinkedIn</a>',

    "experience": [
        {
            "company": "Current Company",
            "role": "Senior Product Manager",
            "dates": "JAN 2023 – PRESENT",
            "bullets": [
                "One outcome-focused bullet with a concrete metric you can defend in an interview.",
                "Another bullet: what you built or decided, and what changed because of it.",
            ],
        },
        {
            "company": "Previous Company",
            "role": "Product Manager",
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

## 4. Configure the pipeline

Your search parameters are personal, so the real config is gitignored:

```sh
cp config/pipeline.example.toml config/pipeline.toml
```

Edit **`config/pipeline.toml`**. What to edit:

- `[location]` — replace the metro regexes with your own target geography,
  and the commute tiers/notes with drive times from where you live.
- `[domains.*]` / `[stages.*]` — reweight to your background; definitions
  feed the extraction prompt, so keep them concrete.
- `[filters]` — your comp floor, comp score thresholds, and years-of-experience cap.

- `[titles]` — which job titles count as target roles, adjacent tracks to
  exclude, and the seniority band. This is the industry knob: replace the
  product-management defaults with your own market's title patterns.
- `[extraction]` — the role noun the extraction prompt speaks about.

## 5. Build your company list

The tracked-company list lives in `data/state.db` (gitignored). Start from
the tiny neutral example, then build your own market's list:

```sh
job-finder companies import config/companies.example.json
job-finder companies list
```

To expand: put candidate employer names in a text file, probe them
(`python scripts/discover_companies.py --file candidates.txt --json hits.json`),
verify the hits, and `job-finder companies import hits.json`. The
`manage-companies` skill drives all of this from plain English in a Claude
Code session.

## 6. Schedule the weekly run

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_schedule.ps1
```

Registers a Windows Scheduled Task: `job-finder run --email` every Monday at
09:00 local. Test it once by hand first (`job-finder run --email` — this spends
real API tokens).

The task is registered with **`WakeToRun`**, which matters more than it sounds.
`StartWhenAvailable` is also on and covers a powered-off machine, but on
2026-08-31 the machine was merely **asleep** at 09:00 and no catch-up run ever
fired: 24 minutes after wake the task still reported one missed run and a next
run a week out. Sleep is the common case, so waking for the trigger is the fix.

Confirm afterwards with `job-finder status`, which prints the task's next run
and whether it will wake the machine.

No GitHub Actions secrets are required: the repo runs no CI workflows. Code
review is on demand: dispatch the `python-code-reviewer` agent, or use the
built-in `/code-review`. Either runs locally against your own key.

## 7. Personalize the Claude-side workflows

The `.claude/` prompts are generic: every user-specific rule (metric
baselines, banned framings, voice) is read at run time from your profile
docs, mainly `profile/claims_ground_truth.md` and the files in `[paths]`. So
personalization happens in §3, not by editing prompts. Two things worth a
skim anyway:

- `profile/claims_ground_truth.md` — the per-claim framing rules the
  fact-checker enforces come from here; the richer you make it, the more it
  catches
- `CLAUDE.md` — project instructions; adjust anything that doesn't match how
  you work

## 8. Optional — run it from Cowork

Skip this if you only use Claude Code; everything works there already.

Cowork does not index a project's `.claude/skills/`, so the weekly batch is also
packaged as a plugin in `cowork-plugin/`. Set `--output-dir` in
`cowork-plugin/.mcp.json` to this clone's absolute `.playwright-mcp` path (§2),
then build the archive:

```sh
python scripts/build_cowork_plugin.py
```

That writes `job-finder-cowork-plugin.zip` to your Downloads folder (`--out` to
put it elsewhere). Then, in Cowork: **Customize -> Plugins -> upload** it.
Uploading a plugin with the same `name` replaces the installed one.

**Install it; do not add `cowork-plugin/` as a context folder.** A connected
folder is just files on disk, so its `.mcp.json` never runs, Playwright never
starts, and the failure looks exactly like a broken plugin.

### Editing the plugin later: rebuild and re-upload, every time

**A correct file in `cowork-plugin/` does nothing until you rebuild the zip and
upload it again.** Cowork runs the snapshot it was given and keeps it
service-side, so nothing on your machine can compare the repo against what is
installed — `~/.claude/plugins/data/job-finder-inline/` is empty and
`.claude.json` holds only a usage counter.

That gap is not theoretical. On 2026-08-31 the repo's `.mcp.json` was correct and
the installed plugin was months older; every file upload was rejected, and seven
applications were filed with no resume and no cover letter attached.

Two checks exist, and you need both:

- **Bump `version` in `cowork-plugin/.claude-plugin/plugin.json` on every change
  that has to reach Cowork.** Cowork's plugin list shows the installed version, so
  the two side by side are a five-second drift check. `job-finder status` prints
  the repo's version for comparison. A version left alone across a rebuild throws
  this away.
- **The batch's preflight upload probe**, which uploads one throwaway file before
  drafting anything. It asks the running server rather than reading a file, so it
  is the only check that catches a stale install on its own.

Once installed, `/job-apply-weekly` runs the batch. It takes a count:
`/job-apply-weekly 3`, or `all`, defaulting to 5. The plugin is a launcher only
— the procedure it follows is `.claude/skills/job-apply-batch/SKILL.md` in this
repo, so **the repo still has to be the mounted folder for that session.**

Three things worth knowing before you rely on it:

- The plugin's `.mcp.json` is **required, not a duplicate of the repo-root one**.
  Cowork does not read a project's `.mcp.json`, so a plugin-bundled server is the
  only way it gets Playwright; the repo copy serves Claude Code. Keep the
  **Playwright version pin** identical in both (separate from the plugin's own
  `version` above).
- **`fill_greenhouse` does not run on Cowork.** The device VM has no `playwright`
  Python module, and a browser launched inside it is not one you can see or click,
  which defeats leaving tabs open for review. On Cowork every form goes through the
  autofill agent at roughly 63k tokens each, so that is a ceiling on how many roles
  one batch can carry. In Claude Code on Windows the script runs at about 2k.
- Playwright starts from a fresh browser profile with no cookies or logins, so
  any form behind an account wall gets an `APPLY_NOTES.md` handoff for manual
  submission rather than a fill attempt.

## 9. What never goes in git

Everything personal, already handled by `.gitignore`: `profile/`, `.env`,
`config/pipeline.toml`, and ALL of `data/` and `digests/` — the state
database (companies, applied/seen ledgers, digest archive), the ephemeral
jobs.db, fill audits, and the outreach log. The repo is pure engine; if a
commit ever contains personal data, that's a bug.

## Day-to-day commands

```sh
python -m pytest -q                              # tests
job-finder status                          # did the last run work? both halves
python -m job_finder.profile_check         # is my profile complete?
job-finder review                          # interactive digest review
job-finder applied add --external-id ...   # record an application
python -m job_finder.fill_greenhouse \
    --url <apply url> --folder <per-app folder>   # deterministic fill (not on Cowork)
python -m job_finder.letter_linter --date <YYYY-MM-DD>  # grade the drafted letters
python -m job_finder.fill_grader --date <YYYY-MM-DD>   # grade a fill batch
```

After every fill batch, run the grader on that date's audit manifests. It
letter-grades each form (missed fields, environment failures, critical
violations like a wrong sponsorship answer) and its `no_rule` list is your
backlog: each entry becomes a new `[[custom_combos]]` answer in
`profile/profile.toml`, so coverage compounds batch over batch.

The pipeline itself (`job-finder run`) is what the scheduled task runs
weekly — it spends real Anthropic tokens, so avoid extra casual runs.
`job-finder digest-archive list|show` reads the archive in state.db.
