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
