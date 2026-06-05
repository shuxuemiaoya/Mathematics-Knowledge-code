# Heading Rules Prompt

You are generating deterministic Markdown heading normalization rules from extracted structure.

Return JSON only with this shape:

```json
{
  "rules": [
    {
      "id": "chapter_heading",
      "pattern": "^(第[一二三四五六七八九十]+章 .+?)(?: *[.．…·]+ *\\d+)?$",
      "replacement": "# \\\\1",
      "flags": ["MULTILINE"]
    }
  ],
  "notes": ["short human-readable summary"]
}
```

Rules must preserve math blocks, code fences, image links, and tables unless the payload explicitly requests changes to them.
