---
name: question-answer-matching
description: Match atomic questions to authoritative answer blocks with reviewed evidence, raw-line context boundaries, unique ownership, and blocking ambiguity review. Use after Question Type Graph content segmentation or when diagnosing missing, duplicate, or conflicting answer matches.
---

# Question Answer Matching

Read `references/answer-matching.md` before planning or applying matches.

Use `scripts/match_answers.py plan` with the frozen profile, reviewed adapter,
and content manifest. Apply only a passed manifest. Accept exact reviewed
identity evidence; keep fuzzy similarity advisory. Preserve raw-line coordinates
when splitting inline OCR headers, enforce one owner per answer and question,
and let application reconcile stale owned notes and embeds automatically.
Questions marked `answer_handling: separate-authoritative` are publisher worked
examples whose standalone answers are created during content segmentation; they
remain outside this external matching ledger.

All authoritative and reviewed supplemental answer notes share the same layout:
a collapsible outer FAQ with collapsible nested success-answer, note-analysis,
and note-explanation blocks. A flat `【答案】` or `【解析】` line is invalid.
