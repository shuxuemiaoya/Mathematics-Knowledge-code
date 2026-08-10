---
name: question-answer-matching
description: Match atomic supplementary-book question notes to source-exact authoritative answer and analysis blocks from a separate or embedded answer source using reviewed context and numbering evidence, while routing missing, duplicate, conflicting, or fuzzy-only candidates to blocking review. Use after question atomization.
---

# Question Answer Matching

Read `references/answer-matching.md`. Do not generate, summarize, or silently repair answers.

```powershell
python scripts/match_answers.py plan `
  "<profile>" "<adapter>" "<question-type-manifest>" `
  "<staging>/answer-match-manifest.json"

python scripts/match_answers.py apply `
  "<profile>" "<staging>/answer-match-manifest.json"
```

Apply only a passed manifest. Store the exact answer beneath `答案与解析` in the atomic question note with independent markers and hashes, without adding a question-title heading. Treat fuzzy similarity as review evidence only. Pass without answer sections only when the frozen profile deliberately declares `answers.mode: unavailable`.

## Hard rules (production-proven)

- **Ownership uniqueness**: a passed manifest must have unique `answer_id` AND
  unique `question_id`. Never match the same answer block to a second question;
  a re-claimed decisive candidate becomes a `duplicate-answer` review item
  (this is what the `used_answer_ids` guard in `lib/question_type_graph/answers.py`
  enforces — keep it when refactoring).
- **Answer patterns**: the guard `(?!\d)` alone silently drops real answers
  whose body starts with a digit (`8.2或-2或…`, `5.2 【解析】`, `6.35 【解析】`).
  Use `^(?P<number>\d+)[.．、](?!\d[.．、\s])\s*` plus
  `^(?P<number>\d+)[.．、]\d\s*(?:[【$]|\d)`; a phantom section number is always
  followed by `[.．、\s]` after its second digit, a real answer body is not.
  Keep the same patterns in the build-script event scanner and the adapter.
- **Stale artifacts**: when questions flip matched → unmatched (e.g. after a
  matcher or adapter fix), remove orphaned `Q*<id>A1.md` notes and strip the
  `![[Q*<id>A1]]` line from the question note BEFORE the final audit;
  otherwise the audit errors `unexpected-generated-note` / `broken-link`.
- **Review-gate resolution**: restart clusters and genuine OCR gaps stay as
  reviewed warnings in a passed manifest (same-series precedent: 必修第一册
  passed with 865 missing / 874 unmatched). Never force fuzzy matches through;
  never fabricate missing answers.
