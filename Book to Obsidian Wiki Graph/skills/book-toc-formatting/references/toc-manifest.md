# TOC Manifest Contract

Create `toc-manifest.json` after inspecting the printed table of contents and the converted Markdown.

Use `scripts/plan_toc_manifest.py` to create the first draft. Its
`review_required` result is intentional: automatic extraction removes
transcription work, but the printed TOC remains authoritative and must be
checked before formatting.

```json
{
  "schema_version": 1,
  "profile": "C:/.../book-profile.json",
  "source_sha256": "<frozen PDF or source-book digest>",
  "input_markdown_sha256": "<raw Markdown digest>",
  "toc_source_ranges": [
    {"start_line": 20, "end_line": 85}
  ],
  "entries": [
    {
      "key": "chapter-1",
      "title": "第一章 集合与常用逻辑用语",
      "level": 1,
      "category": "knowledge",
      "filename": "第一章 集合与常用逻辑用语.md",
      "aliases": []
    },
    {
      "key": "lesson-1-1",
      "title": "1.1 集合的概念",
      "level": 2,
      "category": "knowledge",
      "filename": "1.1 集合的概念.md",
      "aliases": []
    }
  ]
}
```

## Entry rules

- Preserve printed TOC order.
- Use levels `1` through `3` for the hierarchy that should become H1-H3.
- Give every entry a stable unique key.
- Use `aliases` only for OCR variants of the same printed title. After a match,
  emit the canonical `title`, never the alias text from the OCR body.
- Record the exact source lines occupied by the printed TOC so those headings are not mistaken for book content.
- Assign a category for the later split stage.
- Assign book-wide standalone indexes and glossaries to category `root`.
- When OCR omits a printed TOC heading but its complete body is present, a
  reviewed entry may set `insertion_line` to the one-based line where the
  authoritative title must be restored and `insertion_reason` to a specific
  explanation. The manifest input hash binds this line to the exact frozen
  Markdown. Never use insertion to invent a title absent from the printed TOC.
- For textbooks, use the three required core roles plus only the
  source-supported auxiliary roles enabled in the profile.
- For other books, let the LLM propose categories, then record them in the profile before splitting.

The formatter changes heading depth and canonicalizes matched H1-H3 text to the
printed TOC title without rewriting body content. For an adjacent pair of OCR
heading fragments whose normalized concatenation exactly equals the
authoritative title, consolidate the pair and record both source lines. Every
content heading absent from this manifest must be demoted below H3.
