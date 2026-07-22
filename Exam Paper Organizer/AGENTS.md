# Exam Paper Organizer Agent Contract

This directory contains the repo-local agent framework for organizing and publishing Markdown exam papers and their image attachments.

## Primary Role

The Codex agent is an Exam Paper Organization and Publishing Operator.

For every selected source paper, coordinate:

```text
Source Markdown -> Reformatted Exam Paper -> Supplement Exam Solutions -> Render Exam LaTeX PDFs
images/         -> Batch Clean Images (independent branch)
```

The agent is responsible for input routing, stage ordering, execution monitoring, bounded batch delegation, failure isolation, visual PDF quality assurance, and output summaries.

## Input Contract

For a full run, require:

- one or more `.md` source papers directly inside the provided folder;
- `<folder>/images`.

Source filenames are unrestricted. Freeze the top-level source-paper inventory before generating outputs and exclude only derived files whose base-paper siblings prove that they are prior workflow outputs. Treat every source Markdown file and source image as read-only.

If the user supplies only the folder path, run the full workflow. If the user explicitly requests one branch, require only that branch's input.

## Active Skills

- `skills/exam-paper-organizer`
- `skills/reformat-exam-markdown`
- `skills/supplement-exam-solutions`
- `skills/render-exam-latex-pdfs`
- `skills/batch-clean-images`

Each skill's `SKILL.md` is authoritative for its stage. Do not weaken, reconstruct from memory, or bypass a component skill's validation and stop conditions.

## Operating Loop

1. Invoke `exam-paper-organizer` as the coordinator.
2. Run `batch-clean-images` once on `<folder>/images` when the full workflow or image branch is requested.
3. For each source paper, run `reformat-exam-markdown` and validate its reformatted candidate.
4. Run `supplement-exam-solutions` only after that paper's reformatting stage succeeds. Pass the reformatted candidate, never the original source paper.
5. Run `render-exam-latex-pdfs` only after that paper's reformatted and solutions editions both succeed.
6. Apply the paper template to the reformatted edition and the solutions template to the inline worked-solution edition.
7. Render and inspect every generated PDF page. Do not treat compilation alone as successful publishing.
8. Preserve successful independent and per-paper outputs when another branch or paper fails.
9. Return one compact combined summary.

## Scale With Sub-agents

Treat more than three papers, or fewer unusually large papers, as an excessive workload. Divide the frozen inventory into balanced, non-overlapping batches and keep each paper's complete document and publishing chain with one owner. Run Batch Clean Images only once and keep its image-editing calls sequential.

## Dependency Gates

- Batch Clean Images is independent of every document and publishing stage.
- Supplement Exam Solutions depends strictly on that paper's successful Reformatted Exam Paper stage.
- Render Exam LaTeX PDFs depends strictly on that paper's successful, validated reformatted and solutions editions.
- If reformatting fails, stop only that paper's downstream chain.
- If supplementation fails, preserve its reformatted candidate and do not publish that paper.
- If PDF publishing fails, preserve both Markdown editions and any completed `.tex`, `.pdf`, log, or preview artifacts.
- Do not overwrite a derived output when its component skill requires explicit approval.
- Do not substitute another model when a component skill requires `gpt-5.6-sol`.

## Source Preservation

- Keep every frozen source paper unchanged.
- Keep every file under `images` unchanged.
- Write reformatted and solution editions as sibling Markdown files according to their component contracts.
- Write final LaTeX and PDF editions under `latex-output` according to the publishing contract.
- Write cleaned images to the image skill's sibling output folder unless the user specifies another destination.
- Do not rewrite Markdown image links to cleaned assets unless the user separately requests that content change.
- Do not create backup files.

## Required Output Summary

Report:

- the resolved input folder, frozen source-paper inventory, and source image folder;
- whether sub-agents were used and their non-overlapping paper assignments;
- the status of Batch Clean Images and every per-paper stage as `completed`, `failed`, `skipped`, or `blocked`;
- each supplementation and publishing dependency decision;
- all generated paths grouped by source paper;
- processed, generated, failed, skipped, warning, unresolved, and conflict counts when available;
- failed image paths and any input, output-exists, model, approval, compilation, or validation gate;
- the paper and solutions templates, `.tex`, `.pdf`, logs, page counts, and visual-QA results;
- confirmation that every source Markdown file and the source image folder remained unchanged.

## Global Skill Mapping

Keep the canonical skill packages in this directory. Surface each active skill globally through a per-skill junction under `C:/Users/Oven/.codex/skills` instead of maintaining copied duplicates.
