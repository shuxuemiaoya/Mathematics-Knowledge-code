# MathOS Heading Validation OCR Equivalence Design

## Goal

Make Step 5 apply the same conservative OCR-equivalence contract as Stage 3, while bounding provider error output so validation cannot expand into a repetitive, truncated JSON response.

## Scope

The change is limited to:

- `skills/mathos-formatting/agents/heading_check_prompt.md`
- `skills/mathos-formatting/scripts/step5_heading_validation.py`
- focused cases in `tests/test_mathos_formatting_guarded.py`

It does not change TOC extraction, heading processor execution, content processing, candidate approval, or source replacement.

## OCR Equivalence Contract

Step 5 must accept an H1-H3 body heading when it matches the authoritative TOC through conservative, meaning-preserving OCR equivalence already allowed by the Stage 3 prompt.

Accepted equivalences include:

- circled digits and the same Arabic digit, such as `③` and `3`;
- full-width and half-width punctuation with the same structural meaning;
- insignificant spacing differences.

Equivalence never permits changing numeric value, title meaning, source order, or hierarchy. For example, `⑨` is not equivalent to TOC number `3`.

The body heading keeps its original text. Step 5 validates equivalence; it does not rewrite candidate headings.

## Bounded Error Contract

The provider must return the existing JSON object with `valid`, `checked_heading_count`, and `errors`.

The `errors` list must:

- contain unique strings;
- contain at most 20 entries;
- report representative violations rather than every occurrence;
- remain empty when `valid` is true.

The Python validator enforces uniqueness and the 20-entry limit after JSON parsing. Duplicate or oversized lists fail closed with a precise contract error. Invalid or truncated JSON continues to fail closed.

## Prompt Changes

The heading-check prompt will:

- explicitly share Stage 3's conservative OCR-equivalence rules;
- include accepted and rejected numbering examples;
- replace the instruction to report every violation with a unique, maximum-20 error rule;
- forbid repeating an error string.

## Tests

Focused tests will prove:

- the prompt accepts `③` as equivalent to `3`;
- the prompt rejects `⑨` as equivalent to `3`;
- the prompt limits errors to 20 unique strings;
- the parser rejects duplicate errors;
- the parser rejects more than 20 errors;
- existing success, count-mismatch, rejection, and invalid-JSON behavior remains unchanged.

After focused tests pass, run the complete guarded formatter suite, syntax validation, CLI help, and a fresh automated run of `2025解题觉醒邓诚数学.md` while comparing source SHA-256 before and after.

## Acceptance

The change is accepted when all guarded tests pass and the live run no longer fails because equivalent circled digits were reported repeatedly or because the Step 5 response expanded into truncated JSON. Any genuine numeric mismatch, hierarchy error, invalid JSON, duplicate error output, or oversized error list must still fail closed, and the source Markdown must remain unchanged.
