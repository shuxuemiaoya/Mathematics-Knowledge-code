---
name: book-pdf-to-markdown
description: Convert one source book PDF into raw Markdown and extracted assets through MinerU's local-file batch API with OCR forcibly enabled, formula and table extraction enabled, automatic splitting above API limits, and per-book profile identity checks. Use as the standalone Book to Obsidian Wiki Graph conversion stage; do not route book conversion through MathOS Agent.
---

# Book PDF To Markdown

Convert one profile-registered book PDF without changing or interpreting its content. This component is derived from Exam Paper Organizer's proven MinerU converter, with exam-ordering assumptions removed and book-profile/staging handoffs added.

## Inputs

Require:

- an existing PDF;
- a valid `book-profile.json` whose source path and SHA-256 match the PDF;
- a staging directory outside the final book tree.

Do not require exam images, an ordered-exam manifest, or any MathOS artifact.

## Plan And Convert

Run from the standalone agent directory:

```powershell
python .\skills\book-pdf-to-markdown\scripts\book_pdf_to_markdown.py plan `
  "<absolute book PDF>" `
  --profile "<staging>\book-profile.json"
```

Inspect the JSON plan, then continue automatically:

```powershell
python .\skills\book-pdf-to-markdown\scripts\book_pdf_to_markdown.py convert `
  "<absolute book PDF>" `
  --profile "<staging>\book-profile.json"
```

The default output is `<staging_root>\<pdf-stem>.raw.md`. Use `--output` only for an explicit alternative. Never pass `--overwrite` by inference.

Read `MINERU_API_KEY` from the process environment, then `/Users/oven/Documents/Mathematics-Knowledge-code/.env`. Never print or persist the token.

## Fixed MinerU Contract

Read `references/mineru-api.md`. Always send:

- `is_ocr: true`;
- `model_version: "vlm"`;
- `language: "ch"`;
- formula extraction enabled;
- table extraction enabled.

Do not expose an OCR-off option. Split inputs over 200 pages or 200 MB, convert all parts in page order, and merge them without rewriting OCR content.

## Assets And Handoff

- Keep the PDF byte-for-byte unchanged.
- Write assets under `images/<pdf-stem>/`; split parts use `part-###/`.
- Rewrite only MinerU-generated image destinations required to resolve those copied assets.
- Keep upload URLs, result zips, split PDFs, and partial Markdown transient.
- Emit compact JSON on stdout and progress on stderr.

Handoff only when status is `completed`, OCR is confirmed forced, page coverage is complete, the raw Markdown is nonempty, all reported assets exist, every local image link resolves, and the PDF still matches the profile hash.
