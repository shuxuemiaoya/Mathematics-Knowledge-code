# Answer Matching Contract

Parse only reviewed answer regions and context patterns. Match with exact
evidence in this order when available:

1. explicit source answer reference;
2. reviewed hierarchy context plus question number;
3. source page identity;
4. normalized-stem similarity as review evidence only.

Every answer block has one exact source range and digest. A passed manifest
contains one answer for every enabled question and no unused answer block.
Missing, duplicate, conflicting, context-free, or fuzzy-only candidates remain
`review_required`.

Build exact indexes for context-number, evidence fields, source-page-number,
and normalized exact stems. Fuzzy review suggestions may inspect only ambiguous
exact candidates or same-number candidates; never compare every question with
the full answer corpus. Emit both complete `review_items` and grouped counts so
large duplicate/restart failures can be reviewed by context.

Append the answer verbatim beneath `答案与解析` in the atomic question note.
Keep question and answer provenance markers independent. For answerless books,
pass only when the profile explicitly declares `answers.mode: unavailable`.
