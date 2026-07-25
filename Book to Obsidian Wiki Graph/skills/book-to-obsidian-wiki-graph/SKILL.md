---
name: book-to-obsidian-wiki-graph
description: Coordinate the standalone conversion of a PDF or long Markdown book into a validated Obsidian Wiki-style knowledge graph through book-specific forced-OCR conversion, TOC-authoritative heading formatting, immediate TOC-based splitting with parent links, concept extraction, Markdown standardization, audits, and an optional logic canvas. Use for complete conversions, resumes, or audits; never route these stages through MathOS Agent.
---

# Book To Obsidian Wiki Graph

Coordinate component skills and enforce artifact gates. Do not absorb stage-specific implementation.

## Read

- Read `references/pipeline-contract.md` for stage ownership and handoffs.
- Read `references/example-architecture.md` when comparing with the 人教版高中必修第一册 example.
- Load each component skill only when entering its stage.

## Route

1. Invoke `book-graph-intake` to freeze source identity and create `book-profile.json`.
2. For PDF input, invoke `book-pdf-to-markdown`; for Markdown input, register that immutable source directly.
3. Invoke `book-toc-formatting` to build the TOC manifest, align all TOC headings to H1-H3, and demote every other heading below H3.
4. Immediately invoke `book-toc-splitting` after a passed formatting report.
5. Invoke `book-graph-concepts` after splitting.
6. Invoke `book-graph-markdown` to standardize presentation after concept links exist.
7. Invoke `book-graph-audit` and require a passed pre-canvas report.
8. Invoke `book-graph-canvas` only when enabled.
9. Invoke `book-graph-audit` for the final gate.

Never invoke `mathos-pdf-to-md`, `mathos-formatting`, or `mathos-segmentation`.

## Cross-Stage Invariants

- Preserve source meaning, complete blocks, and order.
- Carry one profile path and frozen source digest through every handoff.
- Carry immediate Markdown input/output hashes through formatting and splitting.
- Use only `知识点`, `概念`, and `习题` categories for textbooks.
- Record LLM-selected categories in the profile before splitting other books.
- Retain a link in the parent at every moved child block's original position.
- Do not accept TOC-only textbook splitting. Require the complete H4-H6 semantic-review ledger, numbered subsection notes, and section-exercise notes.
- Keep H1-H3 immutable after TOC formatting.
- Keep hyperlink and image destinations immutable during post-split standardization.
- Require Markdown standardization to eliminate residual functional headings and raw worked-example markers before pre-audit.
- Stop on failed or mismatched artifacts.

## Completion

Report source/profile identity, conversion result, TOC matches and demotions, split/category/parent-link counts, coverage, concepts, formatting validation, links/assets, optional canvas counts, audit results, and source integrity.

Completion requires the final applicable audit to report `status: passed`.
