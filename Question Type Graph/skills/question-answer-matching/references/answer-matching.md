# Answer Matching Contract

Parse only reviewed answer regions and context patterns. Match with exact
evidence in this order when available:

1. explicit source answer reference;
2. reviewed hierarchy context plus question number;
3. source page identity;
4. normalized-stem similarity as review evidence only.

Every answer block has one exact source range and digest. Missing, duplicate,
conflicting, context-free, or fuzzy-only candidates initially remain
`review_required`. A reviewer may mark a manifest passed with genuinely absent
answers using `status: passed` and `reviewer_confirmed: true`, only to route
those questions into the required supplemental-solution
stage; the final audit still requires a validated solution for every enabled
question.

Build exact indexes for context-number, evidence fields, source-page-number,
and normalized exact stems. Fuzzy review suggestions may inspect only ambiguous
exact candidates or same-number candidates; never compare every question with
the full answer corpus. Emit both complete `review_items` and grouped counts so
large duplicate/restart failures can be reviewed by context.

Save the answer as an independently provenance-marked callout note and embed it
from the atomic question. Keep question and answer provenance independent. For
answerless books, pass only when the profile explicitly declares
`answers.mode: unavailable`.

## Answer patterns: phantom guard vs real "N.M" answers

`^(?P<number>\d+)[.．、](?!\d)\s*` was meant to reject section-number phantoms
(`1.3 空间向量…` parsing as answer "1"), but it ALSO silently drops real
answers whose body starts with a digit right after the delimiter — RJA had 21
such lines (`8.2或-2或…`, `5.2 【解析】`, `6.35 【解析】`, `9.0或5【解析】`,
`7.4 8√2`, `3.2(取区间(1,2]内任何一个值均可)` …), all vanishing into
missing-answer with candidate_count 0 despite the text being present.

Discriminator that works: a phantom section number is always followed by
`[.．、\s]` after its second digit (`1.4.2 用…`, `1.3 空间…`); a real answer
body is not. Use in BOTH the event scanner and the adapter:

```
^(?P<number>\d+)[.．、](?!\d[.．、\s])\s*        # "1. A", "8.2或-2或…", "6.35 …"
^(?P<number>\d+)[.．、]\d\s*(?:[【$]|\d)        # "5.2 【解析】", "9.2 $\sqrt{17}$", "7.4 8√2"
```

Verify the pattern set by scanning every `^\d+[.．、]\d` line of the answer raw
and confirming the heading-like lines (bare section titles, no `##`) stay
unmatched. RJA: 21 real answers rescued, 8 heading lines still rejected, zero
new phantoms.

## Out-of-order answer blocks: boundary snap (review correction)

When the answer book answers the next section's questions BEFORE its own
heading (RJA: 第二章刷原创 Q6-Q9 answered inside the 刷真题 section, the 刷原创
section carrying only answers 1-2), bounded flow alignment emits a context
boundary at the first out-of-order answer line, which can be the WRONG side of
the real heading. Symptom: questions with `candidate_count: 0` whose answers
are visibly present, plus phantom duplicate-answer items in the following
context.

Correct handling (RJA, 2026-08):
- Keep a boundary that is correct for the QUESTION flow even when it disagrees
  with the answer book's own headings (answers 6-9 under s2-gk:刷原创 match
  刷原创 Q6-9; content verified).
- Snap the genuinely wrong boundary (s3-1-1:刷基础 emitted at the 刷原创 Q1
  answer line) to the first answer event AFTER the real `## <section>` heading.
  Locate the heading by text, assert it exists, and apply the override as a
  commented review correction in the build script — the adapter is a reviewed
  artifact, so a documented correction is legitimate.
- The answer book's own section labels must never be trusted as truth; the
  question flow is the authority.

## Ownership uniqueness invariant

A passed manifest must satisfy: every `answer_id` appears once AND every
`question_id` appears once. `lib/question_type_graph/answers.py` enforces this
with a `used_answer_ids` set: a decisive candidate already claimed by an
earlier question routes to a `duplicate-answer` review item (candidate_count 1)
instead of a second match. This is what the final audit's
`answer-owned-more-than-once` / `question-matched-more-than-once` checks
protect — keep the guard on any matcher refactor. Numbering-restart contexts
whose second-run answer block is missing from OCR are exactly the case that
previously slipped through (both runs saw the same single candidate).

## Stale answer artifacts on matched → unmatched transitions

Answer application is declarative. It removes previously owned authoritative
or supplemental notes that are no longer desired, strips generated answer
embeds, restores `answer_status: unmatched`, and records removals in the
application report. Do not use manual file deletion as the normal workflow.

## Resolving the answer-review gate

- Read `review_groups` (grouped by kind + context + number) and per-item
  `strategy_results`; sanction restart-boundary matches only when the
  (context, number) identity is defensible; never accept fuzzy-only evidence.
- Numbering-restart clusters are a real book property (question book's OCR
  drops 刷基础/刷提升 headings → one context holds two numbering runs while the
  answer book splits them). They legitimately route to the blocking queue — do
  NOT force fuzzy matches through them.
- Genuine OCR page-boundary gaps stay unmatched in authoritative matching;
  never fabricate a publisher answer. Route the question to a substantive,
  reviewer-confirmed supplemental solution when strict completion is enabled.
- The audit requires 100% explanation coverage for enabled answers. It verifies
  the solution note, callout structure, lexical signature, and provenance, not
  merely the presence of an embed.
