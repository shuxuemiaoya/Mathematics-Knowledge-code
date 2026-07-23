# Step 5 Heading-Check Contradiction Design

## Goal

Prevent a DeepSeek heading-check response from presenting allowed OCR equivalences as errors while simultaneously stating that they are not errors. Preserve the fail-closed contract and make the failure classification accurate.

## Root Cause

The Step 5 prompt already defines circled digits and matching Arabic digits as equivalent. DeepSeek nevertheless returned `valid: false` and populated `errors` with sentences ending in phrases such as `this is not an error`. The local validator checks JSON types, count consistency, uniqueness, and error limits, but it does not reject self-negating error entries. As a result, a malformed provider judgment is reported as a candidate heading failure.

## Design

1. Strengthen `heading_check_prompt.md` so `errors` may contain only genuine violations. Allowed equivalences and explanatory non-errors must never appear in the array. If no genuine violations remain, DeepSeek must return `valid: true` with an empty array.
2. Add a deterministic response-consistency check in `validate_heading_check_response()`. Reject any error string that explicitly says it is not an error, using a small, explicit English and Chinese phrase set rather than broad sentiment inference.
3. Keep fail-closed behavior. The runtime must not delete contradictory entries, reinterpret `valid: false` as success, or approve the candidate based on inferred intent.
4. Report the condition as an internally contradictory provider response so diagnosis points to model output quality instead of the candidate.

## Error Handling

- Contradictory entries raise `FormattingError` before candidate acceptance.
- Valid `false` responses containing genuine violations continue to reject the candidate exactly as before.
- Valid `true` responses with an empty error list continue to pass.
- No automatic retry is added. The operator may rerun after the prompt correction through the existing fingerprinted workflow.

## Testing

- Add a regression test using the exact structural pattern from the failed run: `valid: false` plus an error ending in `circled digits are equivalent, so this is not an error.`
- Add a Chinese self-negating phrase case.
- Confirm genuine violations still reach the normal candidate-rejection path.
- Run the complete guarded formatter test suite, syntax compilation, CLI help, and a real resumed run against the test Markdown.
- Verify the source Markdown SHA-256 remains unchanged.

## Scope

Only the Step 5 prompt, Step 5 response validator, focused tests, and canonical skill failure contract are in scope. Heading generation, TOC extraction, content processing, and source replacement behavior remain unchanged.
