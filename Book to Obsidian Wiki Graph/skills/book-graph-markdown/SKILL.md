---
name: book-graph-markdown
description: Standardize the presentation of TOC-split, concept-linked book notes while preserving all content, H1-H3 headings, table data, hyperlinks, image paths, formulas, reasoning chains, and source order. Use after book-graph-concepts to apply the supplied 概念提取与Markdown排版美化 prompt's Markdown-only rules for spacing, lists, choices, callouts, images, tables, proofs, and footnotes.
---

# Book Graph Markdown

Own Markdown presentation standardization only. Do not extract concepts again, change split ownership, or modify TOC-aligned H1-H3 headings.

## Inputs

Require a valid profile, completed split and coverage manifests, and the concept manifest when concepts are enabled. Read `references/markdown-standardization.md`, derived from:

```text
C:\Mathematics-Knowledge\Mathematics-Knowledge-code\Exam Paper Organizer\skills\概念提取与Markdown排版美化.md
```

## Standardize

Process every generated note in source order:

1. Preserve content before improving presentation.
2. Normalize paragraph spacing, lists, question choices, and formula blocks.
3. Convert only functionally appropriate H4-H6 sections and examples into callouts.
4. Keep ordinary questions and exercises outside callouts.
5. Preserve complete analysis, solution, proof, and reasoning chains.
6. Prefer meaningful multi-image rows before centering single images.
7. Preserve every link and image destination byte-for-byte.
8. Normalize tables and footnotes without changing their data or meaning.

Do not create backups when the profile says `none`. Use task-scoped staging and atomic writes.

## Gate

Require unchanged H1-H3 text/order, table data, link destinations, image destinations, formula numbering, and source order. Require valid callout nesting, a real blank line before every top-level callout, resolving links/assets, and no content loss. Then invoke the pre-canvas audit.

Before handoff, search every non-concept note for residual functional blocks.
No plain H4-H6 `观察`, `思考`, `探究`, `归纳`, theorem/property marker,
or worked-example line may remain outside its required callout. `解：` and
`证明：` belong inside that example when they are part of it; independent
proofs may remain ordinary Markdown when their function does not call for a
callout. Ordinary `练习`, section exercises, and review-exercise headings remain
ordinary Markdown. The audit stage treats residual functional blocks as an error.
