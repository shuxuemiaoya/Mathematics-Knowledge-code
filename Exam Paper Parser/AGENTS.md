# Exam Paper Parser Agent Contract

This directory is a streamlined agent for standardized exam papers with inline
publisher solutions. It is not a general supplementary-book parser.

## Sequence

```text
source hash -> cached forced OCR -> fixed-profile section/question split
-> PDF-text answer reconciliation -> stable QIDs -> Obsidian notes
-> strict final audit
```

## Invariants

- Never edit the source PDF or frozen OCR Markdown.
- Use no LLM calls on the standard fast path.
- Never create a per-paper adapter when the fixed profile passes.
- Preserve every question stem, formula, image, subpart, solution, and order.
- Recover only explicit PDF-text choice answers; never solve or guess during parsing.
- Keep strategy summaries in `【分析】`; place every `【小问 n 详解】` block and
  derivation in `【解析】` without duplicating source marker labels.
- Keep one top-level question per QID and one authoritative answer note per QID.
- Never create `.canvas` files.
- Share the vault QID registry lock to avoid collisions with Question Type Graph.
- Stop at `review_required` rather than publishing a gap, duplicate, missing
  choice answer, missing solution, or broken image.
- Use Question Type Graph only as the exception path for nonstandard papers.
- Completion means the latest `final-audit-report.json` is passed with zero
  errors and zero warnings.
