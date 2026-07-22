---
name: exam-paper-organizer
description: Orchestrate a complete exam-paper workflow from a folder containing one or many arbitrarily named source Markdown papers and an `images` attachment folder. Use when Codex must batch-run any combination of the installed `reformat-exam-markdown`, `supplement-exam-solutions`, `render-exam-latex-pdfs`, and `batch-clean-images` skills, delegating excessive paper volumes to bounded sub-agents. Enforce per-paper reformatting, then solution supplementation, then polished LaTeX/PDF publishing, while allowing Batch Clean Images to run independently.
---

# Exam Paper Organizer

Coordinate the four installed component skills without replacing or weakening their live contracts.

## Load component contracts

Before performing a selected stage, read the corresponding installed `SKILL.md` completely and follow it as authoritative:

- `reformat-exam-markdown` for **Reformatted Exam Paper**
- `supplement-exam-solutions` for **Supplement Exam Solutions**
- `render-exam-latex-pdfs` for **Render Exam LaTeX PDFs**
- `batch-clean-images` for **Batch Clean Images**

Stop and report a missing-skill gate if a required component skill is unavailable. Do not copy its rules from memory or improvise a substitute workflow.

## Resolve the input folder

1. Resolve the user-provided folder to an absolute path.
2. Enumerate `.md` files directly inside the folder. Source paper filenames are unrestricted; do not require `ExamPaper.md`. Do not recursively select Markdown files from subfolders.
3. Freeze the source-paper inventory before generating any outputs. When only the folder is supplied, process every top-level source paper. Exclude an existing derived file only when its exact base-paper sibling proves that it is a prior `（题解整合版）` or `（解析版）` output; do not exclude a standalone paper merely because its name contains those words.
4. Report a missing-input gate only when the frozen inventory is empty. Several source papers are a batch, not an ambiguity gate.
5. Use `<folder>\images` as the exact source image folder.
6. For a full run, require at least one source paper and the image folder. For an explicitly requested single branch, require only that branch's input.
7. Treat every resolved source paper and everything under `images` as read-only source artifacts.
8. Do not create backups. Each component skill writes recoverable sibling outputs while preserving its source.

If the user supplies only the folder path with no narrower stage request, run the full organizer workflow.

## Dispatch requests

- **Full organizer:** Run Batch Clean Images once as an independent branch and run the document chain `Reformatted Exam Paper -> Supplement Exam Solutions -> Render Exam LaTeX PDFs` for every source paper.
- **Images only:** Run only Batch Clean Images on `<folder>\images`.
- **Reformat only:** Run Reformatted Exam Paper on every source paper in the frozen inventory.
- **Solutions requested:** For each source paper, run Reformatted Exam Paper first unless its reformatted candidate was successfully produced and validated earlier in the current task. Then run Supplement Exam Solutions on that paper's reformatted candidate.
- **LaTeX/PDF requested:** For each selected paper, require validated reformatted and solution Markdown editions. Run missing prerequisite document stages first, then publish both editions unless the user explicitly requests one.

Do not make image cleaning a prerequisite for either document stage. Do not rewrite Markdown image links to the cleaned-image folder unless the user separately requests that content change.

## Scale with sub-agents

Treat the document workload as excessive when there are more than three source papers, or when fewer unusually large or complex papers would make serial execution impractical.

1. For an excessive workload, invoke bounded sub-agents and divide the frozen source-paper inventory into balanced, non-overlapping batches. Keep each paper's complete document and publishing chain with one owner; never assign the same paper to multiple agents.
2. Give every document worker the absolute input folder, exact source-paper paths, selected stages, component-skill paths, and required per-paper report fields. Require it to read and follow the selected component contracts completely.
3. When Supplement Exam Solutions is selected, prefer `gpt-5.6-sol` document workers so they can generate missing solution material locally. If another worker model is used, it must follow the component skill's required `gpt-5.6-sol` delegation rule. Do not substitute a different model.
4. Respect available concurrency. Use balanced batches rather than creating one agent per paper without limit, and retain capacity needed for required solution-generation delegation.
5. Run Batch Clean Images only once. It may occupy one independent worker while document batches run, but never split its sequential image-editing calls across agents.
6. Collect every worker's result, verify that all frozen source papers have exactly one owner and one final status, then aggregate the organizer report. A failed paper or worker does not cancel successful results from other paper batches.

## Run Batch Clean Images independently

Invoke `batch-clean-images` with `<folder>\images`.

- Keep every source image unchanged.
- Use its default sibling output folder `<folder>\images-cleaned` unless the user names another output folder.
- Process image-editing calls sequentially as required by the component skill.
- Let this branch succeed or fail independently. Its result must not authorize, block, or invalidate the document chain.

## Run the document chain

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

### 3. Render Exam LaTeX PDFs

For each paper, run this stage only after both preceding Markdown stages succeed. Invoke `render-exam-latex-pdfs` with explicit paths when the source stem is not `ExamPaper`:

```powershell
python <skill-dir>\scripts\render_exam_pdfs.py <folder> `
  --paper <folder>\<source-stem>（题解整合版）.md `
  --solutions <folder>\<source-stem>（题解整合版）（解析版）.md
```

Apply the paper template to the reformatted edition and the solutions template to the inline worked-solution edition. Require both `.tex` and `.pdf` outputs unless the user explicitly selected one edition.

Treat page-by-page rendered-PNG inspection as part of the stage. Pandoc and XeLaTeX success alone do not establish completion. Do not run this stage for a paper whose reformatted or solutions edition is failed, blocked, unresolved, or unvalidated.

## Failure isolation

- If Batch Clean Images fails, continue or retain the document-chain result and report the image failures separately.
- If Reformatted Exam Paper fails for one paper, do not run Supplement Exam Solutions for that paper; continue other papers.
- If Supplement Exam Solutions fails for one paper, preserve and report that paper's successful reformatted candidate, do not publish its PDFs, and continue other papers.
- If Render Exam LaTeX PDFs fails for one paper, preserve both successful Markdown editions and every completed publishing artifact; continue other papers.
- Do not overwrite an existing derived output when its component skill requires approval.
- Do not substitute another model or hand-written approximation when a component skill stops at a tool, model, input, or approval gate.

## Report

Return one compact organizer summary containing:

- the absolute input folder, frozen source-paper inventory, and source image folder;
- whether sub-agents were used and the non-overlapping paper batches assigned to them;
- the status of Batch Clean Images and each paper's Reformatted Exam Paper, Supplement Exam Solutions, and Render Exam LaTeX PDFs stages as `completed`, `failed`, `skipped`, or `blocked`;
- each paper's dependency decisions for Supplement Exam Solutions and Render Exam LaTeX PDFs;
- all generated output paths grouped by source paper;
- the image counts and failed image paths reported by Batch Clean Images;
- the structural counts, unresolved items, answer-source provenance, conflicts, and question coverage reported by the two document skills;
- the paper and solutions template mapping, `.tex` and `.pdf` paths, page counts, build logs, and visual-QA status reported by the publishing skill;
- any existing-output, missing-input, missing-skill, model-availability, or validation gate that stopped a stage;
- confirmation that every resolved source paper and the source `images` folder remained unchanged.
