---
name: convert-exam-pdf-to-markdown
description: Convert the ordered exam PDF produced by `order-exam-images-to-pdf` into source Markdown through MinerU's local-file batch API with OCR forcibly enabled. Use as the Exam Paper Organizer stage immediately after successful page ordering, or when an ordered exam PDF must be converted to Markdown before reformatting, solution supplementation, image cleaning, or LaTeX/PDF publishing.
---

# Convert Exam PDF to Markdown

Convert exactly one semantically ordered exam PDF into Markdown. Preserve the PDF unchanged and force MinerU OCR for every uploaded file or split part.

## Enforce the stage gate

1. Read the completed `order-exam-images-to-pdf` report or manifest.
2. Accept only its verified ordered PDF path. Do not reconstruct page order in this stage.
3. Require the ordering status to be `completed`, its ambiguity list to be empty, and its page-by-page visual QA to have passed.
4. If ordering is `failed`, `blocked`, ambiguous, or unverified, mark conversion `blocked` without calling MinerU.
5. If ordering is `not_applicable`, mark this stage `not_applicable`; do not convert an unrelated PDF implicitly.

## Run the converter

Run from the Exam Paper Organizer directory:

```powershell
python .\skills\convert-exam-pdf-to-markdown\scripts\convert_exam_pdf_to_markdown.py plan `
  "<absolute ordered PDF path>"
```

Inspect the JSON plan, then convert:

```powershell
python .\skills\convert-exam-pdf-to-markdown\scripts\convert_exam_pdf_to_markdown.py convert `
  "<absolute ordered PDF path>"
```

The default output is `<ordered-pdf-parent>\<ordered-pdf-stem>.md`. Use `--output` only when the user requests a different Markdown path. Do not pass `--overwrite` unless the user explicitly approves replacing the pre-existing Markdown and its MinerU asset namespace.

Read `MINERU_API_KEY` from the process environment first, then from `C:\Mathematics-Knowledge\.env`. Never print, persist, or include the token in a report.

## Keep the MinerU contract fixed

The script must submit every PDF or split part through `POST /api/v4/file-urls/batch` with:

```json
{
  "files": [{"name": "ordered.pdf", "data_id": "...", "is_ocr": true}],
  "model_version": "vlm",
  "language": "ch",
  "enable_formula": true,
  "enable_table": true
}
```

Do not expose a command-line option that can disable OCR. Treat the `ocr_forced: true` field in the script's result JSON as required handoff evidence.

For endpoint details, limits, states, and output structure, read [references/mineru-api.md](references/mineru-api.md).

## Preserve outputs and boundaries

- Keep the ordered PDF and every original exam-page image byte-for-byte unchanged.
- Write extracted assets under `images/<ordered-pdf-stem>/`; split PDFs use `images/<ordered-pdf-stem>/part-###/`.
- Rewrite only MinerU-generated Markdown image destinations needed to point at those copied assets.
- Split inputs over 200 pages or 200 MB, convert every part in page order, and merge the returned `full.md` bodies in that same order.
- Keep upload URLs, result zips, split PDFs, and partial Markdown transient.
- Emit compact machine-readable JSON on stdout. Send progress only to stderr.
- Do not judge, rewrite, or improve the OCR text in this stage.

## Validate before handoff

Require all of the following:

- the command exits zero and reports `status: "completed"`;
- `ocr_forced` is `true`;
- `source_pdf` matches the ordered PDF from stage zero;
- `target_md` exists, is nonempty, and is inside the selected exam folder unless the user chose another output;
- every extracted asset reported by the script exists;
- every local image destination in the generated Markdown resolves to the extracted staged asset that will occupy that destination; reject unresolved or redundantly prefixed local paths before committing outputs;
- the part count and page ranges cover the full PDF without gaps or overlap;
- the ordered PDF hash still matches the stage-zero hash.

On success, add only `target_md` to the frozen Markdown source-paper inventory and continue with `reformat-exam-markdown`. Do not treat the MinerU Markdown as already reformatted.

On failure, block every Markdown-dependent downstream stage. Report the script's error category, MinerU error message, ordered PDF path, attempted target path, and whether any pre-existing output gate stopped execution.

## Report

Return:

- stage name `Convert Exam PDF to Markdown`;
- status `completed`, `failed`, `blocked`, or `not_applicable`;
- ordered PDF path, hash, page count, and size;
- target Markdown and asset-root paths;
- `ocr_forced`, model, language, formula, and table settings;
- split-part count and page ranges;
- extracted asset count;
- validation result and exact downstream handoff decision.
