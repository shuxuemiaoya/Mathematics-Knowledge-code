---
name: render-exam-latex-pdfs
description: Convert validated reformatted and inline-solution Markdown editions into separate LaTeX documents and visually polished PDFs using distinct templates. Use as the strict final Exam Paper Organizer stage only after reformatting, solution supplementation, image cleaning, and the organizer barrier audit pass, or as an explicitly requested standalone renderer with Pandoc, XeLaTeX, source preservation, and page-by-page visual QA.
---

# Render Exam LaTeX PDFs

Publish two source-preserving editions with purpose-built templates:

- the validated reformatted paper uses `assets/期末试卷最简版.tex`;
- the worked-solution edition uses `assets/exam-solutions-template.tex`.

Generate both `.tex` and `.pdf` files. Treat PDF rendering and visual inspection as required parts of completion.

## Input contract

For the default two-edition run, resolve these exact sibling inputs:

```text
<folder>\ExamPaper（题解整合版）.md
<folder>\ExamPaper（题解整合版）（解析版）.md
```

Use the reformatted candidate as the paper edition rather than the untouched `ExamPaper.md`; it is the validated, LaTeX-oriented source. Allow explicit `--paper` and `--solutions` overrides when the user supplies different paths.

In the full organizer pipeline, run this skill only after Reformatted Exam Paper, Supplement Exam Solutions, and Batch Clean Images reach terminal successful states and the organizer's pre-publish audit passes. Allow an explicitly requested paper-only or solutions-only standalone run outside the organizer.

## Organizer prerequisite evidence

Distinguish organizer mode from an explicitly requested standalone render.

- **Organizer mode:** Require the controller-provided `<folder>\tmp\organizer\<run-id>\pipeline-state.json`. Read it before the renderer preflight and require `eligible_to_render: true` for the selected paper. Verify that it records successful reformatting and solution supplementation, `image_replacement_status: "completed"`, `image_quality_status: "unverified"` or `"passed"`, completed image counts and failed paths, a complete in-place replacement mapping for every referenced raster asset, and a passed pre-publish audit. Stop at a prerequisite-evidence gate if the manifest is missing, stale, incomplete, or false.
- **Standalone mode:** Do not invent or require organizer state when the user explicitly invokes this skill outside `exam-paper-organizer`. Report that image-cleaning and organizer-barrier guarantees were not applied.

Do not treat the existence of derived Markdown, `.tex`, or `.pdf` files as proof that organizer prerequisites passed.

## Render

1. Resolve the skill directory and input folder absolutely.
2. Record SHA-256 hashes for every selected Markdown source. In organizer mode, also verify the final derived Markdown hashes recorded by the pipeline-state manifest.
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

   Use `--edition paper` or `--edition solutions` only when the user requests one edition. Use `--overwrite` without a new prompt only for provisional outputs created earlier in the same current publishing attempt; require explicit permission for outputs that predate the current task.
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

Do not create backups. Do not overwrite an output that predates the current task without explicit permission. Preserve final Markdown image targets. In organizer mode, accept controller-created rendering-only Markdown copies whose image links point to proven cleaned PNGs; never rewrite the final derived Markdown editions.

## Template rules

- Keep the two templates structurally independent; do not render both editions with one template plus a color flag.
- Use XeLaTeX and `ctexart` for Chinese and Unicode text.
- Use the paper template for restrained exam typography, compact spacing, clear section hierarchy, and neutral answer-key presentation.
- Use the solutions template for a distinct blue-teal visual system, more generous reading spacing, and breakable highlighted solution blocks.
- Preserve Markdown wording, question order, numbering, mathematics, tables, images, and answer content.
- Convert the reformatter's forced-page-break HTML div to `\clearpage` through `scripts/exam_layout.lua`.
- Convert marked `exam-solution` blocks into the template's breakable `examSolutionBox` environment through the same filter.
- Fix layout defects in the templates, filter, or renderer. Do not rewrite mathematical or question content merely to make a page fit.

## Reference-matching profile

When the user supplies an original Markdown paper together with a finished reference PDF, treat the PDF as the visual source of truth and iterate in standalone paper mode.

- Compare every reference page with the same generated page, including title hierarchy, section starts, question grouping, image scale, page density, answer-booklet breaks, watermark restraint, and footer counters.
- Preserve a combined source containing both the question paper and its trailing answer key. Detect the repeated paper title and `数学参考答案`, reset the page counter, and publish independent `4 + 4`-style paper/answer footer counts when the reference uses separate booklets.
- Resolve URL-encoded, space-containing, and folder-prefixed Markdown image targets against the Markdown directory, the supplied folder, and their `images` directories. Rewrite only the generated LaTeX image targets to absolute normalized paths; never modify the Markdown source.
- Treat a standalone diagram immediately following a numbered item as belonging to that final question. Keep it proportionate on the right where space permits; for illustrated multiple-choice questions, switch to the narrow figure-choice measure so options cannot extend beneath the diagram.
- Choose four-column, two-column, or one-column answer choices according to their rendered length. Use one line per option for long choices.
- Normalize unsupported Unicode mathematical relation glyphs in generated LaTeX and preserve their mathematical meaning.
- For the common 19-question reference-answer profile, score markers may act as controlled page-break anchors only when all answer headings 15 through 19 are detected. Do not apply those reference breaks to a different paper structure.
- Reject a candidate with a different page count from the reference unless the source content itself differs. Continue until every generated page is visually clean and the booklet split matches.

## Visual QA

After every meaningful template or rendering change:

1. Run `pdfinfo` on each PDF and require a positive page count.
2. Remove previews from the previous iteration of the same run, then render every PDF page to PNG with Poppler under `<folder>\tmp\organizer\<run-id>\pdfs\<edition>`:

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
5. Record the final PDF hash and the exact inspected page numbers so stale previews cannot satisfy QA for a newer build.
6. In organizer mode, update the manifest only after inspecting the final build:
   - clean pages: set the selected render status and `image_quality_status` to `passed`; set `publishing_complete: true` only when all selected editions passed;
   - visible image or layout defect: set the selected render status to `failed_visual_qa`, set `image_quality_status: failed`, retain the outputs as provisional, and record the exact page and asset.
7. Remove temporary preview PNGs after verification unless the user asks to keep them.

Do not report successful completion based only on Pandoc or XeLaTeX exit codes.

## Report

Return:

- selected paper and solutions Markdown paths;
- the template used for each edition;
- generated `.tex`, `.pdf`, and build-log paths;
- page counts and file sizes;
- Pandoc and XeLaTeX status;
- visual-QA status and any corrected defects;
- organizer pipeline-state manifest and barrier status, or an explicit standalone-mode declaration;
- final PDF hashes and exact page ranges inspected;
- any missing input, dependency, output-exists, compilation, image, font, or visual-quality gate;
- confirmation that every selected Markdown source retained its original SHA-256 hash.
