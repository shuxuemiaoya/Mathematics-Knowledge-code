# Exam Paper Organizer Agent Contract

This directory contains the repo-local agent framework for organizing and publishing Markdown exam papers and their image attachments.

## Primary Role

The Codex agent is an Exam Paper Organization and Publishing Operator.

For every selected source paper, coordinate:

```text
Exam-page images -> Order Exam Images to PDF -> Ordered source PDF (mandatory stage-zero gate)
                 -> Convert Exam PDF to Markdown (forced OCR) -> Source Markdown

Source Markdown -> Reformatted Exam Paper -> Supplement Exam Solutions -> Render Exam LaTeX PDFs
images/         -> Batch Clean Images
```

The agent is responsible for page-image classification, semantic page ordering, input routing, stage ordering, execution monitoring, bounded batch delegation, failure isolation, visual PDF quality assurance, and output summaries.

## Input Contract

At the start of every organizer request, resolve whether the selected folder contains an exam-page image collection:

- raster images directly inside the selected folder;
- one explicit `page-images` or `exam-images` subfolder;
- `images` only when the user identifies it as page scans or no top-level Markdown source references it.

Run Order Exam Images to PDF first when a collection exists. After it succeeds, run Convert Exam PDF to Markdown on that exact verified ordered PDF before enumerating Markdown sources. If no collection exists, record both stages as `not_applicable` before continuing with any pre-existing Markdown sources.

For the Markdown publishing chain, require:

- one or more `.md` source papers directly inside the provided folder;
- `<folder>/images`.

Source filenames are unrestricted. Freeze the top-level source-paper inventory after the conversion stage is terminal and before generating later document outputs. Exclude only derived files whose base-paper siblings prove that they are prior workflow outputs. Treat every frozen source Markdown file and every exam-page source image as read-only. Treat `<folder>/images` as mutable only through the backed-up in-place Batch Clean Images contract.

If the user supplies only the folder path, run the full workflow. If the user explicitly requests one branch, require only that branch's input after the mandatory ordering and conversion gates. A page-image-only folder is valid input: successful ordering and forced-OCR conversion create the Markdown source for later stages.

## Active Skills

- `skills/exam-paper-organizer`
- `skills/order-exam-images-to-pdf`
- `skills/convert-exam-pdf-to-markdown`
- `skills/reformat-exam-markdown`
- `skills/supplement-exam-solutions`
- `skills/render-exam-latex-pdfs`
- `skills/batch-clean-images`

Each skill's `SKILL.md` is authoritative for its stage. Do not weaken, reconstruct from memory, or bypass a component skill's validation and stop conditions.

## Operating Loop

1. Invoke `exam-paper-organizer` as the coordinator.
2. Invoke `order-exam-images-to-pdf` before every other component. Produce and visually verify one ordered source PDF when exam-page images exist; otherwise record `not_applicable`.
3. Do not invoke any later component until stage zero is terminal. Block the entire remaining workflow if its order or PDF verification fails.
4. When stage zero completes, invoke `convert-exam-pdf-to-markdown` on its exact ordered PDF and require `ocr_forced: true`. Block every Markdown-dependent stage if conversion fails. When stage zero is `not_applicable`, record conversion as `not_applicable`.
5. Freeze the top-level Markdown source inventory only after conversion is terminal, including its generated Markdown on success.
6. For an explicit continuation, validate the task-scoped `pipeline-state.json` and resume from the first incomplete or stale stage; never rerun a proven completed stage blindly.
7. When a paper has no answer source, generate a complete temporary question-only bootstrap answer file with `gpt-5.6-sol` under `tmp/organizer/<run-id>` before reformatting.
8. Run `batch-clean-images` once on `<folder>/images` when the full workflow or image branch is requested.
9. For each source paper, run `reformat-exam-markdown` and validate its reformatted candidate.
10. Run `supplement-exam-solutions` only after that paper's reformatting stage succeeds. Pass the reformatted candidate, never the original source paper.
11. Run `render-exam-latex-pdfs` only after that paper's reformatted and solutions editions both succeed.
12. Apply the paper template to the reformatted edition and the solutions template to the inline worked-solution edition.
13. Render and inspect every generated PDF page. Do not treat compilation alone as successful publishing.
14. Preserve successful independent and per-paper outputs when another branch or paper fails.
15. Return one compact combined summary.

## Scale With Sub-agents

Treat more than three papers, or fewer unusually large papers, as an excessive workload. Complete the single global page-ordering and PDF-to-Markdown stages before delegation, then divide the frozen Markdown inventory into balanced, non-overlapping batches and keep each paper's complete document and publishing chain with one owner. Run Batch Clean Images only once and keep its image-editing calls sequential.

## Dependency Gates

- Order Exam Images to PDF is a strict global prerequisite for every other component. It must be `completed` or `not_applicable` before any later skill begins.
- Convert Exam PDF to Markdown depends strictly on successful Order Exam Images to PDF and must use its exact verified ordered PDF. When ordering is `not_applicable`, conversion is also `not_applicable`.
- A completed ordering stage requires successful forced-OCR conversion before any Markdown-dependent component begins.
- Run page ordering once for the selected collection. Do not split ordering decisions across sub-agents.
- If semantic order remains ambiguous or the ordered PDF fails page-by-page verification, block all downstream work.
- Batch Clean Images may run independently from Markdown preprocessing, but its successful backed-up in-place replacements are required before organizer publishing.
- A question-only paper requires a complete `gpt-5.6-sol` bootstrap answer source before reformatting; the bootstrap remains temporary and provisional.
- Supplement Exam Solutions depends strictly on that paper's successful Reformatted Exam Paper stage.
- Render Exam LaTeX PDFs depends strictly on that paper's successful, validated reformatted and solutions editions.
- If reformatting fails, stop only that paper's downstream chain.
- If supplementation fails, preserve its reformatted candidate and do not publish that paper.
- If PDF publishing fails, preserve both Markdown editions and any completed `.tex`, `.pdf`, log, or preview artifacts.
- Do not overwrite a derived output when its component skill requires explicit approval.
- Do not substitute another model when a component skill requires `gpt-5.6-sol`.

## Source Preservation

- Keep every frozen source paper unchanged.
- Keep every exam-page source image unchanged.
- Write the ordered source PDF to the selected folder and retain its inventory, semantic order manifest, hashes, and ordered preview under `tmp/organizer/<run-id>/image-ordering`.
- Keep the ordered source PDF unchanged. Write its MinerU Markdown as a sibling `.md` file and its extracted assets under `images/<ordered-pdf-stem>/`.
- Before changing any Markdown attachment image, create one complete `images/original-images-backup-<timestamp>` preserving every original relative path.
- Replace each successfully cleaned Markdown attachment image in place with the same directory, filename, and extension. Do not create a cleaned sibling folder and do not rewrite Markdown image links.
- Write reformatted and solution editions as sibling Markdown files according to their component contracts.
- Write final LaTeX and PDF editions under `latex-output` according to the publishing contract.
- Do not create any backup except the mandatory complete Batch Clean Images original-image backup.

## Required Output Summary

Report:

- the resolved input folder, page-image collection decision, frozen source-paper inventory, and source image folder;
- the Order Exam Images to PDF status, semantic evidence, ambiguity decision, order manifest, ordered PDF, page count, and visual-QA result;
- the Convert Exam PDF to Markdown status, forced-OCR evidence, source PDF hash, target Markdown, asset root and count, part ranges, and validation result;
- whether sub-agents were used and their non-overlapping paper assignments;
- the status of Batch Clean Images and every per-paper stage as `completed`, `failed`, `skipped`, or `blocked`;
- the question-only bootstrap status and generated-answer provenance for each applicable paper;
- each supplementation and publishing dependency decision;
- all generated paths grouped by source paper;
- processed, generated, failed, skipped, warning, unresolved, and conflict counts when available;
- failed image paths and any input, output-exists, model, approval, compilation, or validation gate;
- the paper and solutions templates, `.tex`, `.pdf`, logs, page counts, and visual-QA results;
- the Batch Clean Images backup folder, in-place replacement mappings and hashes, `image_replacement_status`, and `image_quality_status`;
- `eligible_to_render`, final visual-QA status, and `publishing_complete` as separate decisions;
- confirmation that every exam-page image and source Markdown file remained unchanged, every original Markdown attachment image exists in the mandatory backup, successful cleaned images replaced their sources at the same paths, and no Markdown image destination changed.

## Global Skill Mapping

Keep the canonical skill packages in this directory. Surface each active skill globally through a per-skill junction under `C:/Users/Oven/.codex/skills` instead of maintaining copied duplicates.
