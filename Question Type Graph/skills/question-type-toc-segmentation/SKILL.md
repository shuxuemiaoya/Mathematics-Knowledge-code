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
Count every leader occurrence on a joined multi-column OCR line separately.
Validate conventional `第N讲 -> N.M/思考题` parentage, and mark organizational
lecture parents `structural_only`. When sections contain internal modules/topics (`一、`, `二、`, `考点1`, `考点2`),
automatically extend hierarchy to 3 levels (or 4 levels), creating dedicated leaf notes and directories for each
subtopic. For organizational trees, enable the strict `leaf-only` ownership policy so questions can be owned only by
the finest leaf notes. Every entry in `entries` and `primary_authority` MUST be strictly ordered by `source_line`
in increasing monotonic reading order to ensure full line coverage without drift or empty notes.
Treat inventory's inferred two-level shape as a review proposal, not authority.
