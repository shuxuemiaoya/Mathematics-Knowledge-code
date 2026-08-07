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

## Canonical Skills

The canonical skills live under `skills/`. Expose them through junctions in
`C:\Users\Oven\.codex\skills`; do not maintain copied duplicates.
