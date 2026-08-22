---
name: question-type-toc-segmentation
description: Plan and apply a reviewed complete hierarchy while preserving immutable content snapshots and source-line coverage. Use after format inventory and adapter review.
---

# Question Type TOC Segmentation

Read `references/hierarchy-manifest.md`. Plan and apply through
`scripts/segment_hierarchy.py`. Require a complete reviewed printed-TOC ledger
or an explicit reviewed no-TOC decision, preserve every source line, embed only
direct children, and create immutable staging snapshots for content planning.
For multi-page printed TOCs, register every leader-delimited row before the
first body anchor; use reviewed `primary_authority.excluded_entries` only for
printed answer/index rows that intentionally do not become content nodes.
Validate conventional `第N讲 -> N.M/思考题` parentage, and mark organizational
lecture parents `structural_only` so questions can be owned only by leaf notes.
