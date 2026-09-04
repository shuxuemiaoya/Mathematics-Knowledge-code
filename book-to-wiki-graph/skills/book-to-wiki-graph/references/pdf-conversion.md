# PDF to Markdown Handoff

Use an OCR-capable converter appropriate to the environment. The plugin does
not lock conversion to one vendor: a local model, MinerU, or another converter
is acceptable when it satisfies this handoff.

The bundled `scripts/convert_pdf.py` is the default MinerU adapter. It reads
`MINERU_API_KEY` from the process environment or an explicitly selected env
file, supports OCR/formula/table extraction, splits oversized PDFs, and merges
results in page order. Other PDF tools may supplement conversion and QA; the
Markdown handoff and conversion report remain authoritative.

## Required behavior

- Freeze the PDF path, SHA-256, size, and page count before conversion.
- Enable OCR for scanned or mixed PDFs; enable formula and table extraction
  when the converter supports them.
- Process every page once and merge parts in page order.
- Preserve headings as observed rather than guessing the final hierarchy.
- Preserve formulas, tables, figures, captions, footnotes, examples, question
  numbering, and page-local reading order.
- Store assets below staging and keep every local asset embed resolving.
- Do not rewrite, summarize, translate, or classify content during conversion.
- Do not log API keys, signed URLs, or tokens.

## Conversion report

Write `conversion-report.json` containing:

- source path and SHA-256;
- output Markdown path and SHA-256;
- converter name/version and OCR state;
- expected and converted page counts;
- asset count and unresolved asset list;
- status and failures.

Continue to TOC extraction only when the report says `passed`, the Markdown is
nonempty, page coverage is complete, assets resolve, and the original PDF
digest is unchanged.

When the input is already Markdown, register its path and digest directly and
skip PDF conversion. Do not round-trip it through a PDF tool.

```bash
python scripts/convert_pdf.py <book.pdf> \
  --output <staging>/book.raw.md \
  --report <staging>/conversion-report.json \
  --env-file /path/to/.env
```
