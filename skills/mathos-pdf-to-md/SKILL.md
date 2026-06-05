---
name: mathos-pdf-to-md
description: Use when operating or monitoring PDF to Markdown conversion for the MathOS knowledge-graph build framework.
---

# MathOS PDF To Markdown Operator

Use this skill when the user asks to convert PDFs to Markdown, monitor PDF conversion, inspect a PDF conversion run, or summarize PDF conversion outputs.

## Role

This skill coordinates PDF to Markdown conversion execution for the Knowledge-Graph Implementation Operator through the repo-local MinerU Python arm.

It monitors operational health and produces output summaries.

It does not judge whether generated Markdown is mathematically correct, academically complete, or well formatted.

It does not judge generated content quality.

## Python Workflow

Fast plan before conversion:

```powershell
python .\skills\mathos-pdf-to-md\scripts\mathos_pdf_to_md.py plan `
  "<PDF file or document directory>" `
  --source-base "<source base to strip>" `
  --output-root "<optional output root>" `
  --yes
```

The `plan` command does not call MinerU. It returns compact JSON with pending files, skipped files, and the exact next conversion command.

Use this command shape:

```powershell
python .\skills\mathos-pdf-to-md\scripts\mathos_pdf_to_md.py convert `
  "<PDF file or document directory>" `
  --source-base "<source base to strip>" `
  --output-root "<optional output root>" `
  --yes
```

Implementation module:

```text
skills/mathos-pdf-to-md/scripts/mathos_pdf_to_md.py
```

The workflow reads `MINERU_API_KEY` from:

```text
C:\Mathematics-Knowledge\.env
```

Do not print or save the API key.

## Before Running

1. Confirm the user provided an explicit source PDF or directory.
2. Ask for the `source_base` for this run. The output hierarchy is preserved relative to this path.
3. If `--output-root` is not provided, confirm the remembered output root from `skills/mathos-pdf-to-md/config.json`.
4. Confirm `C:\Mathematics-Knowledge\.env` contains `MINERU_API_KEY`.
5. Confirm the source directory is under `source_base`.
6. Confirm where run records will be written under `agent-memory/records/`.

## Conversion Behavior

- If the source is a single PDF, process only that PDF.
- If the source is a directory, traverse it recursively.
- Process only `.pdf` files.
- For `xxx.pdf`, write `xxx.md` in the mirrored output directory.
- If `xxx.md` already exists, skip that PDF.
- Force MinerU OCR with `file.is_ocr: true`.
- Use `model_version: "vlm"`, `language: "ch"`, `enable_formula: true`, and `enable_table: true`.
- Process up to 10 PDFs concurrently by default, controlled by `MAX_PARALLEL_TASKS`.
- Use MinerU local batch upload API with at most 50 files per upload-url request.
- Split PDFs over 200 pages or 200 MB before upload, then merge the returned Markdown parts in page order.
- Copy extracted assets under `images/<pdf-stem>/`; split parts use `images/<pdf-stem>/part-###/` to avoid collisions.

## Execution Monitoring

Read `run-state.json` first. It is the compact machine-readable run status and includes counts, output paths, retryable failures, permanent failures, and the next retry command.

Track these signals during the run:

- Process crash.
- Non-zero command exit.
- Failed file count.
- Skipped file count.
- Warning count.
- Missing dependency.
- Missing or invalid API key.
- Stalled polling or no progress.
- Missing expected output folder.
- Missing `full.md` in a MinerU result zip.
- MinerU API errors or failed task states.

## Stop Conditions

Stop the task and preserve logs when any of these conditions occur:

- The Python process crashes.
- The command exits non-zero.
- The missing dependency or missing API key prevents conversion.
- Polling stalls and no progress can be observed.
- The expected output folder or target Markdown is not produced.
- A MinerU result zip does not contain `full.md`.
- Failed conversions are numerous enough that continuing is not useful.

When exact failure thresholds are unavailable, use this default rule:

```text
Stop when failed files are at least 5 and at least 30% of attempted files.
```

If fewer than 5 files were attempted, stop after 2 failed files.

## Required Output Summary

Every completed or stopped run must include:

- Stage name: `pdf-to-md`.
- Skill: `skills/mathos-pdf-to-md`.
- Source path.
- Command or Python workflow used.
- Completion status.
- Stop reason, if stopped.
- Output folder paths.
- Log paths.
- Counts for attempted, converted, failed, skipped, and warning items.
- Representative failure categories.
- Split-part counts and merge status when a source PDF was split.
- Next operational step.

## Save Records

When the run produces useful operational information, save records using:

- `agent-memory/templates/run-summary.md`
- `agent-memory/templates/failure-ledger.json`
- `agent-memory/templates/artifact-index.md`

The Python workflow writes run records under `agent-memory/records/<date>-pdf-to-md-<slug>/`.

Each run writes `run-state.json` for fast monitoring and resume decisions. Prefer it over reading full manifests unless details are needed.

## Boundary Reminder

Do not review output Markdown for mathematical correctness.

Do not edit generated Markdown unless the user explicitly asks for content changes through a separate task.

Do not create, modify, or rewrite skills.
