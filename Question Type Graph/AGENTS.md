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
  -> optional authoritative answer matching
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
- Preserve source text, formulas, images, tables, numbering, and order. Add
  Markdown structure and navigation only.
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
- When answer matching changes, clean stale answer artifacts before the final
  audit: orphaned `Q*<id>A1.md` notes and `![[Q*<id>A1]]` embeds left behind by
  questions that flipped matched → unmatched. The audit errors on
  `unexpected-generated-note` / `broken-link` otherwise.
- Keep atomic questions off the structural Canvas.
- Leave knowledge-point linking disabled until a later explicit stage.
- Keep staging outside published vault roots and create no backup directories.
- Use adapter-configured `answers.callout_title` for answer callouts rather than hardcoding publisher names.
- Ensure question and answer regex patterns use a single named group (e.g. `^【?(?P<number>\d+)[】.．、]?\s*`) to prevent Python regex duplicate group name errors.
- Bound question `end_line` before any internal markdown heading (`^\s*#{1,6}\s+\S`) in `plan_note()`, preserving inline sub-classifications (`角度`/`类型`), strategy callout text, and figures inside the leaf Type note between question embeds.
- Automatically deduplicate adjacent OCR duplicate answer header lines for the same `(context, number)` in `answers.py`.
- Automatically scan central mathmap question repository (`/Users/oven/Documents/ovenmathmap/mathmap/习题/questions`) alongside `vault_root` in `find_next_q_number()` so new question sequence numbers (`Q0000XXXX.md`) strictly continue after the global maximum question ID.
- Pre-split inline answer headers (e.g. `... 故选：B 【5】A`) in `parse_answer_blocks()` before scanning so OCR lines containing concatenated answer headers are isolated into separate answer blocks.
- Update `format_answer_callout()` option extraction regex (`^【?\d+】?[\.、\s]*([A-Z]+)`) to accept bracketed question numbers (`【N】A`) as well as plain numbers (`N. A`).
- Validate and align `answers.contexts` `start_line` boundaries against exact section heading positions in `answers.raw.md` during format inventory to prevent cross-section answer block misattribution and duplicate-number collisions.
- Preserve `## 知识导学` knowledge guide sections and all nested subheadings (`## 一. ...`, `## 1. ...`), formulas, diagram asset paths, and comparison tables within primary section notes without splitting them into separate question notes.
- Enforce zero-tolerance validation for questions lacking explanations during graph audit: when answers are enabled, every atomic question note MUST embed a valid solution callout note (authoritative or AI-supplemented). Any question lacking an explanation MUST trigger a blocking audit error with its exact root cause identified (`ocr-header-missing`, `context-boundary-mismatch`, or `missing-answer-key`).

## Canonical Skills

The canonical skills live under `skills/`. Expose them through junctions in
`C:\Users\Oven\.codex\skills`; do not maintain copied duplicates.
