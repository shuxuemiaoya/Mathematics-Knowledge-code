---
name: mathos-formatting
description: Use when MathOS Markdown after PDF or Word conversion needs provider-backed formatting, TOC-driven heading normalization, protected-region validation, or reusable formatting program generation.
---

# MathOS Formatting

## Overview

This repo-local skill is operational. It manages adaptive MathOS Markdown formatting with DeepSeek-generated artifacts plus local self-checks, while preserving the original Markdown until explicit file-replacement approval.

## When To Use

Use this skill when a MathOS-generated `.md` file needs repeatable formatting cleanup before segmentation or graph-building.

Use it for:

- Inspecting Markdown structure, headings, TOC signals, H1 sections, and protected blocks.
- Learning formatting artifacts through the provider workflow.
- Creating a candidate Markdown file from `heading_rules.json` plus `content_rules.json`.
- Running the skill self-check loop that validates heading structure, protected regions, and preservation counts.
- Saving a self-check-passing candidate as a reusable program.
- Reusing an approved program on another Markdown file from the same family.
- Diagnosing formatting runs that fail on heading rules, TOC stripping, provider JSON, protected regions, or content-preservation validation.

## When Not To Use

Do not use this skill for:

- PDF or Word conversion. Use the conversion stage first.
- Segmentation. Run segmentation only after a self-check-passing formatting candidate has replaced the source with explicit file-replacement approval.
- Mathematical correctness review or content rewriting.
- Summarization, translation, deletion, reordering, or educational-content editing.
- Non-Markdown files.
- Replacing the original Markdown file without an explicit user approval message for that exact replacement.

## Quick Reference

Run commands from `C:\Mathematics-Knowledge\Mathematics-Knowledge-code`.

| Task | Command |
| --- | --- |
| Show CLI help | `python skills\mathos-formatting\scripts\mathos_formatting.py --help` |
| Inspect without writing | `python skills\mathos-formatting\scripts\mathos_formatting.py inspect "<source.md>"` |
| Learn provider artifacts | `python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "<source.md>" --env ..\.env` |
| Learn into an explicit work dir | `python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "<source.md>" --env ..\.env --work-dir "<source-dir>\mathos-formatting\<source-stem>" --timeout-seconds 120 --h1-index 0` |
| Build candidate from JSON rules | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-rules "<work-dir>\heading_rules.json" --content-rules "<work-dir>\content_rules.json"` |
| Build candidate with heading optimizations | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-rules "<work-dir>\heading_rules.json" --content-rules "<work-dir>\content_rules.json" --heading-optimizations "<work-dir>\heading_optimizations.json"` |
| Build candidate from legacy cleaner | `python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "<source.md>" --heading-rules "<work-dir>\heading_rules.json" --plugin "<work-dir>\content_cleaner.py"` |
| Save self-check-passing JSON program | `python skills\mathos-formatting\scripts\mathos_formatting.py approve --approved-root skills\mathos-formatting\plugins\approved --plugin-id "<program-id>" --heading-rules "<work-dir>\heading_rules.json" --content-rules "<work-dir>\content_rules.json" --original "<source.md>" --candidate "<candidate.md>" --summary "self-check passed"` |
| Apply approved program to a fresh candidate | `python skills\mathos-formatting\scripts\mathos_formatting.py apply-approved "skills\mathos-formatting\plugins\approved\<program-id>" "<source.md>"` |

## Workflow SOP

1. Inspect first when the source family is unknown:
   `python skills\mathos-formatting\scripts\mathos_formatting.py inspect "<source.md>"`
2. Learn or reuse rules:
   - Unknown or changed file family: run `learn-from-provider`.
   - Known self-check-passing file family: run `apply-approved`.
   - Manually repaired artifacts: run `candidate-from-artifacts`.
3. Run the self-check loop on the generated candidate and report. The candidate is accepted only when every self-check passes.
4. If self-check fails, revise the JSON rules or rerun provider learning. Do not save a reusable program.
5. If self-check passes, run `approve` to save the reusable formatting program with a summary such as `self-check passed`.
6. If the user explicitly approves replacing the original Markdown file for downstream stages, make a source-preserving backup such as `original-before-formatting.md`, then replace the source with the candidate.
7. Only clean the temporary `mathos-formatting` work directory after self-check passes and no audit artifacts are still needed.

### The 5-Stage Provider Learning Workflow

When running `learn-from-provider`, the formatter executes the following five stages sequentially:

1. **Stage 1: Heading Refinement**: Learns pattern rules via DeepSeek to normalize headings completely according to the TOC. TOC entries occupy H1-H3; headings not present in the TOC must be downgraded to H4-H6, with the target downgrade level chosen by DeepSeek. All heading modifications are driven entirely by DeepSeek's `heading_rules.json`. A structural audit runs immediately to validate that TOC chapter headings remain H1 before proceeding.
2. **Stage 2: TOC Detection & Stripping**: Identifies start and end boundaries of the Table of Contents via DeepSeek to strip the TOC section while preserving prefaces and standard text.
3. **Stage 3: Sample Section Extraction**: Extracts a representative sample H1 chapter section to serve as a baseline for formatting analysis.
4. **Stage 4: Chapter-Inner Formatting**: Learns and applies Markdown normalization rules (whitespace, spacing, formula cleanup) protecting mathematical formulas, code fences, and other structural blocks.
5. **Stage 5: Heading Optimization And Self-Check**: Extracts all heading lines and calls DeepSeek to correct OCR errors and demote any non-TOC heading that still occupies H1-H3.
   - **TOC Consistency Enforcement**: H1-H3 are reserved for TOC entries. Non-TOC headings may keep their existing level only if it is already H4-H6, or may be downgraded to H4-H6.
   - **Mapping Storage**: The optimized heading dictionary is written to `heading_optimizations.json`.

## Input And Output Contract

Inputs:

- Source path must exist and end in `.md`.
- Source text must be UTF-8 Markdown.
- Provider learning requires a workspace `.env` with provider settings. Never print or save secret values.
- `candidate-from-artifacts`, `approve`, and `apply-approved` require valid JSON artifacts or a guarded legacy cleaner.

Outputs:

- The original source is not modified by `inspect`, `learn-from-provider`, `candidate-from-artifacts`, or `apply-approved`.
- Candidate output is a self-check artifact, usually `<source-dir>\mathos-formatting\<source-stem>\candidate.md` for provider learning or `<source-dir>\<source-stem>.candidate.md` for artifact/application runs.
- Each successful candidate has a report, usually `candidate-report.md`, `<source-stem>.candidate-report.md`, or `stage1_heading_report.md`.
- Approved reusable programs are written under `skills\mathos-formatting\plugins\approved\<program-id>\`.
- CLI JSON contains status, artifact paths, warnings, `self_check_required`, and `next_actions`.

## Artifact Layout

Provider learning work directories may include:

- `toc_sample.md`
- `heading_rules_prompt.md`
- `heading_rules_response.json`
- `heading_rules.json`
- `stage1_heading_report.md`
- `toc_detection_prompt.md`
- `toc_detection_sample.md`
- `toc_detection_response.json`
- `h1_sample.md`
- `content_cleaner_prompt.md`
- `content_rules_response.json`
- `content_rules.json`
- `heading_optimization_prompt.md`
- `heading_optimizations.json`
- `candidate.md`
- `candidate-report.md`
- `run-state.json`

Approved program directories contain:

- `heading_rules.json`
- `content_rules.json` for new programs, or `content_cleaner.py` only for legacy programs.
- `heading_optimizations.json` (optional, contains mapping template for Stage 5 heading optimizations).
- `metadata.json`
- `approval.md`
- `sample_before.md`
- `sample_after.md`

New reusable programs start with `allowed_scope: self-check-only` when the self-check loop is the acceptance authority.

## JSON Schemas

`heading_rules.json`:

```json
{
  "rules": [
    {
      "id": "chapter_h1",
      "pattern": "^第(.+)章\\s+(.+)$",
      "replacement": "# 第$1章 $2",
      "flags": ["MULTILINE"]
    }
  ]
}
```

Rules must be a non-empty list. Each rule must have non-empty string `id` and `pattern`, string `replacement`, and string-list `flags`.

`heading_optimizations.json`:

```json
{
  "## ϰο4": "#### Chapter 5 Review Exercise 4",
  "## Review Questions 5": "#### Chapter 5 Review Questions 5"
}
```

Must be a flat key-value object where both keys and values are non-empty strings starting with `#`. Values may keep the same heading level or downgrade to H4-H6. Values must not promote a heading into H1-H3 unless that heading is a TOC entry.

`content_rules.json`:

```json
{
  "plugin_id": "chapter_inner_markdown_formatter",
  "plugin_version": "1.0.0",
  "schema_version": "1.0.0",
  "stage": "chapter_inner_formatting",
  "description": "Normalize chapter-inner Markdown formatting without deleting content.",
  "safety": {
    "never_modify_heading_lines": true
  },
  "execution_contract": {
    "mutation_scope": "unprotected spans only"
  },
  "protected_blocks": [
    "heading_lines",
    "fenced_code_blocks",
    "display_math_blocks",
    "html_details_blocks",
    "yaml_frontmatter",
    "markdown_tables"
  ],
  "analyze": {
    "checks": []
  },
  "rules": [
    {
      "id": "normalize_blank_lines",
      "type": "blank_line_normalize",
      "scope": "all_unprotected_non_heading_text",
      "phase": "blank_line_fix",
      "risk_level": "low",
      "pattern": "\\n{3,}",
      "replacement": "\\n\\n",
      "flags": [],
      "replacement_mode": "regex_template",
      "enabled": true
    }
  ],
  "warnings": [],
  "summary": []
}
```

Required content-rule keys are `plugin_id`, `plugin_version`, `schema_version`, `stage`, `description`, `safety`, `execution_contract`, `protected_blocks`, `analyze`, `rules`, `warnings`, and `summary`.

Hard schema requirements:

- `plugin_id` must be `chapter_inner_markdown_formatter`.
- `schema_version` must be `1.0.0`.
- `stage` must be `chapter_inner_formatting`.
- `safety.never_modify_heading_lines` must be true.
- `protected_blocks`, `analyze.checks`, `rules`, `warnings`, and `summary` must be lists.
- `warnings` and `summary` must be string lists.
- Mutating rule types are limited to `literal_replace`, `regex_replace`, `line_regex_replace`, `blank_line_normalize`, `choice_option_split`, `callout_spacing_fix`, `formula_whitelist_fix`, and guarded `image_caption_fix`.
- Enabled `image_caption_fix` is rejected unless disabled or represented as report-only guidance.

## Protected Regions

The content-rule executor applies rules only to unprotected spans and preserves:

- Heading lines.
- Fenced code blocks using backticks or tildes.
- Display math blocks delimited by `$$` or `\[` and `\]`.
- HTML `<details>` blocks.
- YAML frontmatter.
- Markdown table lines.

Heading-rule application also skips code fences and display math blocks.

## Critical Rules

- **Never modify the skill's own scripts or code during execution.** The files under `skills/mathos-formatting/scripts/` (including `mathos_formatting_core.py`, `mathos_formatting.py`, and `mathos_provider.py`) are read-only during skill execution. If a pipeline error is caused by a code defect (missing flag mapping, unrecognized heading pattern, unsupported rule type, etc.), the agent must stop and report the defect to the user, not patch the code to continue. Code changes require a separate, explicit user request outside the formatting workflow.
- Fail closed on deletion risk. A cleaner-looking candidate is invalid if it drops source content.
- Stage 1 mutation and Stage 1 audit are separate: heading rules modify headings according to DeepSeek's `heading_rules.json`; `audit_stage1_headings` only validates that TOC chapter headings remain H1.
- Stage 1 audit runs before TOC stripping so the original TOC remains available for heading context validation.
- TOC stripping must remove only the detected TOC block; preserve prefaces and any content before the TOC.
- Headings must be modified completely according to the TOC: TOC entries map to H1-H3, and every heading not appearing in the TOC must be downgraded to H4-H6.
- The H4/H5/H6 downgrade level for non-TOC headings is chosen by DeepSeek and then verified by the self-check loop.
- All heading modifications (including any parent context additions) are driven entirely by DeepSeek's heading rules and heading optimizations, not by hardcoded patterns in the core code.
- Stage 4 content rules must not modify heading lines.
- Heading optimizations (Stage 5) may downgrade non-TOC headings to H4-H6; promotions into H1-H3 are rejected unless they match TOC structure.
- Use literal replacement for literal LaTeX command strings; avoid regex replacement when replacing text such as `\mathbb`.
- Never save a reusable program until the candidate and report have passed the self-check loop.
- Never replace the original file unless the user explicitly approves that exact replacement.

## Failure Handling

Stop and report artifacts when any of these occur:

- Missing source Markdown or non-Markdown input.
- Missing `.env` provider configuration.
- Provider response is empty, invalid JSON, or fails schema validation.
- `heading_rules.json` has invalid regex or an empty `rules` list.
- Stage 1 audit rejects heading levels or chapter H1 handling.
- TOC detection returns invalid line numbers or would strip beyond the TOC.
- `content_rules.json` is missing required keys or uses unsupported rule types/scopes/phases.
- A pipeline error is caused by a code-level defect in the skill scripts (e.g. unsupported flag, unrecognized heading pattern, missing function). Report the defect; do not modify the scripts.
- Candidate becomes too short or preservation counts drop.
- Images, `<details>` blocks, math delimiters, table-like lines, headings, code fences, YAML, or table regions are modified unexpectedly.
- Legacy `content_cleaner.py` imports unsafe modules, performs file IO, changes headings, or returns invalid analysis types.
- Reusable-program saving is attempted before the self-check loop passes.
- Original replacement is attempted without explicit user approval.

When failure happens, keep the work directory and report the current stage plus artifact paths. Do not silently retry by weakening validation or by modifying skill scripts.

## Validation

Before calling a formatting run successful, verify:

- CLI exits zero.
- Candidate path exists and is non-empty.
- Report path exists.
- CLI status is `candidate-written`, `candidate-created`, `approved`, or the expected success state.
- `self_check_required` is true for candidate-producing commands.
- Original source file hash or modified timestamp is unchanged by candidate-producing commands.
- Preservation summary shows no lost images, details blocks, math delimiters, or table-like lines.
- Heading lines are unchanged by Stage 4 content rules.
- H1-H3 candidate headings are all present in the TOC-derived structure.
- Non-TOC headings are all H4-H6.
- Candidate length is plausible compared with the post-TOC source. If it is dramatically shorter, stop for self-check failure handling.

Required regression coverage for this skill:

- Accidental TOC deletion: provider TOC detection must preserve pre-TOC content and must not strip main body text.
- Heading-level judgment: real TOC chapter H1s stay H1; TOC sections/subsections map to H2/H3; non-TOC headings become H4-H6.
- Protected regions: display math, code fences, YAML frontmatter, and markdown tables survive unchanged.
- Invalid provider JSON: invalid heading/content responses fail before candidate approval.
- Candidate too short: destructive candidates fail validation.
- Original replacement: no command or workflow may replace the source without explicit user approval.

Suggested checks:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py --help
python skills\mathos-formatting\scripts\mathos_formatting.py inspect "<source.md>"
python -m pytest
```

## Self-Check And Acceptance

Manual formatting confirmation is removed. Candidate-producing commands are self-check-only. After each candidate:

1. Read the machine report and run-state artifacts.
2. Verify preservation-sensitive content: images, details, formulas, tables, YAML, code fences, and headings.
3. Verify TOC alignment: all H1-H3 headings must appear in the TOC-derived heading structure.
4. Verify non-TOC headings: every heading not in the TOC must be H4-H6.
5. If every check passes, run `approve` to save the reusable program.
6. Separately ask whether to replace the original source with the candidate for downstream segmentation.
7. If replacement is approved, keep an audit backup such as `original-before-formatting.md`.

Acceptance saves a reusable program. It does not mean the original source file has already been replaced.

## Reuse Approved Programs

Use `apply-approved` only when the source appears to belong to the same self-check-passing family as the reusable program.

Reuse behavior:

- Reads `heading_rules.json`.
- Prefers `content_rules.json`.
- Falls back to legacy `content_cleaner.py` if JSON rules are absent.
- Replays local heading optimizations from `heading_optimizations.json` if present, completely bypassing external LLM calls.
- Creates a fresh candidate backup and report.
- Preserves the original source until explicit replacement approval.
- Keeps reusable programs scoped to self-check acceptance until multiple successful runs justify broader automation.

## Examples

Inspect:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py inspect "C:\path\book.md"
```

Learn from provider:

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py learn-from-provider "C:\path\book.md" --env "C:\Mathematics-Knowledge\.env" --work-dir "C:\path\mathos-formatting\book" --timeout-seconds 120 --h1-index 0
```

Rebuild candidate after editing JSON (with optional heading optimizations):

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py candidate-from-artifacts "C:\path\book.md" --heading-rules "C:\path\mathos-formatting\book\heading_rules.json" --content-rules "C:\path\mathos-formatting\book\content_rules.json" --heading-optimizations "C:\path\mathos-formatting\book\heading_optimizations.json"
```

Save self-check-passing reusable program (automatically copies `heading_optimizations.json` to the approved program directory if present):

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py approve --approved-root skills\mathos-formatting\plugins\approved --plugin-id "textbook-family-v1" --heading-rules "C:\path\mathos-formatting\book\heading_rules.json" --content-rules "C:\path\mathos-formatting\book\content_rules.json" --original "C:\path\book.md" --candidate "C:\path\mathos-formatting\book\candidate.md" --summary "self-check passed"
```

Reuse self-check-passing program (which automatically replays optimizations if `heading_optimizations.json` is present):

```powershell
python skills\mathos-formatting\scripts\mathos_formatting.py apply-approved "skills\mathos-formatting\plugins\approved\textbook-family-v1" "C:\path\next-book.md"
```

## Main Problems With The Original Skill

- It read like a README rather than an agent operating procedure.
- It described the happy path but under-specified stop conditions and validation gates.
- It did not provide a quick command table or exact command templates.
- It omitted concrete input/output contracts and artifact layouts.
- It mentioned JSON content rules without an actionable schema.
- It did not foreground the most dangerous risks: TOC over-stripping, heading-level misclassification, protected-region mutation, invalid provider JSON, destructive short candidates, and unapproved source replacement.
- It did not clearly separate reusable-program approval from replacing the original Markdown file.

## Improvements To best_skill

- Adds precise frontmatter so agents choose this skill only for MathOS Markdown formatting and self-check candidate workflows.
- Adds When To Use and When Not To Use sections to keep conversion, formatting, segmentation, approval, and replacement boundaries distinct.
- Adds exact CLI commands matching the live parser.
- Makes candidate-vs-original behavior explicit and fail-closed.
- Documents artifact layout for provider learning and approved programs.
- Documents heading-rule and content-rule JSON schemas with required keys and supported rule families.
- Promotes protected regions and preservation checks to first-class SOP rules.
- Adds failure handling for provider JSON, TOC stripping, heading audit, content preservation, legacy cleaner safety, and unapproved replacement.
- Adds validation tasks for the specific high-risk cases this formatter has historically hit.
- Aligns the skill with the current runtime: heading rules, Stage 1 audit before TOC stripping, Stage 4 JSON rules, guarded legacy cleaners, and heading optimization artifacts.
