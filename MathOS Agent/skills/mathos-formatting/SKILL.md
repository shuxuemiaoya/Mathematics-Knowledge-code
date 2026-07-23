---
name: mathos-formatting
description: Use for MathOS Markdown formatting when Codex needs to normalize TOC-aligned headings, strip the TOC safely, write reviewable candidates, and keep the original source unchanged until explicit replacement approval.
---

# MathOS Formatting

## Overview

This repo-local skill formats MathOS Markdown after conversion and before segmentation. The workflow extracts an immutable verbatim TOC, generates and runs a sandboxed heading processor, strips the recorded TOC span, validates headings, then writes the validated TOC-free Markdown as the candidate.

This skill does not perform concept extraction, chapter-inner content rewriting, reusable content-template creation, or source replacement.

## Quick Reference

Run commands from `C:\Mathematics-Knowledge\Mathematics-Knowledge-code\MathOS Agent`.

| Task | Command |
| --- | --- |
| CLI help | `python skills\mathos-formatting\scripts\mathos_formatting.py --help` |
| Ordinary formatting run | `python skills\mathos-formatting\scripts\mathos_formatting.py run "<source.md>" --env ..\..\.env` |
| Inspect only | `python skills\mathos-formatting\scripts\mathos_formatting.py inspect "<source.md>"` |
| Focused provider diagnosis | `python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "<source.md>" --env ..\..\.env` |

## Workflow SOP

1. Use `run "<source.md>" --env ..\..\.env` for ordinary formatting.
2. Read only `<work-dir>\result-summary.json` after `run` completes.
3. If `status` is `failed`, read only the `error_artifact` path named in that digest. Report `failed_stage`, `source_unchanged`, the one-line cause, the error artifact path, and the next safe action.
4. If `status` is `passed`, report `candidate_path`, `report_path`, and `source_unchanged`.
5. Do not replace the original Markdown automatically. Ask for explicit user approval before replacing the source with `candidate.md`.
6. Run segmentation only after the user authorizes replacement and the candidate has actually replaced the source.

## Provider Stages

1. **Step 1 TOC Extraction**: DeepSeek returns unchanged numbered lines from the first-20-page sample. The runtime validates one complete contiguous span and saves those source lines as immutable `toc.md`.
2. **Step 2 Heading Extraction**: The runtime combines `toc.md` with unprotected body headings in `toc_and_headings.md`.
3. **Step 3 Heading Processing**: DeepSeek returns `heading_processor.py`, which runs only in a temporary sandbox. A separate call returns `heading_expected_result.md` for comparison evidence.
4. **Step 4 TOC Removal**: The runtime deletes the original validated TOC line interval. It never searches modified text for new TOC boundaries.
5. **Step 5 Heading Validation**: DeepSeek validates `heading_check_input.md` as JSON. The runtime also checks heading counts and exact H1-H3 order. Passing Step 5 produces `candidate.md`.

## Runtime Contract

Inputs:

- Source path exists, is a file, ends in `.md`, and is UTF-8 Markdown.
- Provider settings come from `.env`; never print or persist secret values.
- Heading prompts live under `agents\` and are the only active provider prompt surface.

Outputs:

- `inspect`, `learn-from-provider`, and `run` never modify the original source.
- Provider runs write `<work-dir>\candidate.md`, `candidate-report.md`, `run-state.json`, and per-step evidence artifacts.
- Automated `run` additionally writes `result-summary.json` and `automation-checkpoint.json`.
- `result-summary.json` is the only normal agent-readable digest. It contains final status, candidate/report paths, source mutation status, recovery status, preservation status, and either zero or one `error_artifact`.

## Artifact Layout

Provider work directories may include:

- `toc_detection_sample.md`
- `toc_detection_response.md`
- `toc.md`
- `toc_and_headings.md`
- `heading_processor_prompt.md`
- `heading_processor_response.py`
- `heading_processor.py`
- `heading_expected_result.md`
- `stage1_heading_report.md`
- `toc_detection_prompt.md`
- `heading_check_prompt.md`
- `heading_check_input.md`
- `heading_check_response.json`
- `_python-artifact-sandboxes\`
- `candidate.md`
- `candidate-report.md`
- `run-state.json`
- `result-summary.json`
- `automation-checkpoint.json`

## Failure Handling

Stop and keep artifacts when:

- Source is missing, non-Markdown, or unreadable.
- Provider output is invalid Python for the heading processor.
- TOC output is modified, incomplete, disjoint, ambiguous, or includes unrelated text.
- Heading validation JSON is invalid, false, reports errors, or has a count mismatch.
- Heading validation errors contain self-negating text such as `not an error` or the Chinese literal `不是错误`; treat the provider response as internally contradictory and fail closed.
- Python heading artifacts contain dangerous imports or calls.
- Stage 1 validation rejects TOC hierarchy or non-TOC H1-H3 headings.
- TOC stripping would remove preface or body content.
- Heading-only self-check detects source mutation, candidate loss, missing headings, or protected-count regressions.
- Original replacement is attempted without explicit user approval.

Do not weaken validation, silently retry with looser rules, or patch runtime scripts during an ordinary formatting run.

## Critical Rules

- Fail closed on deletion risk.
- Generated heading scripts run only in temporary sandbox directories.
- Never execute generated Python against the original Markdown directory.
- H1-H3 are reserved for TOC-derived structure; non-TOC headings must be H4-H6.
- No heading may receive invented parent or chapter context.
- Never replace the original source without explicit user approval.

## Validation

Before calling formatter changes successful, run:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py --help
python skills\mathos-formatting\scripts\mathos_formatting.py run --help
python -m pytest tests\test_mathos_formatting_guarded.py -q
git diff --check
```
