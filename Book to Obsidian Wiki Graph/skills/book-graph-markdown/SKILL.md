---
name: book-graph-markdown
description: Standardize the presentation of TOC-split, concept-linked book notes while preserving all content, H1-H3 headings, table data, hyperlinks, image paths, formulas, reasoning chains, and source order. Use after book-graph-concepts to apply the supplied 概念提取与Markdown排版美化 prompt's Markdown-only rules for spacing, lists, choices, callouts, images, tables, proofs, and footnotes.
---

# Book Graph Markdown

Own Markdown presentation standardization only. Do not extract concepts again, change split ownership, or modify TOC-aligned H1-H3 headings.

## Inputs

Require a valid profile, completed split, lesson-flow, and coverage manifests,
and the concept manifest when concepts are enabled. Read
`references/markdown-standardization.md`, derived from:

```text
C:\Users\Oven\OneDrive\桌面\新建文件夹 (3)\概念提取与Markdown排版美化.md
```

Treat that user-supplied file as the canonical formatting contract. The local
reference is a checked-in operational rendering of Task 2 and must not weaken
or replace the source contract.

## Standardize

Process every generated note in source order:

1. Read the passed lesson-flow manifest first. Preserve its entry/topic
   ownership, hard functional boundaries, and block order; do not rebuild
   teaching hierarchy from keywords or merge adjacent blocks.
2. Preserve content before improving presentation.
3. Normalize paragraph spacing, lists, question choices, and formula blocks.
4. Convert only functionally appropriate H4-H6 headings and worked-example
   labels into complete, continuous callout containers. Prefix every body
   line, formula, image, HTML line, table line, and intentional blank line
   with the callout's required `>` depth.
5. Keep ordinary questions and exercises outside callouts.
6. Preserve complete analysis, solution, proof, and reasoning chains.
   In a contextual problem or question callout, nest an explicit
   `分析/思路/点拨` or `解/证明/解析/解答` block when it forms the matching
   response; do not flatten it into the parent body.
7. Prefer meaningful multi-image rows before centering single images.
8. Preserve every link and image destination byte-for-byte.
9. Normalize tables and footnotes without changing their data or meaning.
10. Remove OCR-only ornament headings such as `#### ● ●` and categorized-page
   running publisher headings. Keep meaningful publication text in the root
   front matter.
11. Do not treat prose references such as `例 1 中...` or `例7的结果...` as
    new worked-example markers.
12. Render a source functional label once. When the reviewed block already
    supplies `思考`, `观察`, or a similar label as its callout title, do not
    repeat that label as the first quoted body line.

Do not create backups when the profile says `none`. Use task-scoped staging and atomic writes.

Run `scripts/standardize_markdown.py` for the deterministic presentation pass.
Pass `--lesson-flow-manifest` for new textbook profiles.
It converts reviewed functional H4-H6 headings and numbered worked-example
labels into continuous quoted callouts, compacts a one-line worked-example
stem onto the example marker to match the approved textbook exemplar, nests
example and paired contextual analysis/solution
blocks at depth two, normalizes blank runs, verifies protected destinations
and content structure before publication, and writes the required per-file
report. Review any residual blocks reported by the formatting audit instead of
broadening its conversion patterns speculatively.

## Report

Write `markdown-standardization-report.json` with:

- `schema_version`, `stage: markdown-standardization`, and `status`;
- the absolute `profile` path and frozen `source_sha256`;
- `input_corpus_sha256` and `output_corpus_sha256`;
- a `protected_invariants` object covering headings, tables, links, images,
  formula numbering, source order, and quoted-body callout continuity, with every
  value a passing boolean;
- one entry in `files` for every processed note.

## Gate

Require unchanged H1-H3 text/order, table data, link destinations, image
destinations, formula numbering, and source order. Require continuous quoted
callout bodies, valid depth-two nesting, a real blank line before every callout,
resolving links/assets, no content loss, and no callout that owns a later
functional heading, definition, worked example, or practice block. Then invoke
the pre-canvas audit.

Before handoff, search every non-concept note for residual functional blocks.
No plain H4-H6 `观察`, `思考`, `探究`, `归纳`, theorem/property marker,
or worked-example line may remain outside its required callout marker. `解：`,
`证明：`, analysis, formulas, images, and the rest of the marked block must
remain inside its parent callout at the correct quote depth. Ordinary `练习`, section
exercises, and review-exercise headings remain ordinary Markdown. Require
`book-graph-audit --stage formatting` to pass before the pre-canvas gate.

The formatting gate must also block suspicious source incompleteness rather
than silently polishing it: a formal-definition line with unbalanced
parentheses, or an example whose solution contains a numbered subpart absent
from the stem, requires source/reference review.
