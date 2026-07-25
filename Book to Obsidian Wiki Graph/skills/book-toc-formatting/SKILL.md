---
name: book-toc-formatting
description: Rebuild a raw book Markdown heading hierarchy from the printed table of contents, promote every TOC entry to its authoritative H1-H3 level, automatically demote every content heading absent from the TOC below H3, and produce a validated formatted candidate without rewriting content. Use immediately after book PDF conversion or on equivalent raw book Markdown before TOC-based splitting.
---

# Book TOC Formatting

Make the printed TOC the only authority for H1-H3. Do not perform concept extraction, semantic splitting, callout formatting, or prose rewriting.

## Build The TOC Manifest

Read `references/toc-manifest.md`.

1. Inspect the actual printed TOC pages and raw Markdown.
2. Record TOC entries in printed order with authoritative levels 1-3.
3. Record OCR aliases only when they represent the same printed title.
4. Record the raw-Markdown line ranges occupied by the printed TOC.
5. Freeze the raw Markdown digest.

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
- Preserve heading text; change only the `#` depth.
- Ignore headings inside fenced code and the recorded printed-TOC ranges.
- Match every TOC entry exactly once and in printed order.
- Leave the raw Markdown unchanged.

## Gate And Automatic Handoff

Require a completed report, matching profile/source/input hashes, all TOC entries matched, and no non-TOC H1-H3 headings.

On success, immediately invoke `book-toc-splitting`. Do not introduce the old MathOS formatting approval gate.
