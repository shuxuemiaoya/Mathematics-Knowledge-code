# MathOS Formatting Multiline TOC Design

## Goal

Make Stage 1 TOC extraction handle OCR Markdown whose logical TOC entries span multiple source lines or repeat `目录` / `CONTENTS` page headers, while preserving the existing fail-closed guarantee against deleting body content.

## Scope

The change is limited to:

- `skills/mathos-formatting/agents/toc_detection_prompt.md`
- `skills/mathos-formatting/scripts/step1_toc_extraction.py`
- focused cases in `tests/test_mathos_formatting_guarded.py`

It does not change later formatting stages, candidate approval, source replacement, or generated-script safety.

## Response Contract

The provider must still return one exact, contiguous, numbered source span beginning at a recognized TOC heading. Every returned line must match the numbered sample verbatim.

The prompt will explicitly describe:

- wrapped entries where a title fragment and its page-bearing continuation occupy separate lines;
- repeated `目录` / `CONTENTS` headers caused by multi-page OCR;
- the requirement to stop before the first body heading or body paragraph after the final TOC entry;
- prohibition on returning the rest of the sample when the TOC ends before page 20.

## Validator Design

Replace independent line classification with a small look-ahead state machine over the already verified contiguous response.

The validator accepts:

- recognized TOC headers;
- ATX section headings that are followed by TOC entries;
- ordinary page-bearing TOC entries;
- wrapped logical entries whose non-page-bearing first line is completed by the next nonblank page-bearing line;
- repeated recognized TOC headers within a multi-page TOC;
- blank lines and protected media/details blocks already supported by the current contract.

The validator rejects:

- text before the first TOC header;
- non-page-bearing text with no valid TOC continuation;
- body paragraphs or body headings after the TOC;
- repeated non-TOC headings that indicate entry into the book body;
- disjoint, modified, incomplete, or ambiguous source spans;
- responses ending in an unfinished wrapped entry or details block.

The validator must not silently trim an overlong provider response. Any unrelated tail fails the run so Stage 4 cannot delete an uncertain interval.

## Error Handling

Failures remain `step1-toc-extraction` failures. The automated run continues to write exactly one routed error artifact, set `safe_to_approve: false`, and leave the source bytes unchanged.

Errors for malformed wrapped entries should identify whether the entry is unfinished or whether unrelated body text follows the validated TOC prefix.

## Tests

Add focused tests that prove:

- a wrapped title plus page-bearing continuation is accepted;
- repeated `目录` / `CONTENTS` page headers are accepted;
- an unfinished wrapped entry is rejected;
- a valid TOC followed by body content is rejected rather than trimmed;
- an ordinary single-line TOC remains unchanged;
- existing contiguous-span, verbatim, media/details, and source-preservation tests continue to pass.

After focused tests pass, run the complete guarded formatter suite and the CLI validation required by `SKILL.md`.

## Acceptance

The change is accepted when the guarded test suite passes and a fresh automated run of `2025解题觉醒邓诚数学.md` either passes Stage 1 safely or fails with a new precise provider-boundary error. Passing Stage 1 must never depend on weakening body-content rejection or modifying the source file.
