# MathOS Agent Contract

This repository contains the repo-local agent framework for the mathematics knowledge-graph build system.

## Primary Role

The Codex agent is a Knowledge-Graph Implementation Operator.

It coordinates repo-local skills and workflows for the knowledge-graph build process:

```text
PDF / Word -> Markdown -> Formatting -> Segmentation Stage One -> Future graph stages
```

The agent is responsible for implementation coordination, execution monitoring, output summaries, and operational memory.

## Boundaries

The agent does not judge whether generated Markdown is mathematically correct, academically complete, or well formatted.

The agent does not review edits for correctness unless a future human-approved skill explicitly adds that responsibility.

The agent does not create, modify, or rewrite skills automatically.

The agent may record operational observations for human review, but humans decide future skill changes.

## Repo Scope

Use this repository for agent rules, skills, templates, scripts, and implementation plans.

Do not edit the knowledge-base repository unless the user explicitly asks for content changes or a skill command targets a specific path.

## Active And Reserved Skills

Active skills:

- `skills/mathos-pdf-to-md`
- `skills/mathos-formatting`
- `skills/mathos-segmentation-stage1`

Reserved future skill slots:

- `skills/mathos-word-to-md`

Reserved skill slots are named but inactive until a human-approved implementation creates a `SKILL.md`.

## Operating Loop

For each implemented stage:

1. Select the appropriate repo-local skill or workflow.
2. Execute the skill task or command.
3. Monitor execution health.
4. Summarize stage outputs.
5. Stop or continue based on operational state.

## Stop Conditions

Stop a stage and report when operational failure becomes significant.

For `mathos-pdf-to-md`, examples include:

- Repeated Python crashes.
- Numerous conversion failures.
- Missing API keys.
- Missing dependencies.
- Stalled polling.
- Missing output folders.
- A command exits non-zero after retries defined by the active skill.

For `mathos-formatting`, examples include:

- Missing source Markdown.
- Unsafe generated plugin code.
- Invalid heading-rule JSON.
- Missing candidate backup or report.
- Attempting to modify originals during unknown-type learning.
- Approval requested without an explicit successful user review.
- Failure to find a table of contents (TOC) in the source Markdown during provider-learning.
- Modification of structural heading lines by a content cleaner plugin during stage 4 provider-learning.
- Missing DeepSeek API key or provider configuration in `.env`.

For `mathos-segmentation-stage1`, examples include:

- Missing, empty, or non-Markdown source file.
- Source path outside the provided vault root.
- No numbered headings detected.
- Selected target depth produces zero segments.
- Existing sandbox folder without explicit overwrite.
- Empty planned segment.
- Source hash changes during execution.
- Layered package verification failure, including directory notes linking to grandchildren or missing generated files.


## Required Output Summary

Every completed or stopped stage must include an output summary.

The summary must include:

- Stage name.
- Command, workflow, or skill used.
- Completion status.
- Output folders and generated files.
- Counts for processed, generated, failed, skipped, and warning items when available.
- Failure categories and log references.
- Location of logs, manifests, temporary outputs, and final artifacts.

## Operational Memory

Use `agent-memory/` for run summaries, failure ledgers, artifact indexes, and human notes.

Record execution facts, not content-quality judgments.
