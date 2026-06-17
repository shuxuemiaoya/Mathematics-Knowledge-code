---
name: mathos-formatting
description: Use for MathOS Markdown formatting when provider-generated Python artifacts must normalize TOC-aligned headings, strip the TOC safely, preserve protected Markdown regions, produce self-check candidates, or save/reuse approved formatting programs without replacing the original source.
---

# MathOS Formatting

## Overview

This repo-local skill formats MathOS Markdown after conversion and before segmentation. The current main path is Python artifact mode: Stage 1, Stage 4, and Stage 5 consume DeepSeek-generated Python files; Stage 2 TOC detection remains JSON because it only returns line numbers. Candidate-producing commands never replace the original Markdown file.

## When To Use

Use this skill when a MathOS `.md` file needs:

- Structure inspection before formatting.
- Provider-backed heading normalization according to the TOC.
- TOC stripping with preface/body preservation.
- Chapter-inner Markdown cleanup through a generated Python batch processor.
- Stage 5 title cleanup through `TITLE_REWRITE_MAP`.
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
| Inspect only | `python skills\mathos-formatting\scripts\mathos_formatting.py inspect "<source.md>"` |
| Learn Python artifacts | `python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "<source.md>" --env ..\.env` |
| Learn into explicit work dir | `python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "<source.md>" --env ..\.env --work-dir "<work-dir>" --timeout-seconds 120 --h1-index 0` |
| Build candidate from Python artifacts | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-script "<work-dir>\heading_processor.py" --content-script "<work-dir>\content_processor.py"` |
| Build candidate with title map | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-script "<work-dir>\heading_processor.py" --content-script "<work-dir>\content_processor.py" --title-rewrite-map "<work-dir>\title_rewrite_map.py"` |
| Save approved Python program | `python skills\mathos-formatting\scripts\mathos_formatting.py approve --approved-root skills\mathos-formatting\plugins\approved --plugin-id "<program-id>" --heading-script "<work-dir>\heading_processor.py" --content-script "<work-dir>\content_processor.py" --title-rewrite-map "<work-dir>\title_rewrite_map.py" --original "<source.md>" --candidate "<candidate.md>" --summary "self-check passed"` |
| Apply approved program | `python skills\mathos-formatting\scripts\mathos_formatting.py apply-approved "skills\mathos-formatting\plugins\approved\<program-id>" "<source.md>"` |
| Legacy JSON candidate | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-rules "<old>\heading_rules.json" --content-rules "<old>\content_rules.json"` |

## Workflow SOP

1. Inspect unknown source families before formatting.
2. Use `learn-from-provider` for new or changed families.
3. Use `candidate-from-artifacts` after editing generated Python artifacts.
4. Run the self-check loop on `candidate.md` and the report. Manual review is not an approval gate; the skill self-check is.
5. Save a reusable program only after the candidate passes self-check.
6. Ask separately before replacing the original Markdown with the candidate. Keep an audit backup such as `original-before-formatting.md` when replacement is approved.
7. Run segmentation only after the approved candidate has explicitly replaced the source.

## Provider Stages

1. **Stage 1 Heading Processor**: DeepSeek returns Python source saved as `heading_processor_response.py`, normalized to `heading_processor.py`, then executed against a temporary sandbox copy of `candidate.md`.
2. **Stage 2 TOC Detection**: DeepSeek returns JSON saved as `toc_detection_response.json`; only `toc_start_line` and `main_text_start_line` are used.
3. **Stage 3 H1 Sample Extraction**: The local runtime extracts an H1 sample after TOC stripping.
4. **Stage 4 Content Processor**: DeepSeek returns Python source saved as `content_processor_response.py`, normalized to `content_processor.py`, then executed against a temporary sandbox copy of the stripped candidate.
5. **Stage 5 Title Rewrite Map**: DeepSeek returns Python source defining `TITLE_REWRITE_MAP`, saved as `title_rewrite_map_response.py` and normalized to `title_rewrite_map.py`.

## Input And Output Contract

Inputs:

- Source path exists, is a file, ends in `.md`, and is UTF-8 Markdown.
- Provider learning reads secrets from `.env`; never print or persist secret values.
- Stage 1/4 artifacts are Python batch scripts.
- Stage 5 artifact is a Python title-map file.
- Stage 2 remains JSON line-number output.

Outputs:

- `inspect`, `learn-from-provider`, `candidate-from-artifacts`, and `apply-approved` do not modify the original source.
- Provider learning writes `<work-dir>\candidate.md`, reports, generated artifacts, and `run-state.json`.
- Artifact/application runs write a fresh candidate under the source directory's `mathos-formatting` area.
- Approved programs are written under `skills\mathos-formatting\plugins\approved\<program-id>\`.
- CLI JSON includes status, candidate path, report path, warnings, `self_check_required`, and `next_actions`.

## Artifact Layout

Provider learning work directories may include:

- `toc_sample.md`
- `heading_processor_prompt.md`
- `heading_processor_response.py`
- `heading_processor.py`
- `stage1_heading_report.md`
- `toc_detection_prompt.md`
- `toc_detection_sample.md`
- `toc_detection_response.json`
- `h1_sample.md`
- `content_cleaner_prompt.md`
- `content_processor_response.py`
- `content_processor.py`
- `heading_optimization_prompt.md`
- `title_rewrite_map_response.py`
- `title_rewrite_map.py`
- `_python-artifact-sandboxes\`
- `candidate.md`
- `candidate-report.md`
- `run-state.json`

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

Stage 1 and Stage 4 Python scripts must:

- Start with `import os`.
- Include `from pathlib import Path` and `import re`.
- Define `get_target_root()`, `protect_blocks()`, `restore_blocks()`, `replace_in_file()`, and `main()`.
- Read a target root from stdin and process Markdown files under that root.
- Preserve display math, code fences, YAML frontmatter, markdown tables, headings where required, and other protected blocks.
- Run only inside the runtime-created temporary sandbox.

Stage 5 files must define only:

```python
TITLE_REWRITE_MAP: dict[str, str] = {
    "## Review Questions 5": "#### Chapter 5 Review Questions 5",
}
```

Every key and value must be a Markdown heading line. Values may keep the same level or downgrade to H4-H6.

## Protected Regions

The self-check loop must protect or validate:

- TOC before Stage 1 audit, to avoid accidental TOC deletion during heading validation.
- Display math blocks delimited by `$$` or `\[` and `\]`.
- Fenced code blocks using backticks or tildes.
- YAML frontmatter.
- Markdown table lines.
- Image references.
- HTML `<details>` blocks unless the user has explicitly changed the content contract and tests for that behavior.
- Heading lines during Stage 4 content cleanup.

## Critical Rules

- Fail closed on deletion risk.
- Stage 1/4 generated scripts run only in temporary sandbox directories.
- Never execute generated Python against the original Markdown directory.
- Never accept a Python artifact that imports network, subprocess, shell, or unsafe filesystem modules.
- Reject artifacts that call `open`, `eval`, `exec`, external commands, delete, move, rename, or recursively copy files.
- Stage 1 mutation and Stage 1 audit are separate. The audit validates; it does not mutate.
- Stage 1 audit runs before TOC stripping.
- H1-H3 are reserved for TOC-derived structure; non-TOC headings must be H4-H6.
- Headings like `Section` or `Review Questions 5` should receive parent context through provider-generated artifacts, not hardcoded runtime enrichment.
- Stage 5 uses `TITLE_REWRITE_MAP`, not JSON.
- Never save a reusable program until the candidate passes self-check.
- Never replace the original source without explicit approval.

## Failure Handling

Stop and keep artifacts when:

- Source is missing, non-Markdown, or unreadable.
- Provider output is invalid Python for Stage 1/4/5.
- Stage 2 JSON is invalid or returns unusable line numbers.
- Python artifact is missing required imports or functions.
- Python artifact contains dangerous imports or calls.
- Stage 1 audit rejects TOC heading levels.
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
rg "content_rules.json|heading_rules.json|heading_optimizations.json|json_object" skills\mathos-formatting tests
```

The final `rg` should show only legacy compatibility or Stage 2 TOC JSON references.

Required validation coverage:

- Accidental TOC deletion is caught.
- Heading level judgment is checked against TOC-derived structure.
- Display math, code fences, YAML frontmatter, and tables are protected.
- Invalid provider JSON is still tested for Stage 2 TOC detection.
- Invalid provider Python is rejected for Stage 1/4/5.
- Candidate-too-short or content-loss output fails closed.
- Original file cannot be replaced without explicit user approval.
- Dangerous Python artifacts are rejected, including `os.remove`, `subprocess`, arbitrary write `open`, network imports/calls, and missing required functions.
- Stage 1/4 scripts only affect sandbox candidate copies.
- Stage 5 parses and applies `TITLE_REWRITE_MAP`.
- Legacy approved programs still apply through the compatibility branch.

## Review And Approval Workflow

Manual review is not the acceptance gate. Candidate-producing commands set `self_check_required: true`; the agent must complete the skill self-check loop:

1. Read `run-state.json`, `candidate.md`, and the report.
2. Confirm the original file was not modified.
3. Verify heading alignment and Stage 1 audit evidence.
4. Verify preservation counts and protected-region behavior.
5. Confirm candidate length is plausible.
6. If all checks pass, save the approved program.
7. Ask separately before replacing the original source with the candidate.

## Reuse Approved Programs

Use `apply-approved` only for sources from the same self-check-passing family.

Reuse behavior:

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
