---
name: render-exam-latex-pdfs
description: Convert a validated reformatted Markdown exam paper and its inline worked-solution edition into separate LaTeX documents and visually polished PDFs using distinct paper and solutions templates. Use for the final Exam Paper Organizer publishing stage, or when Codex must render `ExamPaper（题解整合版）.md` and `ExamPaper（题解整合版）（解析版）.md` as Chinese-capable `.tex` and `.pdf` artifacts with Pandoc, XeLaTeX, source preservation, and page-by-page visual QA.
---

# Render Exam LaTeX PDFs

Publish two source-preserving editions with purpose-built templates:

- the validated reformatted paper uses `assets/exam-paper-template.tex`;
- the worked-solution edition uses `assets/exam-solutions-template.tex`.

Generate both `.tex` and `.pdf` files. Treat PDF rendering and visual inspection as required parts of completion.

## Input contract

For the default two-edition run, resolve these exact sibling inputs:

```text
<folder>\ExamPaper（题解整合版）.md
<folder>\ExamPaper（题解整合版）（解析版）.md
```

Use the reformatted candidate as the paper edition rather than the untouched `ExamPaper.md`; it is the validated, LaTeX-oriented source. Allow explicit `--paper` and `--solutions` overrides when the user supplies different paths.

In the full organizer pipeline, run this skill only after Reformatted Exam Paper and Supplement Exam Solutions both succeed. Allow an explicitly requested paper-only or solutions-only standalone run.

## Render

1. Resolve the skill directory and input folder absolutely.
2. Record SHA-256 hashes for every selected Markdown source.
3. Run a non-writing preflight:

   ```powershell
   $env:PYTHONUTF8='1'
   python <skill-dir>\scripts\render_exam_pdfs.py <folder> --check
   ```

4. Stop at a missing-input, missing-template, missing-Pandoc, or missing-XeLaTeX gate.
5. Generate both editions by default:

   ```powershell
   python <skill-dir>\scripts\render_exam_pdfs.py <folder>
   ```

   Use `--edition paper` or `--edition solutions` only when the user requests one edition. Use `--overwrite` only with explicit permission when a target `.tex` or `.pdf` already exists.
6. Read the script's stdout JSON. Treat a nonzero exit or an edition status other than `completed` as a failed publishing stage.
7. Confirm the Markdown source hashes are unchanged.

## Output contract

Write to `<folder>\latex-output` unless the user supplies `--output-dir`.

For each selected Markdown source, write:

```text
<output-dir>\<source-stem>.tex
<output-dir>\<source-stem>.pdf
<output-dir>\logs\<source-stem>.xelatex.log
```

Do not create backups. Do not overwrite an existing output without explicit permission. Preserve image targets and resolve them through Pandoc's resource path rather than rewriting source Markdown links.

## Template rules

- Keep the two templates structurally independent; do not render both editions with one template plus a color flag.
- Use XeLaTeX and `ctexart` for Chinese and Unicode text.
- Use the paper template for restrained exam typography, compact spacing, clear section hierarchy, and neutral answer-key presentation.
- Use the solutions template for a distinct blue-teal visual system, more generous reading spacing, and breakable highlighted solution blocks.
- Preserve Markdown wording, question order, numbering, mathematics, tables, images, and answer content.
- Convert the reformatter's forced-page-break HTML div to `\clearpage` through `scripts/exam_layout.lua`.
- Convert marked `exam-solution` blocks into the template's breakable `examSolutionBox` environment through the same filter.
- Fix layout defects in the templates, filter, or renderer. Do not rewrite mathematical or question content merely to make a page fit.

## Visual QA

After every meaningful template or rendering change:

1. Run `pdfinfo` on each PDF and require a positive page count.
2. Render every PDF page to PNG with Poppler under `<folder>\tmp\pdfs\<edition>`:

   ```powershell
   pdftoppm -png -r 144 <input.pdf> <preview-prefix>
   ```

3. Inspect every rendered page. Check:
   - Chinese and mathematical glyphs render correctly;
   - no text, tables, formulas, images, headers, or footers are clipped or overlapping;
   - margins, line spacing, list indentation, section transitions, and page breaks are consistent;
   - question images are sharp, proportionate, and aligned;
   - the paper and solutions editions are visibly distinct;
   - solution boxes split cleanly across pages and never obscure content;
   - there are no blank accidental pages, black squares, raw HTML comments, placeholders, or tool tokens.
4. Correct every visible defect and rerun the affected edition until the latest page inspection is clean.
5. Remove temporary preview PNGs after verification unless the user asks to keep them.

Do not report successful completion based only on Pandoc or XeLaTeX exit codes.

## Report

Return:

- selected paper and solutions Markdown paths;
- the template used for each edition;
- generated `.tex`, `.pdf`, and build-log paths;
- page counts and file sizes;
- Pandoc and XeLaTeX status;
- visual-QA status and any corrected defects;
- any missing input, dependency, output-exists, compilation, image, font, or visual-quality gate;
- confirmation that every selected Markdown source retained its original SHA-256 hash.
