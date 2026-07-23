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
- Match headings using the same conservative, meaning-preserving OCR equivalence used by Stage 3.
- Circled digits and the same Arabic digit are equivalent; for example, `③` and `3` are equivalent.
- Numeric value must remain identical; for example, `⑨` and `3` are not equivalent.
- Escaped markdown characters (such as `\*`) in the TOC and the same characters without escape (or spaces) in the body headings are equivalent.
- Full-width or half-width punctuation and insignificant spacing differences are equivalent only when title meaning, source order, and hierarchy are unchanged.
- Preserve the body heading text; validation does not require rewriting an equivalent OCR form to the TOC spelling.
- Set `valid` to false and return at most 20 unique errors that represent genuine violations.
- Do not repeat an error string, even when the same violation pattern occurs on several headings.
- The `errors` array may contain only genuine violations. Never include an allowed equivalence, a non-error explanation, or any sentence saying that something is not an error.
- Before responding, remove every allowed equivalence from `errors`. If no genuine violations remain, return `valid: true` and `errors: []`.
- `valid: false` requires at least one genuine violation in `errors`; `valid: true` requires `errors: []`.
- Do not return Markdown fences or text outside the JSON object.
