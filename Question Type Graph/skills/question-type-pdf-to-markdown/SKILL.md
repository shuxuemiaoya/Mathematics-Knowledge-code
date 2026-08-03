---
name: question-type-pdf-to-markdown
description: Convert a profile-registered supplementary-book PDF source in the questions, answers, or combined role into raw Markdown and assets through MinerU with OCR forcibly enabled, formulas and tables enabled, and automatic splitting above 200 pages or 200 MB. Use as the conversion stage of Question Type Graph.
---

# Question Type PDF To Markdown

Convert one immutable typed PDF without interpreting its content. Read `references/mineru-api.md` before live conversion.

## Commands

```powershell
python scripts/question_type_pdf_to_markdown.py plan "<profile>" questions
python scripts/question_type_pdf_to_markdown.py convert "<profile>" questions `
  --report "<staging>/questions-conversion-report.json"
```

Run separately for `answers`; use `combined` for a single combined source.

## Contract

- Always send `is_ocr: true`, `model_version: vlm`, language from the profile, and formula/table extraction enabled.
- Split locally above either API limit and merge in page order with source-part markers.
- Read `MINERU_API_KEY` from the process environment, then `C:\Mathematics-Knowledge\.env`; never print it or signed upload URLs.
- Preserve the PDF digest, commit resolving assets, and emit a hash-backed report.
- Persist active MinerU batch identity so `resume` survives transient polling disconnects without a second upload.
- Refuse existing output without explicit `--overwrite`.
