# MathOS Preheader TOC Extraction Design

## Goal

Allow Stage 1 to extract a complete contiguous TOC whose earliest entries appear before the first OCR-recognized `# 目录` or `# CONTENTS` page header, without weakening the fail-closed boundary against preface or body content.

## Root Cause

The affected book has a contiguous TOC beginning at source line 185. Its first recognized TOC page header does not appear until line 301 because earlier TOC pages begin directly with titles and entries. The current provider prompt requires the response to begin at a TOC header, and the validator rejects any semantic line before that header. The accepted span therefore begins at line 301 and omits the first four topics, causing Stage 3 and Step 5 to disagree about valid H1-H3 headings.

## Scope

The change is limited to:

- `skills/mathos-formatting/agents/toc_detection_prompt.md`
- `skills/mathos-formatting/scripts/step1_toc_extraction.py`
- focused cases in `tests/test_mathos_formatting_guarded.py`

Later heading, content, approval, and source-replacement stages remain unchanged.

## Provider Contract

The provider must return one exact contiguous numbered source span covering the complete TOC.

- Begin at the earliest TOC title or entry, even when a recognized TOC page header occurs only on a later TOC page.
- Include the later `# 目录` or `# CONTENTS` header unchanged as an internal anchor.
- Stop after the final TOC entry and before the first body heading or body paragraph.
- Do not prepend cover, preface, author, date, or other non-TOC content.

## Validator Contract

The response no longer needs a recognized TOC header as its first semantic line. It must contain at least one recognized TOC header somewhere in the contiguous span.

Before the first recognized header, each semantic line must satisfy the same strict TOC evidence rules used after the header:

- a page-bearing TOC entry;
- a wrapped entry completed by a following page-bearing line;
- an ATX topic or section heading followed by TOC evidence;
- supported media/details blocks and blank lines inside the contiguous span.

The validator continues to require exact numbered-line identity, one contiguous source interval, a complete details block, TOC evidence on both sides of internal page headers, and safe adjacent boundaries. It must reject arbitrary preface/body headings, standalone prose, and any response with no recognized TOC header anchor.

## Output Contract

`VerbatimToc.start_line` and `end_line` cover the full validated span, including preheader TOC entries and internal media. `toc.md` contains every semantic TOC title and entry from that span while omitting protected media/details content as before.

TOC removal uses the validated full interval. No runtime backward search or automatic prefix expansion is allowed after provider selection.

## Tests

Focused tests will prove:

- a TOC beginning with topic headings and entries before a later `# 目录` anchor is accepted;
- the returned start line includes the preheader entries;
- preface text before an otherwise valid TOC is rejected;
- a headerless TOC-like span is rejected;
- existing wrapped-entry, repeated-header, media/details, verbatim, contiguous, incomplete, and body-tail rejection tests continue to pass.

After focused tests pass, run the complete guarded formatter suite, syntax validation, CLI help, and a fresh automated run of `2025解题觉醒邓诚数学.md` with source SHA-256 comparison.

## Acceptance

The change is accepted when the real run's immutable TOC contains the previously omitted topics one through four, Step 5 no longer reports their H3 headings as absent from the TOC, all guarded tests pass, and the original Markdown remains byte-identical. Any unrelated preface/body inclusion or missing internal TOC anchor must still fail closed.
