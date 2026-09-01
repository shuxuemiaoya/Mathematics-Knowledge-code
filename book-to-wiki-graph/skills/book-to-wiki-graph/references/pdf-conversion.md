# PDF to Markdown Handoff

Use an OCR-capable converter appropriate to the environment. The plugin does
not lock conversion to one vendor: a local model, MinerU, or another converter
is acceptable when it satisfies this handoff.

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
