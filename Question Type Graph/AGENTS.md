# Question Type Graph Agent Contract

This directory is a standalone, profile-driven supplementary-book agent. Do
not import runtime code from `Book to Obsidian Wiki Graph` and do not modify
that agent while operating here.

## Required Sequence

```text
freeze typed sources
  -> forced MinerU OCR for every PDF source
  -> format inventory and reviewed adapter
  -> hierarchy segmentation
  -> functional-block and atomic-question segmentation
  -> generated-title cleanup
  -> optional authoritative answer matching
  -> reviewed supplementation for unresolved enabled answers
  -> markup-only Markdown standardization
  -> structural Canvas
  -> final audit
```

## Invariants

- Treat every source PDF and registered raw Markdown file as immutable.
- Carry the same absolute profile path and frozen source hashes through every
  structured handoff.
- Keep publisher labels, titles, page ranges, numbering rules, answer layouts,
  and output folder templates in a reviewed `format-adapter.json`, never in
  reusable compiler code.
- Create one leaf note per top-level question and keep its subparts together.
- Flatten question-bearing HTML tables into semantic column streams before
  segmentation. Merge streams by the next printed question number, keep each
  image or strategy with its column record, and expose adapter-matched labels
  inside cells as their own nodes; never leave orphan `<td>` or `<tr>` tags in
  an atomic question.
- Final audit must require a continuous `1..N` question-number ledger inside
  every reviewed answer context. Gaps, duplicates, and reordered numbers are
  blocking errors rather than warnings.
- Treat every authoritative `unmatched-answer` review record as a blocking
  `answer-without-question` error. Reviewer confirmation cannot waive it,
  because it may be the only evidence that a continuous-looking question
  ledger lost its entire tail.
- Preserve a publisher/OCR numbering reset in the immutable source body, but
  use matching reviewed question/answer number-shift ranges when semantic
  identity must remain continuous.
- If visual PDF review proves that conversion omitted a complete question,
  recover it only through a page-provenanced, reviewer-confirmed virtual
  question entry anchored to the immutable hierarchy corpus; never reconstruct
  a missing stem from the answer alone.
- Preserve source text, formulas, images, tables, numbering, and order. Add
  Markdown structure and navigation only.
- After content segmentation, clean every generated title and corresponding
  filename by preserving only Unicode letters, digits, and `_` and replacing
  every other character (including whitespace, full-width punctuation such as
  `：`, ASCII punctuation, symbols, and emoji) with `_`. Never rewrite frozen
  OCR text or question bodies during title cleanup.
- Never accept fuzzy answer similarity by itself. Route ambiguous or missing
  matches to a blocking review queue.
- Assign each answer block to at most one question and each question to at most
  one answer. A re-claimed candidate routes to the blocking review queue,
  never to a second match (the final audit hard-errors on
  `answer-owned-more-than-once`).
- Answer patterns must accept real "N.M…" answers (e.g. `8.2或-2或…`,
  `5.2 【解析】`) while rejecting section-number phantoms (`1.3 空间向量…`).
  Verify the pattern set against every `^\d+[.．、]\d` line in the answer raw,
  and keep the same patterns in the adapter and any build-script event scanner.
- Answer application is declarative: automatically remove owned answer notes
  and embeds when a question flips matched → unmatched, and record removals in
  `answer-application-report.json`.
- Store reviewer-authored solutions that must survive pipeline regeneration in
  staging `reviewed-supplement-overrides.json`, keyed by `question_id` and
  `question_body_sha256`. Regenerated supplement plans must reuse only entries
  whose body digest still matches, and the coordinator should reapply those
  reviewed solutions without another manual copy/paste cycle.
- Keep atomic questions off the structural Canvas.
- Leave knowledge-point linking disabled until a later explicit stage.
- Keep staging outside published vault roots and create no backup directories.
- Use adapter-configured `answers.callout_title` for answer callouts rather than hardcoding publisher names.
- When OCR drops a choice answer header but preserves an explicit authoritative conclusion such as `故选:D`, recover `D` into a separate `**【答案】** D` field. Never infer an option from isolated capital letters or mathematical prose. Choice-question audit must fail on a missing answer field, and authoritative notes must agree with the source conclusion.
- Every generated solution callout must contain both `**【答案】**` and
  `**【解析】**`. Recover a bounded publisher-stated result that appears before
  an explicit `解析:`/`【解析】` marker. When a non-choice problem has no safely
  separable short result, write `**【答案】** 详见解析`; never use that fallback
  for a choice problem, whose exact option remains mandatory.
- Ensure question and answer regex patterns use a single named group (e.g. `^【?(?P<number>\d+)[】.．、]?\s*`) to prevent Python regex duplicate group name errors.
- Bound question `end_line` before any internal markdown heading (`^\s*#{1,6}\s+\S`) in `plan_note()`, preserving inline sub-classifications (`角度`/`类型`), strategy callout text, and figures inside the leaf Type note between question embeds.
- Automatically deduplicate adjacent OCR duplicate answer header lines for the same `(context, number)` in `answers.py`.
- Allocate question sequence numbers through the locked vault registry
  `.question-type-graph/question-id-registry.json`. Seed a new registry from
  the vault and any adapter-configured central question repository.
- Pre-split inline answer headers (e.g. `... 故选：B 【5】A`) in `parse_answer_blocks()` before scanning so OCR lines containing concatenated answer headers are isolated into separate answer blocks.
- Update `format_answer_callout()` option extraction regex (`^【?\d+】?[\.、\s]*([A-Z]+)`) to accept bracketed question numbers (`【N】A`) as well as plain numbers (`N. A`).
- Validate and align `answers.contexts` `start_line` boundaries against exact section heading positions in `answers.raw.md` during format inventory to prevent cross-section answer block misattribution and duplicate-number collisions.
- Preserve `## 知识导学` knowledge guide sections and all nested subheadings (`## 一. ...`, `## 1. ...`), formulas, diagram asset paths, and comparison tables within primary section notes without splitting them into separate question notes.
- Enforce zero-tolerance validation for questions lacking explanations during graph audit: when answers are enabled, every atomic question note MUST embed a valid solution callout note (authoritative or AI-supplemented). Any question lacking an explanation MUST trigger a blocking audit error with its exact root cause identified (`ocr-header-missing`, `context-boundary-mismatch`, or `missing-answer-key`).
- Treat this file and `skills/question-type-graph/references/pipeline-contract.md`
  as the canonical policy. Knowledge linking remains deferred; component skill
  documentation must not activate it implicitly.

## Canonical Skills

The canonical skills live under `skills/`. Install or link that directory using
the host platform's Codex skill location; do not maintain copied duplicates.
