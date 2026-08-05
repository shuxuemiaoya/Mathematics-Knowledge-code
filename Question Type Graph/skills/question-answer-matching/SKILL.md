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
