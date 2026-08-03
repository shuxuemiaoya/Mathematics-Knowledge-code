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
- Keep atomic questions off the structural Canvas.
- Leave knowledge-point linking disabled until a later explicit stage.
- Keep staging outside published vault roots and create no backup directories.

## Canonical Skills

The canonical skills live under `skills/`. Expose them through junctions in
`C:\Users\Oven\.codex\skills`; do not maintain copied duplicates.
