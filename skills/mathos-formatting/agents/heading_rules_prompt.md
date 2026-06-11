# Heading Rules Prompt

You are generating deterministic Markdown heading normalization rules from the extracted table of contents (TOC/目录) and text structure.

Your goal is to output JSON containing regex replacement rules that accomplish two main tasks:

1. **Standardize TOC Headings**:
   Generate rules to format the headings mentioned in the TOC to their appropriate hierarchical levels (e.g. Chapter headings to level-1 `#`, Section headings to level-2 `##`, Subsection headings to level-3 `###` etc.), removing page numbers and leader dots.

2. **Demote Non-TOC Headings**:
   Generate rules to demote any other headings in the document that are NOT mentioned in the TOC to levels not used by the TOC (e.g., H4+, using negative lookahead patterns like `^# (?!目录|第七章|第八章)(.+)$` to H4 or similar) so they do not occupy/clash with the TOC heading levels.

Return JSON only with this shape:

```json
{
  "rules": [
    {
      "id": "chapter_heading",
      "pattern": "^#? *(第[一二三四五六七八九十]+章 .+?)(?: *[.．…·]+ *\\\\d+)?$",
      "replacement": "# \\\\1",
      "flags": ["MULTILINE"]
    }
  ],
  "notes": ["short human-readable summary"]
}
```

Rules must preserve math blocks, code fences, image links, and tables unless the payload explicitly requests changes to them.

The input sample must contain a table of contents. If the sample does not contain a TOC, return JSON with an empty `rules` list and a note explaining that a TOC is required.

Use the TOC to infer the intended heading hierarchy. Return deterministic regex rules only; do not include prose outside JSON.
