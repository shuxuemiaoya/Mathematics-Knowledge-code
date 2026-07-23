---
name: exam-paper-organizer
description: Orchestrate a complete exam-paper workflow from a folder containing unordered exam-page images, one or many arbitrarily named source Markdown papers, and optional image attachments. Use when Codex must run `order-exam-images-to-pdf` as a mandatory stage-zero gate, convert its ordered PDF through MinerU with forced OCR, then coordinate any combination of `reformat-exam-markdown`, `supplement-exam-solutions`, `batch-clean-images`, and `render-exam-latex-pdfs`, with bounded sub-agents for excessive paper batches and strict validation barriers.
---

# Exam Paper Organizer

Coordinate the six installed component skills without replacing or weakening their live contracts.

## Load component contracts

Before performing a selected stage, read the corresponding installed `SKILL.md` completely and follow it as authoritative:

- `order-exam-images-to-pdf` for **Order Exam Images to PDF**
- `convert-exam-pdf-to-markdown` for **Convert Exam PDF to Markdown**
- `reformat-exam-markdown` for **Reformatted Exam Paper**
- `supplement-exam-solutions` for **Supplement Exam Solutions**
- `batch-clean-images` for **Batch Clean Images**
- `render-exam-latex-pdfs` for **Render Exam LaTeX PDFs**

Stop and report a missing-skill gate if a required component skill is unavailable. Do not copy its rules from memory or improvise a substitute workflow.

## Resolve the input folder

1. Resolve the user-provided folder to an absolute path.
2. Before invoking any other component, resolve the candidate exam-page image collection in this order:
   - supported raster images directly inside the selected folder;
   - exactly one nonempty explicit `page-images` or `exam-images` subfolder;
   - `<folder>\images` only when the user identifies it as page scans or no top-level Markdown source references those images.
3. Do not combine separate candidate collections. If multiple explicit candidates remain equally plausible, stop at a page-image input ambiguity gate.
4. Invoke Order Exam Images to PDF and wait for `completed`, `blocked`, `failed`, or `not_applicable`. Do not enumerate or process document stages while stage zero is running.
5. When stage zero is `completed`, invoke Convert Exam PDF to Markdown on its exact verified ordered PDF and wait for a terminal result. Require `ocr_forced: true`, the unchanged ordered-PDF hash, complete page coverage, and a nonempty Markdown output. When stage zero is `not_applicable`, record conversion as `not_applicable`.
6. After conversion succeeds or is not applicable, enumerate `.md` files directly inside the folder. Source paper filenames are unrestricted; do not require `ExamPaper.md`. Do not recursively select Markdown files from subfolders.
7. Before freezing a Markdown file produced by Convert Exam PDF to Markdown, perform a post-conversion OCR handoff audit against the verified ordered PDF. Check question-number continuity within the visible section sequence and require every local Markdown image destination to resolve. Correct only a deterministic OCR or path defect that is directly proven by the ordered page or extracted asset; record the original and repaired Markdown hashes plus the exact corrections. Do not infer an ambiguous number, wording, formula, or missing image.
8. Freeze the source-paper inventory before generating later document outputs. Include the audited Markdown produced by Convert Exam PDF to Markdown. When only the folder is supplied, process every top-level source paper. Exclude an existing derived file only when its exact base-paper sibling proves that it is a prior `（题解整合版）` or `（解析版）` output; do not exclude a standalone paper merely because its name contains those words.
9. Use `<folder>\images` as the exact Markdown attachment folder when it was not classified as the exam-page source collection.
10. For a full Markdown run, require at least one source paper and its required attachment folder. For an explicitly requested single branch, require only that branch's input after stage zero and conversion.
11. Treat every resolved source paper, every exam-page image, and the ordered PDF as read-only source artifacts after creation. Treat a Markdown attachment folder as mutable only through `batch-clean-images`, which must first create its required complete original-image backup and then replace successful images in place.
12. Do not create backups except for the mandatory `batch-clean-images` original-image backup. Other component skills write recoverable outputs while preserving their sources.

If the user supplies only the folder path with no narrower stage request, run the full organizer workflow.

An image-only folder is valid input. After stage zero succeeds, convert its ordered PDF to Markdown with MinerU forced OCR; do not skip Markdown-dependent stages merely because no Markdown predated the current run.

## Resume a recorded run

Treat an explicit continuation of the same organizer task, or a user-supplied run manifest, as a resume request. Do not interpret an unrelated request for the same folder as permission to reuse old state.

1. Read [references/pipeline-state-schema.md](references/pipeline-state-schema.md).
2. Run `scripts/validate_pipeline_state.py <folder> <pipeline-state.json>` before reusing any stage.
3. Reuse a completed stage only when the manifest schema is supported, its resolved folder matches, every recorded artifact required by that stage still exists with the recorded SHA-256 hash, and its dependency statuses remain valid.
4. Resume at the first incomplete, failed, blocked, or stale stage. Preserve valid completed stages and never rerun them blindly.
5. Never rerun a completed Batch Clean Images stage during resume. Reusing it requires the complete backup, replacement mappings, replacement hashes, and failure list to validate; otherwise mark the image stage stale and stop for user direction before modifying images again.
6. Start a fresh run when validation fails before any reusable stage can be proven. Do not silently merge two run IDs or copy successful flags from an older manifest.

## Dispatch requests

- **Fresh organizer request:** Run Order Exam Images to PDF first and wait for its terminal gate. If it completes, run Convert Exam PDF to Markdown next and wait for its terminal gate.
- **Continuation request:** Validate and consume the named or latest task-scoped `pipeline-state.json`, then resume from its first non-reusable stage.
- **Full organizer:** After ordering and conversion, run the preprocessing phases, wait at the global publishing barrier, then run Render Exam LaTeX PDFs as the final phase.
- **Images only:** After ordering and conversion are terminal, run Batch Clean Images on the Markdown attachment folder only when that branch is applicable.
- **Reformat only:** After ordering and conversion are terminal, run Reformatted Exam Paper on every source paper in the frozen inventory.
- **Solutions requested:** For each source paper, run Reformatted Exam Paper first unless its reformatted candidate was successfully produced and validated earlier in the current task. Then run Supplement Exam Solutions on that paper's reformatted candidate.
- **LaTeX/PDF requested:** Run all missing prerequisite Markdown and image-cleaning phases first. Publish only after the global barrier passes, unless the user explicitly invokes `render-exam-latex-pdfs` as a standalone skill outside this organizer.

Do not make image cleaning a prerequisite for Reformatted Exam Paper or Supplement Exam Solutions. Make it a prerequisite for the organizer's Render Exam LaTeX PDFs phase.

## Enforce the final publishing barrier

Treat `exam-paper-organizer` as the controller, not as a component stage that can literally run before or after itself. Within one organizer invocation, use this phase order:

1. Resolve the selected folder and candidate page-image collection.
2. Run Order Exam Images to PDF once. Record its inventory, semantic order manifest, ordered PDF path and hash, page count, and visual-QA result. Do not start phase 3 until its status is `completed` or `not_applicable`.
3. If phase 2 completed, run Convert Exam PDF to Markdown on the exact ordered PDF. If phase 2 was `not_applicable`, record conversion as `not_applicable`.
4. Audit the conversion-produced Markdown against the ordered PDF for deterministic question-number OCR defects and unresolved local image destinations, record any proven corrections and hash change, then freeze the remaining source inputs.
5. Resolve an answer source for every paper. When no authoritative answer source exists, run the question-only bootstrap below.
6. Run Reformatted Exam Paper for every selected Markdown source.
7. Run Supplement Exam Solutions for every successfully reformatted source.
8. Run Batch Clean Images once on the Markdown attachment folder. It may overlap phases 5-7 for latency, but never phases 2-3, and it must reach a terminal state before phase 9.
9. Audit all Markdown and in-place image-cleaning prerequisites, then run Render Exam LaTeX PDFs last.

Do not dispatch conversion when page ordering is failed, blocked, ambiguous, or unverified. Do not dispatch any Markdown-dependent component when required conversion is failed or blocked. Do not dispatch any render call until all selected papers have terminal statuses for phases 5-6 and Batch Clean Images has returned its complete counts and failed paths. Pass the barrier only when:

- Order Exam Images to PDF is `completed` or `not_applicable`;
- Convert Exam PDF to Markdown is `completed` with `ocr_forced: true`, or `not_applicable` because ordering was `not_applicable`;
- every paper selected for publishing has validated reformatted and solution Markdown editions;
- every raster image referenced by those editions still exists at its unchanged Markdown destination after in-place cleaning, and the Batch Clean Images backup folder contains its original relative path;
- no referenced image appears in the Batch Clean Images failure list;
- every pre-publish layout and provenance check below passes.

Batch Clean Images establishes replacement completion, not visual correctness. Allow `image_quality_status: "unverified"` at this barrier when every required replacement operation succeeded. The renderer's page-by-page visual QA must resolve that status to `passed` or `failed`; publishing is not complete while it remains `unverified`.

If any barrier condition fails, mark rendering `blocked`, preserve successful Markdown and image outputs, and report the exact missing or failed prerequisite. Do not silently render with an original image when a required cleaned image is unavailable.

Write the barrier evidence to `<folder>\tmp\organizer\<run-id>\pipeline-state.json` using [references/pipeline-state-schema.md](references/pipeline-state-schema.md). Include the schema version, run ID, resolved folder, stage statuses, reusable artifact paths and hashes, question-only bootstrap provenance, per-paper reformat and supplement statuses, Batch Clean Images backup folder, counts, failed paths, in-place replacement mappings and hashes, `image_replacement_status`, `image_quality_status`, pre-publish audit results, `eligible_to_render`, render visual-QA status, and `publishing_complete`. Pass this exact manifest path to every publishing worker; do not ask a renderer to infer prerequisite success from filenames alone.

## Scale with sub-agents

Treat the document workload as excessive when there are more than three source papers, or when fewer unusually large or complex papers would make serial execution impractical.

1. Run Order Exam Images to PDF and Convert Exam PDF to Markdown once in the coordinator before assigning any worker. Never split a single collection's ordering or conversion across sub-agents.
2. For an excessive workload, invoke bounded sub-agents and divide the frozen source-paper inventory into balanced, non-overlapping batches. Keep each paper's Markdown preprocessing with one owner; never assign the same paper to multiple preprocessing agents.
3. Give every document worker the absolute input folder, exact source-paper paths, selected stages, component-skill paths, stage-zero manifest path, and required per-paper report fields. Require it to read and follow the selected component contracts completely.
4. When Supplement Exam Solutions is selected, prefer `gpt-5.6-sol` document workers so they can generate missing solution material locally. If another worker model is used, it must follow the component skill's required `gpt-5.6-sol` delegation rule. Do not substitute a different model.
5. Respect available concurrency. Use balanced batches rather than creating one agent per paper without limit, and retain capacity needed for required solution-generation delegation.
6. Run Batch Clean Images only once. It may occupy one independent worker while Markdown batches run, but never split its sequential image-editing calls across agents.
7. Require workers to report at stage boundaries with source path, output path, validation status, unresolved items, and next dependency. If a worker becomes unresponsive, recover its artifacts and status before reassigning; never rerun a completed stage blindly.
8. Collect every preprocessing result and the image result before assigning publishing batches. Verify that all frozen source papers have exactly one preprocessing owner and one final status.
9. After the global barrier passes, assign non-overlapping publishing batches. A failed paper or worker does not cancel successful results from other paper batches, but no publisher may bypass the barrier.

## Run Order Exam Images to PDF first

Invoke `order-exam-images-to-pdf` once on the resolved page-image collection before every other component.

- Inventory and hash every source image without treating enumeration order as page order.
- Inspect every image and infer order from question flow, section transitions, split-content continuity, and answer structure. Use page numbers, filenames, timestamps, and EXIF data only as supporting evidence.
- Require one content-based reason for every adjacency and an empty ambiguity list.
- Write the default ordered source PDF as `<folder>\<folder-name>（图片整理版）.pdf` unless the user names another path.
- Keep inventory, order manifest, ordered preview, and merge report under `<folder>\tmp\organizer\<run-id>\image-ordering`.
- Render the PDF and inspect every page before marking the stage complete.
- Preserve every source image and its hash. Do not overwrite a pre-existing PDF without explicit approval.

If the collection is absent, record `not_applicable` and continue. If input classification, semantic order, source integrity, merge validation, or visual QA fails, block the entire remaining organizer workflow.

## Run Convert Exam PDF to Markdown second

When Order Exam Images to PDF completes, invoke `convert-exam-pdf-to-markdown` on the exact verified ordered PDF.

- Require the stage-zero ordered PDF path and SHA-256 hash as inputs.
- Force MinerU OCR through `file.is_ocr: true`; do not allow an OCR-off override.
- Keep `model_version: "vlm"`, `language: "ch"`, `enable_formula: true`, and `enable_table: true`.
- Write the default Markdown beside the ordered PDF and extracted assets under `images/<ordered-pdf-stem>/`.
- Require complete split-part page coverage, a nonempty Markdown output, committed assets, and an unchanged ordered-PDF hash.
- Add the completed Markdown output to the source-paper inventory before freezing it.

If stage zero is `not_applicable`, mark conversion `not_applicable`. If conversion fails or is blocked, do not invoke Reformatted Exam Paper, Supplement Exam Solutions, or Render Exam LaTeX PDFs for the missing generated source.

## Run Batch Clean Images independently

Invoke `batch-clean-images` with `<folder>\images`.

- Create one new `original-images-backup-<timestamp>` folder inside `<folder>\images` and copy every source image into it with the original relative path before any replacement begins.
- Replace each successfully edited image directly at its original path with the same filename and extension. Do not create `images-cleaned` and do not change any Markdown image destination.
- Process image-editing calls sequentially as required by the component skill.
- Give each image-editing call a bounded operational timeout. On timeout, record that source as failed, do not retry it, and continue the remaining images.
- Record successful operational completion as `image_replacement_status: "completed"` and the accepted-but-uninspected result as `image_quality_status: "unverified"`. Do not claim visual or transparency validation at this stage.
- Let this branch succeed or fail independently from Markdown preprocessing. Its final result authorizes or blocks publishing through the global barrier.

## Run the document chain

### 0. Bootstrap a question-only paper

Use this stage only when the source paper has no embedded answer section, no explicitly supplied answer attachment, and no unambiguous matching answer file.

1. Inventory the questions before generation.
2. Use `gpt-5.6-sol` under the same model rule as Supplement Exam Solutions to generate a temporary answer-source Markdown file under `<folder>\tmp\organizer\<run-id>\question-only-bootstrap\`.
3. Require one answer entry for every inventoried question ID. Include enough derivation for long-form questions to let the reformatter preserve a usable answer section.
4. Record `answer_source_kind: "generated_bootstrap"`, the generator model, question coverage, unresolved questions, path, and SHA-256 hash in `pipeline-state.json`.
5. Pass the temporary file to `reformat_exam_markdown.py` with `--answers`. Never insert it into or place it beside the original paper.
6. Treat the generated bootstrap as model-generated provenance, not an authoritative supplied answer. Supplement Exam Solutions may reuse it because it was generated by the required model, but must classify its answers and explanations as generated rather than sourced.
7. Block that paper's chain if coverage is incomplete or a required figure is unreadable.

### 1. Reformatted Exam Paper

For each resolved source paper, invoke `reformat-exam-markdown` and follow its parse, generation, review, and validation workflow.

The expected default candidate is:

```text
<folder>\<source-stem>（题解整合版）.md
```

Keep every resolved source paper unchanged. Do not replace one as part of this organizer.

Treat this stage as successful for a paper only when the component skill's structural validation passes and that paper's reformatted candidate exists. If it fails, report the failure and stop only that paper's document chain.

### 2. Supplement Exam Solutions

For each paper, run this stage only after its Reformatted Exam Paper stage succeeds. Pass that paper's reformatted candidate—not its original source paper—to `supplement-exam-solutions`.

The expected default output is:

```text
<folder>\<source-stem>（题解整合版）（解析版）.md
```

Never run Supplement Exam Solutions directly on an original source paper. Never treat Batch Clean Images completion as satisfying this dependency. Follow the component skill's authoritative-answer selection, `gpt-5.6-sol` generation, output-exists gate, source-fidelity rules, and validation requirements.

If the reformatted candidate already exists from outside the current task, do not assume it is valid. Re-run Reformatted Exam Paper unless the user explicitly requests reuse and there is evidence that the candidate passed that skill's validation.

### Pre-publish audit

Before rendering, inspect both derived Markdown editions for defects that structural parsing alone can miss:

- every recognizable A-D choice is a separate list item; no first option remains appended to a stem and no two options share one item;
- table-shaped source data is a real Markdown table rather than a vertical sequence of headings, labels, and values;
- every question has exactly one solution block in the solution edition;
- inserted solution labels use the paper's language, including Chinese labels for a Chinese paper;
- no placeholder, helper note, tool token, or temporary-generation text remains;
- authoritative-answer conflicts and unresolved OCR or figure issues are explicitly recorded and do not masquerade as validated content.

Correct presentation-only defects in the derived editions while preserving wording, values, order, mathematics, and source hashes. Revalidate the affected component stage after correction.

Keep all helper inputs, generated answer fragments, normalized temporary copies, preview pages, and staging artifacts under `<folder>\tmp\organizer\<run-id>`. Never leave helper Markdown files at the folder top level. Remove helper artifacts after terminal reporting; retain only contract outputs and requested previews.

### 3. Render Exam LaTeX PDFs

Run this stage only after the global publishing barrier passes. Invoke `render-exam-latex-pdfs` with explicit paths when the source stem is not `ExamPaper`:

```powershell
python <skill-dir>\scripts\render_exam_pdfs.py <folder> `
  --paper <folder>\<source-stem>（题解整合版）.md `
  --solutions <folder>\<source-stem>（题解整合版）（解析版）.md
```

Apply the paper template to the reformatted edition and the solutions template to the inline worked-solution edition. Require both `.tex` and `.pdf` outputs unless the user explicitly selected one edition.

Pass the validated final Markdown editions directly to the renderer. Batch Clean Images preserves every raster image destination by replacing the referenced file in place, so do not create rendering-only Markdown copies and do not rewrite image paths. Block publishing if a referenced path is missing, its original is absent from the batch backup, or that image appears in the cleaning failure list.

Treat page-by-page rendered-PNG inspection as part of the stage. Pandoc and XeLaTeX success alone do not establish completion. Do not run this stage for a paper whose reformatted or solutions edition is failed, blocked, unresolved, or unvalidated.

Treat outputs created earlier in the same current publishing attempt as provisional: allow the renderer's overwrite mode during the required fix-and-rerender loop. Continue to require explicit user permission before replacing outputs that predated the current task.

After inspection, write `image_quality_status: "passed"` and `publishing_complete: true` only when every selected page is clean. If an image or layout defect is visible, write `image_quality_status: "failed"`, mark the affected render `failed_visual_qa`, keep the PDFs provisional, and report the exact page and asset.

## Failure isolation

- If Order Exam Images to PDF is failed or blocked, do not invoke any other component. Preserve its inventory and evidence, and report the exact ambiguity or validation failure.
- If Convert Exam PDF to Markdown fails or is blocked, preserve the verified ordered PDF, block its Markdown-dependent chain, and report the MinerU or output-exists gate.
- If Batch Clean Images fails, retain Markdown results and the complete original-image backup, block publishing only for papers that reference failed, missing, or unrestorable in-place images, and report the image failures separately.
- If Reformatted Exam Paper fails for one paper, do not run Supplement Exam Solutions for that paper; continue other papers.
- If Supplement Exam Solutions fails for one paper, preserve and report that paper's successful reformatted candidate, do not publish its PDFs, and continue other papers.
- If Render Exam LaTeX PDFs fails for one paper, preserve both successful Markdown editions and every completed publishing artifact; continue other papers.
- Do not overwrite an existing derived output when its component skill requires approval.
- Do not substitute another model or hand-written approximation when a component skill stops at a tool, model, input, or approval gate.

## Report

Return one compact organizer summary containing:

- the absolute input folder, page-image collection decision, frozen source-paper inventory, and Markdown attachment folder;
- the Order Exam Images to PDF status, content-order evidence, ambiguities, ordered PDF, order manifest, source hashes, page count, and visual-QA result;
- the Convert Exam PDF to Markdown status, forced-OCR evidence, ordered-PDF hash, target Markdown, asset root and count, split ranges, and validation result;
- whether sub-agents were used and the non-overlapping paper batches assigned to them;
- the status of Batch Clean Images and each paper's Reformatted Exam Paper, Supplement Exam Solutions, and Render Exam LaTeX PDFs stages as `completed`, `failed`, `skipped`, or `blocked`;
- every question-only bootstrap status, generated-answer provenance, coverage count, and unresolved question;
- each paper's dependency decisions for Supplement Exam Solutions and Render Exam LaTeX PDFs;
- all generated output paths grouped by source paper;
- the image counts and failed image paths reported by Batch Clean Images;
- the global publishing-barrier decision, original-image backup folder, and in-place replacement mapping used by each published paper;
- `image_replacement_status`, `image_quality_status`, `eligible_to_render`, and `publishing_complete` as separate decisions;
- the structural counts, unresolved items, answer-source provenance, conflicts, and question coverage reported by the two document skills;
- the paper and solutions template mapping, `.tex` and `.pdf` paths, page counts, build logs, and visual-QA status reported by the publishing skill;
- any existing-output, missing-input, missing-skill, model-availability, or validation gate that stopped a stage;
- every pre-publish defect found and corrected, plus any remaining blocker;
- confirmation that every exam-page image and resolved source paper remained unchanged, every original Markdown attachment image was preserved in the reported backup folder, successful cleaned images replaced their sources at the same paths, and no Markdown image destination changed.
