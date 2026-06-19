# Heading Validation Prompt

Validate the final Markdown heading structure against the immutable table of contents supplied in the input.

Return only one JSON object with this exact shape:

```json
{
  "valid": true,
  "checked_heading_count": 123,
  "errors": []
}
```

Rules:

- Copy the declared BODY HEADING COUNT into `checked_heading_count`; do not estimate or deduplicate it.
- Every H1-H3 heading must correspond to a TOC entry in the same order and hierarchy.
- TOC chapters map to H1, sections to H2, and subsections to H3.
- Every heading not represented in the TOC must be H4-H6.
- Non-TOC H4-H6 headings are valid and must not be reported as errors merely because they are absent from the TOC.
- Reject invented TOC entries, hierarchy changes, reordered headings, or OCR corrections that change TOC meaning.
- Generic headings must not gain parent or chapter context.
- Set `valid` to false and add a precise error for every violation.
- Do not return Markdown fences or text outside the JSON object.
