---
name: mathos-formatting
description: Use for MathOS Markdown formatting when provider-generated Python artifacts must normalize TOC-aligned headings, strip the TOC safely, preserve protected Markdown regions, produce self-check candidates, or save/reuse approved formatting programs without replacing the original source.
---

# MathOS Formatting

## Overview

This repo-local skill formats MathOS Markdown after conversion and before segmentation. Stage 1 uses DeepSeek to extract an immutable verbatim TOC, generate a sandboxed heading processor, delete the recorded TOC span, and validate the final heading structure. Stage 2 then applies the generated content processor. Candidate-producing commands never replace the original Markdown file.

## When To Use

Use this skill when a MathOS `.md` file needs:

- Structure inspection before formatting.
- Provider-backed heading normalization according to the TOC.
- TOC stripping with preface/body preservation.
- Chapter-inner Markdown cleanup through a generated Python batch processor.
- A self-check candidate and report before segmentation.
- An approved reusable formatting program for the same source family.
- Diagnosis of heading, TOC, protected-region, Python-artifact, or preservation failures.

## When Not To Use

Do not use this skill for:

- PDF or Word conversion.
- Segmentation or graph building.
- Mathematical correctness review.
- Summarization, translation, rewriting, answer generation, or educational-content deletion.
- Non-Markdown files.
- Replacing the original Markdown file without explicit user approval for that exact replacement.
- Editing files under `skills/mathos-formatting/scripts/` during an ordinary formatting run. Script changes require a separate explicit development request.

## Quick Reference

Run commands from `C:\Mathematics-Knowledge\Mathematics-Knowledge-code`.

| Task | Command |
| --- | --- |
| CLI help | `python skills\mathos-formatting\scripts\mathos_formatting.py --help` |
| Fully automated run | `python skills\mathos-formatting\scripts\mathos_formatting.py run "<source.md>" --env ..\.env` |
| Inspect only | `python skills\mathos-formatting\scripts\mathos_formatting.py inspect "<source.md>"` |
| Learn Python artifacts | `python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "<source.md>" --env ..\.env` |
| Learn into explicit work dir | `python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "<source.md>" --env ..\.env --work-dir "<work-dir>" --timeout-seconds 120 --h1-index 0` |
| Build candidate from Python artifacts | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-script "<work-dir>\heading_processor.py" --content-script "<work-dir>\content_processor.py"` |
| Build candidate with title map | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-script "<work-dir>\heading_processor.py" --content-script "<work-dir>\content_processor.py" --title-rewrite-map "<work-dir>\title_rewrite_map.py"` |
| Save approved Python program | `python skills\mathos-formatting\scripts\mathos_formatting.py approve --approved-root skills\mathos-formatting\plugins\approved --plugin-id "<program-id>" --heading-script "<work-dir>\heading_processor.py" --content-script "<work-dir>\content_processor.py" --title-rewrite-map "<work-dir>\title_rewrite_map.py" --original "<source.md>" --candidate "<candidate.md>" --summary "self-check passed"` |
| Apply approved program | `python skills\mathos-formatting\scripts\mathos_formatting.py apply-approved "skills\mathos-formatting\plugins\approved\<program-id>" "<source.md>"` |
| Legacy JSON candidate | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-rules "<old>\heading_rules.json" --content-rules "<old>\content_rules.json"` |

## Workflow SOP

1. Prefer `run` for ordinary single-file formatting. It executes provider learning, conservative recovery, deterministic self-checking, and final judgment in one process.
2. Read only `<work-dir>\result-summary.json` after `run` completes.
3. When its status is `failed`, read only the path in `error_artifact`; do not load all intermediate artifacts into the agent context.
4. Use `learn-from-provider` directly only for development or focused diagnosis.
5. Use `candidate-from-artifacts` after editing generated Python artifacts.
6. Save a reusable program only when `result-summary.json` has `safe_to_approve: true`.
7. Ask separately before replacing the original Markdown with the candidate. Keep an audit backup such as `original-before-formatting.md` when replacement is approved.
8. Run segmentation only after the approved candidate has explicitly replaced the source.

## Provider Stages

1. **Stage 1 TOC Extraction**: DeepSeek returns unchanged numbered lines from the first-20-page sample. The runtime validates one complete contiguous span and saves those source lines as immutable `toc.md`.
2. **Stage 1 Heading Processor**: The runtime combines `toc.md` with all unprotected body headings in `toc_and_headings.md`. It sends that exact payload to DeepSeek twice: the first call returns `heading_processor.py`, which runs only in a temporary sandbox; the independent second call returns the explanatory `heading_expected_result.md`.
3. **Stage 1 Removal And Validation**: The runtime deletes the original recorded TOC line interval, builds `heading_check_input.md`, and requires passing DeepSeek JSON before continuing.
4. **Stage 2 Content Processor**: DeepSeek returns `content_processor.py`, which runs against the validated, TOC-free candidate. Later stages may not modify headings.

## Runtime Module Layout

`scripts\learning_pipeline.py` is orchestration only. The current workflow has one implementation module per step:

1. `step1_toc_extraction.py` - first-20-page extraction, provider call, verbatim TOC validation, and `toc.md`.
2. `step2_heading_extraction.py` - protected heading extraction and `toc_and_headings.md`.
3. `step3_heading_processing.py` - heading processor generation, expected-result generation, sandbox execution, and invariant checks.
4. `step4_toc_removal.py` - deletion by the original validated TOC interval.
5. `step5_heading_validation.py` - final heading payload, provider check, and JSON validation.
6. `step6_content_processing.py` - Stage 2 content generation, runtime protection, execution, and preservation checks.

Compatibility-only behavior is isolated under `legacy_heading_rules.py`, `legacy_title_map.py`, and `legacy_toc_helpers.py`. Shared report generation lives in `reporting.py`.

## Input And Output Contract

Inputs:

- Source path exists, is a file, ends in `.md`, and is UTF-8 Markdown.
- Provider learning reads secrets from `.env`; never print or persist secret values.
- Stage 1 heading and Stage 2 content artifacts are Python batch scripts.
- `heading_expected_result.md` is a validated explanatory artifact. It records the modified TOC, change details, and expected effect, but does not drive candidate mutation or replace Step 5 validation.
- Stage 1 TOC output is verbatim Markdown; Stage 1 validation output is JSON.

Outputs:

- `inspect`, `learn-from-provider`, `candidate-from-artifacts`, and `apply-approved` do not modify the original source.
- Provider learning writes `<work-dir>\candidate.md`, reports, generated artifacts, and `run-state.json`.
- Automated `run` additionally writes `<work-dir>\result-summary.json` and `automation-checkpoint.json`.
- `result-summary.json` is the only normal agent-readable artifact. It contains final status, self-check booleans, candidate/report paths, recovery status, and either zero or one `error_artifact`.
- Artifact/application runs write a fresh candidate under the source directory's `mathos-formatting` area.
- Approved programs are written under `skills\mathos-formatting\plugins\approved\<program-id>\`.
- CLI JSON includes status, candidate path, report path, warnings, `self_check_required`, and `next_actions`.

## Artifact Layout

Provider learning work directories may include:

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
- `h1_sample.md`
- `content_cleaner_prompt.md`
- `content_processor_response.py`
- `content_processor.py`
- `_python-artifact-sandboxes\`
- `candidate.md`
- `candidate-report.md`
- `run-state.json`
- `result-summary.json`
- `automation-checkpoint.json`

## Automated Run Contract

`run` leaves the source unchanged and returns `0` only when deterministic self-checking passes. It returns nonzero after writing a failure digest when any stage or self-check fails.

Recovery is guarded by a SHA-256 execution fingerprint covering the source bytes, heading and content prompts, provider identity, timeout, and selected H1 sample. A matching fingerprint may reuse the generated `heading_processor.py` and `content_processor.py`. A mismatch removes those reusable processors from the selected work directory before restarting the provider pipeline.

On success, `result-summary.json` contains `status: passed`, `safe_to_approve: true`, and no error artifact. On failure it contains `status: failed`, `failed_stage`, `safe_to_approve: false`, and exactly one `error_artifact`. Codex should inspect that one artifact and no others unless a human explicitly requests deeper diagnosis.

Approved Python program directories contain:

- `heading_processor.py`
- `content_processor.py`
- `title_rewrite_map.py` optional
- `metadata.json`
- `approval.md`
- `sample_before.md`
- `sample_after.md`

Legacy directories may contain `heading_rules.json`, `content_rules.json`, `content_cleaner.py`, or `heading_optimizations.json`. Those are compatibility only.

## Python Artifact Contract

Stage 1 heading and Stage 2 content Python scripts must:

- Start with `import os`.
- Include `from pathlib import Path` and `import re`.
- Define `get_target_root()`, `protect_blocks()`, `restore_blocks()`, `replace_in_file()`, and `main()`.
- Read a target root from stdin and process Markdown files under that root.
- Preserve display math, code fences, YAML frontmatter, markdown tables, headings where required, and other protected blocks.
- Run only inside the runtime-created temporary sandbox.

Legacy explicit title-map commands may still consume:

```python
TITLE_REWRITE_MAP: dict[str, str] = {
    "## Review Questions 5": "#### Chapter 5 Review Questions 5",
}
```

Every key and value must be a Markdown heading line. Values may keep the same level or downgrade to H4-H6.

## Protected Regions

The self-check loop must protect or validate:

- Immutable `toc.md` and the original validated TOC line interval.
- Display math blocks delimited by `$$` or `\[` and `\]`.
- Fenced code blocks using backticks or tildes.
- YAML frontmatter.
- Markdown table lines.
- Image references.
- HTML `<details>` blocks unless the user has explicitly changed the content contract and tests for that behavior.
- Heading lines during Stage 2 content cleanup.

## Critical Rules

- Fail closed on deletion risk.
- Generated heading/content scripts run only in temporary sandbox directories.
- Never execute generated Python against the original Markdown directory.
- Never accept a Python artifact that imports network, subprocess, shell, or unsafe filesystem modules.
- Reject artifacts that call `open`, `eval`, `exec`, external commands, delete, move, rename, or recursively copy files.
- Stage 1 processing must preserve line count, non-heading content, protected blocks, heading count, and heading order.
- TOC deletion uses the original validated line interval; it never searches modified text for new boundaries.
- DeepSeek heading validation must pass before Stage 2 begins.
- H1-H3 are reserved for TOC-derived structure; non-TOC headings must be H4-H6.
- No heading may receive newly invented parent or chapter context.
- Do not prepend or rewrite any parent or chapter prefix for headings that lack parent context (e.g., an independent "Exercise" heading should remain "Exercise" when downgraded, and must not be rewritten to include parent information like "Chapter X Exercise").
- `learn-from-provider` does not generate or apply a late `TITLE_REWRITE_MAP`; explicit legacy artifact commands remain compatible.
- Never save a reusable program until the candidate passes self-check.
- Never replace the original source without explicit approval.

## Failure Handling

Stop and keep artifacts when:

- Source is missing, non-Markdown, or unreadable.
- Provider output is invalid Python for the heading or content processor.
- TOC output is modified, incomplete, disjoint, ambiguous, or includes unrelated text.
- Heading validation JSON is invalid, false, reports errors, or has a count mismatch.
- Heading validation errors contain self-negating text such as `not an error` or the Chinese literal `不是错误`; treat the provider response as internally contradictory and fail closed.
- Python artifact is missing required imports or functions.
- Python artifact contains dangerous imports or calls.
- Stage 1 validation rejects TOC hierarchy or non-TOC H1-H3 headings.
- TOC stripping would remove preface or body content.
- Candidate becomes too short or preservation counts drop.
- Display math, code fence, YAML, table, image, details, or heading preservation fails.
- Approved-program saving is attempted before self-check passes.
- Original replacement is attempted without explicit user approval.

Do not weaken validation, silently retry with looser rules, or patch runtime scripts during a formatting run.

## Validation

Before calling the work successful, run:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py --help
python -m pytest tests\test_mathos_formatting_guarded.py -q
rg "content_rules.json|heading_rules.json|heading_optimizations.json" skills\mathos-formatting tests
```

The final `rg` should show only explicit legacy compatibility references.

Required validation coverage:

- Accidental TOC deletion is caught.
- Heading level judgment is checked against TOC-derived structure.
- Display math, code fences, YAML frontmatter, and tables are protected.
- Invalid heading-check JSON is rejected before Stage 2.
- Invalid provider Python is rejected for heading and content processors.
- Candidate-too-short or content-loss output fails closed.
- Original file cannot be replaced without explicit user approval.
- Dangerous Python artifacts are rejected, including `os.remove`, `subprocess`, arbitrary write `open`, network imports/calls, and missing required functions.
- Generated scripts only affect sandbox candidate copies.
- Provider learning produces no late title-map artifact.
- Legacy approved programs still apply through the compatibility branch.

## Review And Approval Workflow

Manual review is not the acceptance gate. Candidate-producing commands set `self_check_required: true`; the agent must complete the skill self-check loop:

1. Read `run-state.json`, `candidate.md`, and the report.
2. Confirm the original file was not modified.
3. Verify immutable TOC evidence, stored boundaries, and the passing heading-check response.
4. Verify preservation counts and protected-region behavior.
5. Confirm candidate length is plausible.
6. If all checks pass, save the approved program.
7. Ask separately before replacing the original source with the candidate.
8. **Save Generalized Formatting Templates**: If the approved program is intended to serve as a general formatting specification for a book family (e.g., textbook-family-v1), clean the plugin directory after `approve` completes. Go to `skills/mathos-formatting/plugins/approved/<program-id>` and manually delete the book-specific `heading_processor.py` and sample comparison files (`sample_before.md`, `sample_after.md`). Keep only the generalized Stage 2 `content_processor.py`, `metadata.json`, and `approval.md`.

## Reuse Approved Programs

Use `apply-approved` only for sources from the same self-check-passing family.

Reuse behavior:

- Directory deletion and heading adjustment stages cannot be reused; only the Stage 2 content processor (`content_processor.py`) can be reused.
- For other books in the same family, you cannot directly apply the entire program using `apply-approved`. You must run TOC extraction, heading processing, and heading validation individually for each book, but you can reuse the approved `content_processor.py` during `learn-from-provider` (or by manually compiling candidates from artifacts).
- **Generalized Template Pruning**: When creating a family-wide general formatting template, manually prune the plugin folder to remove all book-specific files (e.g., `heading_processor.py`) and comparison samples, leaving only `content_processor.py`, `metadata.json`, and `approval.md`.
- Prefer `heading_processor.py` and `content_processor.py`.
- Apply `title_rewrite_map.py` when present.
- Fall back to legacy JSON or legacy `content_cleaner.py` only when no Python artifacts exist.
- Create a fresh candidate and report.
- Leave the original source untouched until explicit replacement approval.

## Examples

Learn:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "C:\path\book.md" --env "C:\Mathematics-Knowledge\.env" --work-dir "C:\path\mathos-formatting\book"
```

Rebuild from Python artifacts:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "C:\path\book.md" --heading-script "C:\path\mathos-formatting\book\heading_processor.py" --content-script "C:\path\mathos-formatting\book\content_processor.py" --title-rewrite-map "C:\path\mathos-formatting\book\title_rewrite_map.py"
```

Approve:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py approve --approved-root skills\mathos-formatting\plugins\approved --plugin-id "textbook-family-v1" --heading-script "C:\path\mathos-formatting\book\heading_processor.py" --content-script "C:\path\mathos-formatting\book\content_processor.py" --title-rewrite-map "C:\path\mathos-formatting\book\title_rewrite_map.py" --original "C:\path\book.md" --candidate "C:\path\mathos-formatting\book\candidate.md" --summary "self-check passed"
```

Reuse:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py apply-approved "skills\mathos-formatting\plugins\approved\textbook-family-v1" "C:\path\next-book.md"
```

## Main Problems With The Original Skill

- It read like a README rather than an operating procedure.
- It made JSON rules the main path even after prompts moved to Python output.
- It under-specified sandbox execution and generated-code safety.
- It did not clearly separate self-check approval from source replacement.
- It hid high-risk cases such as TOC over-stripping, heading misclassification, protected-region mutation, short candidates, and unsafe generated code.

## Improvements To best_skill

- Uses precise frontmatter and SOP sections.
- Documents Python artifacts as the official main path.
- Keeps Stage 2 JSON scoped to TOC line detection only.
- Gives exact CLI commands for learning, candidate rebuild, approval, and reuse.
- Defines input/output contracts, artifact layout, protected regions, critical rules, failure handling, validation, approval, and reuse.
- Marks old JSON programs as legacy compatibility only.
