# Repo-Local Knowledge-Graph Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first repo-local Knowledge-Graph Implementation Operator framework for MathOS.

**Architecture:** This creates a repo-local operating contract, a skill registry, one active PDF-to-Markdown operator skill, reserved future skill slots, and lightweight operational memory templates. The agent monitors execution health and reports output summaries; it does not judge content correctness, review edits, or rewrite its own skills.

**Tech Stack:** Markdown, Codex repo-local skills, PowerShell verification commands, Git.

---

## File Structure

Create these files:

```text
AGENTS.md
docs/agent/README.md
docs/agent/skill-registry.md
docs/agent/operator-lifecycle.md
agent-memory/README.md
agent-memory/templates/run-summary.md
agent-memory/templates/failure-ledger.json
agent-memory/templates/artifact-index.md
agent-memory/templates/human-notes.md
agent-proposals/README.md
skills/mathos-pdf-to-md/SKILL.md
skills/mathos-word-to-md/README.md
skills/mathos-formatting/README.md
```

Responsibilities:

- `AGENTS.md`: Repo-level operating contract for all Codex work in this project.
- `docs/agent/README.md`: Human entry point for the agent framework.
- `docs/agent/skill-registry.md`: Names active and reserved skill slots.
- `docs/agent/operator-lifecycle.md`: Defines the operator loop and reporting behavior.
- `agent-memory/README.md`: Explains operational memory boundaries.
- `agent-memory/templates/*`: Human-readable run record templates.
- `agent-proposals/README.md`: Human decision holding area for future observations and requests.
- `skills/mathos-pdf-to-md/SKILL.md`: First active skill for monitoring PDF-to-Markdown conversion execution.
- `skills/mathos-word-to-md/README.md`: Reserved future skill slot, intentionally inactive.
- `skills/mathos-formatting/README.md`: Reserved future skill slot, intentionally inactive.

Do not create `SKILL.md` for `mathos-word-to-md` or `mathos-formatting` in this first implementation. A `SKILL.md` would make Codex treat those slots as active skills, but their behavior is not designed yet.

---

### Task 1: Create Repo-Level Agent Contract

**Files:**
- Create: `AGENTS.md`

- [ ] **Step 1: Create `AGENTS.md`**

Create `AGENTS.md` with this exact content:

````markdown
# MathOS Agent Contract

This repository contains the repo-local agent framework for the mathematics knowledge-graph build system.

## Primary Role

The Codex agent is a Knowledge-Graph Implementation Operator.

It coordinates repo-local skills and workflows for the knowledge-graph build process:

```text
PDF / Word -> Markdown -> Formatting -> Future graph stages
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

Active first-version skill:

- `skills/mathos-pdf-to-md`

Reserved future skill slots:

- `skills/mathos-word-to-md`
- `skills/mathos-formatting`

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
````

- [ ] **Step 2: Verify the contract file exists**

Run:

```powershell
Test-Path -LiteralPath .\AGENTS.md
```

Expected: `True`

- [ ] **Step 3: Verify core boundaries are present**

Run:

```powershell
Select-String -LiteralPath .\AGENTS.md -Pattern 'does not judge','does not create, modify, or rewrite skills automatically','Required Output Summary'
```

Expected: three matching lines.

- [ ] **Step 4: Commit**

Run:

```powershell
git add AGENTS.md
git commit -m "docs: add MathOS agent contract"
```

Expected: commit succeeds with `AGENTS.md` created.

---

### Task 2: Create Agent Documentation

**Files:**
- Create: `docs/agent/README.md`
- Create: `docs/agent/skill-registry.md`
- Create: `docs/agent/operator-lifecycle.md`

- [ ] **Step 1: Create `docs/agent/README.md`**

Create `docs/agent/README.md` with this exact content:

```markdown
# MathOS Repo-Local Agent

The MathOS repo-local agent is a Knowledge-Graph Implementation Operator.

Its first version exists to coordinate the knowledge-graph build framework, monitor task execution, summarize stage outputs, and save operational memory.

It is not a content-quality reviewer and it is not a self-modifying meta-agent.

## Read These Files First

- `AGENTS.md`: project-level operating contract.
- `docs/agent/skill-registry.md`: active and reserved skill slots.
- `docs/agent/operator-lifecycle.md`: execution and reporting lifecycle.
- `agent-memory/README.md`: run memory boundaries and templates.

## First-Version Focus

The first concrete stage is PDF to Markdown conversion through `skills/mathos-pdf-to-md`.

The agent should monitor operational health for that stage and stop if repeated failures make the run unsafe or unproductive.

The agent must summarize outputs for every completed or stopped stage.
```

- [ ] **Step 2: Create `docs/agent/skill-registry.md`**

Create `docs/agent/skill-registry.md` with this exact content:

```markdown
# Skill Registry

This registry names repo-local skill slots for the MathOS Knowledge-Graph Implementation Operator.

## Active Skills

### `skills/mathos-pdf-to-md`

Status: active first-version skill.

Purpose: coordinate and monitor PDF to Markdown conversion tasks.

First-version behavior:

- Identify the conversion command or Python workflow.
- Run the task only against an explicit user-provided target.
- Monitor crashes, non-zero exits, repeated conversion failures, stalled runs, and missing outputs.
- Stop the task when failure volume crosses the active skill threshold.
- Preserve logs and output locations.
- Report a required output summary.

The skill does not judge whether generated Markdown content is correct.

## Reserved Future Skill Slots

### `skills/mathos-word-to-md`

Status: reserved, inactive.

Purpose: future Word/DOCX to Markdown workflow.

This slot must not contain a `SKILL.md` until its detailed behavior is designed and approved.

### `skills/mathos-formatting`

Status: reserved, inactive.

Purpose: future batch Markdown formatting workflow.

This slot must not contain a `SKILL.md` until its detailed behavior is designed and approved.
```

- [ ] **Step 3: Create `docs/agent/operator-lifecycle.md`**

Create `docs/agent/operator-lifecycle.md` with this exact content:

```markdown
# Operator Lifecycle

The Knowledge-Graph Implementation Operator follows the same lifecycle for every implemented stage.

## 1. Select Stage

Choose the repo-local skill or workflow that matches the user's requested task.

If no implemented skill exists for the requested task, stop and report that the skill slot is not active yet.

## 2. Execute Task

Run the command or Python workflow defined by the active skill.

Only run broad operations against explicit user-provided targets.

## 3. Monitor Health

Monitor operational health signals:

- Process crash.
- Non-zero command exit.
- Repeated failed files.
- Missing dependency.
- Missing API key.
- Stalled polling or no progress.
- Missing output folder.

Do not inspect generated content for mathematical correctness.

## 4. Summarize Output

Every completed or stopped stage must produce an output summary.

The summary includes:

- Stage name.
- Command or workflow used.
- Completion status.
- Output paths.
- Processed, generated, failed, skipped, and warning counts when available.
- Failure categories and log locations.

## 5. Save Operational Memory

Save run facts in `agent-memory/` using the templates in `agent-memory/templates/`.

Records must be human-readable Markdown or simple JSON.

## 6. Stop Or Continue

Stop when the active skill's operational stop conditions are met.

Continue only when the current implemented stage completed and the next requested stage is also implemented.
```

- [ ] **Step 4: Verify agent documentation**

Run:

```powershell
$files = @(
  '.\docs\agent\README.md',
  '.\docs\agent\skill-registry.md',
  '.\docs\agent\operator-lifecycle.md'
)
$files | ForEach-Object { "$_ => $(Test-Path -LiteralPath $_)" }
```

Expected:

```text
.\docs\agent\README.md => True
.\docs\agent\skill-registry.md => True
.\docs\agent\operator-lifecycle.md => True
```

- [ ] **Step 5: Verify reserved slots are marked inactive**

Run:

```powershell
Select-String -LiteralPath .\docs\agent\skill-registry.md -Pattern 'reserved, inactive','must not contain a `SKILL.md`'
```

Expected: matches for both reserved skill slots.

- [ ] **Step 6: Commit**

Run:

```powershell
git add docs/agent
git commit -m "docs: add agent framework documentation"
```

Expected: commit succeeds with three files added.

---

### Task 3: Create Operational Memory Templates

**Files:**
- Create: `agent-memory/README.md`
- Create: `agent-memory/templates/run-summary.md`
- Create: `agent-memory/templates/failure-ledger.json`
- Create: `agent-memory/templates/artifact-index.md`
- Create: `agent-memory/templates/human-notes.md`

- [ ] **Step 1: Create `agent-memory/README.md`**

Create `agent-memory/README.md` with this exact content:

```markdown
# Agent Memory

This directory stores operational memory for the MathOS Knowledge-Graph Implementation Operator.

The agent records execution facts:

- What stage ran.
- What command or workflow ran.
- What outputs were produced.
- What failures occurred.
- Where logs and artifacts were saved.

The agent does not record judgments about mathematical correctness or content quality unless a future human-approved skill explicitly changes that responsibility.

## Templates

- `templates/run-summary.md`: stage-level run summary.
- `templates/failure-ledger.json`: structured failure categories and counts.
- `templates/artifact-index.md`: generated files, folders, logs, and manifests.
- `templates/human-notes.md`: user-approved notes and future work.

Create dated run records from these templates when executing implemented stages.
```

- [ ] **Step 2: Create `agent-memory/templates/run-summary.md`**

Create `agent-memory/templates/run-summary.md` with this exact content:

```markdown
# Run Summary

## Stage

- Name:
- Skill:
- Command or workflow:

## Time

- Started:
- Finished:
- Duration:

## Status

- Completion status:
- Stop reason:
- User intervention needed:

## Counts

- Input files:
- Processed files:
- Generated files:
- Failed files:
- Skipped files:
- Warnings:

## Outputs

- Output folders:
- Generated files:
- Logs:
- Manifests:
- Temporary artifacts:

## Notes

- Operational observations:
- Next recommended operational step:

## Boundary Reminder

This summary records execution facts and output inventory. It does not judge content correctness.
```

- [ ] **Step 3: Create `agent-memory/templates/failure-ledger.json`**

Create `agent-memory/templates/failure-ledger.json` with this exact content:

```json
{
  "stage": "",
  "skill": "",
  "command_or_workflow": "",
  "status": "",
  "failure_counts": {
    "process_crash": 0,
    "non_zero_exit": 0,
    "conversion_failure": 0,
    "missing_dependency": 0,
    "missing_api_key": 0,
    "stalled_polling": 0,
    "missing_output": 0,
    "skipped_file": 0,
    "warning": 0
  },
  "failed_items": [],
  "log_paths": [],
  "stopped": false,
  "stop_reason": ""
}
```

- [ ] **Step 4: Create `agent-memory/templates/artifact-index.md`**

Create `agent-memory/templates/artifact-index.md` with this exact content:

```markdown
# Artifact Index

## Stage

- Name:
- Skill:
- Run summary:

## Inputs

- Source paths:

## Outputs

- Output directories:
- Generated Markdown files:
- Generated media files:
- Logs:
- Manifests:
- Temporary directories:

## Counts

- Input files:
- Output files:
- Temporary files:

## Cleanup Notes

- Files safe to delete:
- Files to preserve:
```

- [ ] **Step 5: Create `agent-memory/templates/human-notes.md`**

Create `agent-memory/templates/human-notes.md` with this exact content:

```markdown
# Human Notes

## Context

- Date:
- Stage:
- Related run summary:

## User-Approved Notes

- 

## Future Work

- 

## Decisions

- 

## Boundary Reminder

These notes do not change agent behavior by themselves. Skill changes require separate human-approved implementation work.
```

- [ ] **Step 6: Verify memory templates**

Run:

```powershell
$files = @(
  '.\agent-memory\README.md',
  '.\agent-memory\templates\run-summary.md',
  '.\agent-memory\templates\failure-ledger.json',
  '.\agent-memory\templates\artifact-index.md',
  '.\agent-memory\templates\human-notes.md'
)
$files | ForEach-Object { "$_ => $(Test-Path -LiteralPath $_)" }
```

Expected all lines end with `=> True`.

- [ ] **Step 7: Verify failure ledger JSON parses**

Run:

```powershell
Get-Content -LiteralPath .\agent-memory\templates\failure-ledger.json -Raw | ConvertFrom-Json | Select-Object -ExpandProperty failure_counts
```

Expected: object with keys such as `process_crash`, `conversion_failure`, and `missing_output`.

- [ ] **Step 8: Commit**

Run:

```powershell
git add agent-memory
git commit -m "docs: add agent operational memory templates"
```

Expected: commit succeeds with five files added.

---

### Task 4: Create Agent Proposal Holding Area

**Files:**
- Create: `agent-proposals/README.md`

- [ ] **Step 1: Create `agent-proposals/README.md`**

Create `agent-proposals/README.md` with this exact content:

```markdown
# Agent Proposals

This directory holds human-facing observations, future requests, and pending decisions related to the MathOS Knowledge-Graph Implementation Operator.

The first-version agent may record operational observations here when a run reveals a repeatable implementation issue.

Entries in this directory do not change agent behavior by themselves.

Skill changes require separate human-approved implementation work.

## Accepted Uses

- Record a repeatable operational failure pattern.
- Save a user-requested future improvement.
- Link a proposal to a run summary in `agent-memory/`.
- Capture a decision that should be reviewed before future implementation work.

## Boundaries

- Do not use this directory for generated Markdown content review.
- Do not use this directory to auto-author skills.
- Do not treat a proposal as approval to modify `SKILL.md` files.
```

- [ ] **Step 2: Verify proposal boundary language**

Run:

```powershell
Select-String -LiteralPath .\agent-proposals\README.md -Pattern 'do not change agent behavior','Skill changes require separate human-approved implementation work','Do not use this directory to auto-author skills'
```

Expected: three matching lines.

- [ ] **Step 3: Commit**

Run:

```powershell
git add agent-proposals/README.md
git commit -m "docs: add agent proposal holding area"
```

Expected: commit succeeds with `agent-proposals/README.md` added.

---

### Task 5: Create Active PDF-To-Markdown Operator Skill

**Files:**
- Create: `skills/mathos-pdf-to-md/SKILL.md`

- [ ] **Step 1: Create `skills/mathos-pdf-to-md/SKILL.md`**

Create `skills/mathos-pdf-to-md/SKILL.md` with this exact content:

````markdown
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
````

- [ ] **Step 2: Verify the skill metadata**

Run:

```powershell
Select-String -LiteralPath .\skills\mathos-pdf-to-md\SKILL.md -Pattern 'name: mathos-pdf-to-md','PDF to Markdown conversion','does not judge','Stop when failed files are at least 5'
```

Expected: four matching lines.

- [ ] **Step 3: Verify the skill does not assign content-review responsibility**

Run:

```powershell
Select-String -LiteralPath .\skills\mathos-pdf-to-md\SKILL.md -Pattern 'mathematically correct','Do not review output Markdown'
```

Expected: two matching lines that explicitly deny content-review responsibility.

- [ ] **Step 4: Commit**

Run:

```powershell
git add skills/mathos-pdf-to-md/SKILL.md
git commit -m "docs: add PDF to Markdown operator skill"
```

Expected: commit succeeds with `SKILL.md` added.

---

### Task 6: Create Reserved Future Skill Slots

**Files:**
- Create: `skills/mathos-word-to-md/README.md`
- Create: `skills/mathos-formatting/README.md`

- [ ] **Step 1: Create `skills/mathos-word-to-md/README.md`**

Create `skills/mathos-word-to-md/README.md` with this exact content:

```markdown
# mathos-word-to-md

Status: reserved, inactive.

This directory reserves the future repo-local skill slot for Word/DOCX to Markdown conversion.

Do not add `SKILL.md` until the detailed behavior is designed and approved.

The first-version Knowledge-Graph Implementation Operator must report that this skill is not active yet if a task requires it.
```

- [ ] **Step 2: Create `skills/mathos-formatting/README.md`**

Create `skills/mathos-formatting/README.md` with this exact content:

```markdown
# mathos-formatting

Status: reserved, inactive.

This directory reserves the future repo-local skill slot for batch Markdown formatting.

Do not add `SKILL.md` until the detailed behavior is designed and approved.

The first-version Knowledge-Graph Implementation Operator must report that this skill is not active yet if a task requires it.
```

- [ ] **Step 3: Verify reserved slots do not contain active skill files**

Run:

```powershell
Test-Path -LiteralPath .\skills\mathos-word-to-md\SKILL.md
Test-Path -LiteralPath .\skills\mathos-formatting\SKILL.md
```

Expected:

```text
False
False
```

- [ ] **Step 4: Verify reserved slot text**

Run:

```powershell
Select-String -LiteralPath .\skills\mathos-word-to-md\README.md,.\skills\mathos-formatting\README.md -Pattern 'reserved, inactive','Do not add `SKILL.md`'
```

Expected: matches in both files.

- [ ] **Step 5: Commit**

Run:

```powershell
git add skills/mathos-word-to-md/README.md skills/mathos-formatting/README.md
git commit -m "docs: reserve future MathOS skill slots"
```

Expected: commit succeeds with two README files added.

---

### Task 7: Final Verification

**Files:**
- Verify: all files created in Tasks 1-5

- [ ] **Step 1: Verify complete file inventory**

Run:

```powershell
$expected = @(
  '.\AGENTS.md',
  '.\docs\agent\README.md',
  '.\docs\agent\skill-registry.md',
  '.\docs\agent\operator-lifecycle.md',
  '.\agent-memory\README.md',
  '.\agent-memory\templates\run-summary.md',
  '.\agent-memory\templates\failure-ledger.json',
  '.\agent-memory\templates\artifact-index.md',
  '.\agent-memory\templates\human-notes.md',
  '.\agent-proposals\README.md',
  '.\skills\mathos-pdf-to-md\SKILL.md',
  '.\skills\mathos-word-to-md\README.md',
  '.\skills\mathos-formatting\README.md'
)
$missing = $expected | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($missing) {
  $missing
  exit 1
}
'All expected agent framework files exist.'
```

Expected:

```text
All expected agent framework files exist.
```

- [ ] **Step 2: Verify only PDF-to-Markdown is active**

Run:

```powershell
Get-ChildItem -Recurse -Filter SKILL.md .\skills | Select-Object -ExpandProperty FullName
```

Expected: only one result ending with:

```text
skills\mathos-pdf-to-md\SKILL.md
```

- [ ] **Step 3: Verify boundary language across framework files**

Run:

```powershell
Select-String -LiteralPath .\AGENTS.md,.\docs\agent\operator-lifecycle.md,.\skills\mathos-pdf-to-md\SKILL.md -Pattern 'does not judge','Do not review output Markdown','does not create, modify, or rewrite skills automatically'
```

Expected: matches confirming no content-review responsibility and no automatic skill rewriting.

- [ ] **Step 4: Verify JSON template remains valid**

Run:

```powershell
Get-Content -LiteralPath .\agent-memory\templates\failure-ledger.json -Raw | ConvertFrom-Json | Out-Null
'failure-ledger.json is valid JSON.'
```

Expected:

```text
failure-ledger.json is valid JSON.
```

- [ ] **Step 5: Check git status**

Run:

```powershell
git status --short
```

Expected: no tracked-file changes. The temporary `.superpowers/` browser companion directory may still appear untracked if the brainstorming preview is still present.

If `.superpowers/` is the only untracked item, leave it uncommitted.
