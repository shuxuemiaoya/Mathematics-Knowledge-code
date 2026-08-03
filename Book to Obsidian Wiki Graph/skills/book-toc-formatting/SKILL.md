---
name: book-toc-formatting
description: Rebuild a raw book Markdown heading hierarchy from the printed table of contents, promote every TOC entry to its authoritative H1-H3 level, automatically demote every content heading absent from the TOC below H3, and produce a validated formatted candidate without rewriting content. Use immediately after book PDF conversion or on equivalent raw book Markdown before TOC-based splitting.
---

# Book TOC Formatting

Make the printed TOC the only authority for H1-H3. Do not perform concept extraction, semantic splitting, callout formatting, or prose rewriting.

## Build The TOC Manifest

Read `references/toc-manifest.md`.

1. Inspect the actual printed TOC pages and raw Markdown.
2. Generate a reviewable draft instead of transcribing the printed TOC:

```powershell
python .\skills\book-toc-formatting\scripts\plan_toc_manifest.py `
  "<staging>\<book>.raw.md" `
  "<staging>\book-profile.json" `
  "<staging>\toc-manifest.json"
```

3. Review the reported source range, printed order, levels, categories, wrapped
   entries, filenames, and aliases against the actual printed TOC.
4. Add or remove OCR aliases only when they represent the same printed title.
   If OCR omitted a printed heading while retaining its body, record a reviewed
   `insertion_line` and specific `insertion_reason` in the identity-bound
   manifest instead of editing the raw Markdown.
5. Use `--toc-range START:END` only when automatic range detection is wrong.

## Format

```powershell
python .\skills\book-toc-formatting\scripts\format_toc_headings.py `
  "<staging>\<book>.raw.md" `
  "<staging>\toc-manifest.json" `
  "<staging>\<book>.toc-formatted.md" `
  --profile "<staging>\book-profile.json" `
  --report "<staging>\toc-format-report.json"
```

Apply these rules:

- A content heading present in the TOC receives its TOC level.
- A content heading absent from the TOC is automatically demoted to H4-H6.
- Emit the authoritative printed-TOC title for every match. OCR aliases are
  matching aids and must not survive as output H1-H3 text.
- When two adjacent OCR heading fragments exactly reconstruct one authoritative
  TOC title, consolidate them into the printed title and record both source
  lines in the report.
- Ignore headings inside fenced code and the recorded printed-TOC ranges.
- Match every TOC entry exactly once and in printed order.
- Leave the raw Markdown unchanged.

## Gate And Automatic Handoff

Require a completed report, matching profile/source/input hashes, all TOC
entries matched, every composite title backed by an exact authoritative-title
match, and no non-TOC H1-H3 headings.

On success, immediately invoke `book-toc-splitting`. Do not introduce the old MathOS formatting approval gate.
