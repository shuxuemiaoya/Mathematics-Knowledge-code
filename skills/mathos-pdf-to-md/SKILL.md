---
name: mathos-pdf-to-md
description: Use when operating or monitoring PDF to Markdown conversion for the MathOS knowledge-graph build framework.
---

# MathOS PDF To Markdown Operator

Use this skill when the user asks to convert PDFs to Markdown, monitor PDF conversion, inspect a PDF conversion run, or summarize PDF conversion outputs.

## Role

This skill coordinates PDF to Markdown conversion execution for the Knowledge-Graph Implementation Operator.

It monitors operational health and produces output summaries.

It does not judge whether generated Markdown is mathematically correct, academically complete, or well formatted.

It does not create or modify skills.

## Before Running

1. Confirm the user provided an explicit source path or batch target.
2. Confirm the target path exists.
3. Identify the conversion command or Python workflow available in the repository.
4. If no conversion command or Python workflow exists, stop and report that the converter implementation is missing.
5. Identify where logs and outputs will be written.

## Execution Monitoring

Track these signals during the run:

- Process crash.
- Non-zero command exit.
- Failed file count.
- Skipped file count.
- Warning count.
- Missing dependency.
- Missing API key.
- Stalled polling or no progress.
- Missing expected output folder.

## Stop Conditions

Stop the task and preserve logs when any of these conditions occur:

- The Python process crashes.
- The command exits non-zero.
- The missing dependency or missing API key prevents conversion.
- Polling stalls and no progress can be observed.
- The expected output folder is not produced.
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
- Next operational step.

## Save Records

When the run produces useful operational information, save records using:

- `agent-memory/templates/run-summary.md`
- `agent-memory/templates/failure-ledger.json`
- `agent-memory/templates/artifact-index.md`

Use dated filenames so multiple runs can coexist.

## Boundary Reminder

Do not review output Markdown for mathematical correctness.

Do not edit generated Markdown unless the user explicitly asks for content changes through a separate task.

Do not create, modify, or rewrite skills.
