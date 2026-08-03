---
name: question-type-toc-segmentation
description: Plan and apply a reviewed hierarchy for supplementary exercise books using a primary printed TOC, secondary indexes, or a reviewer-confirmed content-derived hierarchy when no reliable TOC exists. Use after Question Type Graph format inventory and before content atomization.
---

# Question Type TOC Segmentation

Own the complete primary-TOC ledger, hierarchy ranges, chapter or section notes, source-order parent links, and line coverage. Read `references/hierarchy-manifest.md`.

```powershell
python scripts/segment_hierarchy.py plan `
  "<profile>" "<adapter>" "<staging>/hierarchy-manifest.json"

python scripts/segment_hierarchy.py apply `
  "<profile>" "<adapter>" "<staging>/hierarchy-manifest.json"
```

Record every primary printed-TOC entry before splitting; do not substitute repeated training-band labels for section, topic, comprehensive-training, assessment, or reinforcement entries. Require the executable entries to cover that ledger exactly and in order. When OCR omits a body title, use a reviewer-confirmed `reviewed-boundary` anchor with evidence and emit the source-exact TOC title as Markdown structure. Use `structural_only` for parent entries that share the first child's boundary.

Replace each direct child range with a resolving link at that same position. Preserve all unassigned front matter, secondary indexes, advertisements, and appendices in the root note. Stop when the hierarchy, anchor, or adapter needs review.
