# Repo-Local Knowledge-Graph Agent Design

Date: 2026-06-05

## Purpose

Create a repo-local Codex agent system for `Mathematics-Knowledge-code`. The agent is a Knowledge-Graph Implementation Operator: it coordinates the implementation and operation of the mathematics knowledge-graph build framework.

The first version focuses on the agent framework, role, memory, run reporting, and scope boundaries. It does not implement the whole graph pipeline and does not make the agent a skill author.

## Core Role

The agent is responsible for the overall implementation of the knowledge-graph workflow:

```text
PDF / Word -> Markdown -> Formatting -> Future graph stages
```

The agent operates repo-local skills and workflows as they become available. Its first concrete skill target is:

```text
skills/mathos-pdf-to-md
```

Two additional skill slots are reserved for later integration:

```text
skills/mathos-word-to-md
skills/mathos-formatting
```

The agent does not judge whether generated Markdown is mathematically correct, academically complete, or well formatted. It also does not review edits. Instead, it monitors task execution, summarizes outputs, records operational facts, and stops unsafe or repeatedly failing runs.

## Repo-Local Structure

The first version should establish a project-local agent system with these intended areas:

```text
AGENTS.md
skills/
  mathos-pdf-to-md/
  mathos-word-to-md/
  mathos-formatting/
agent-memory/
agent-proposals/
docs/agent/
```

`AGENTS.md` defines the project-level operating contract: scope, safety, repo-local behavior, stop rules, and output-summary requirements.

`skills/mathos-pdf-to-md` is the first concrete skill slot. Its first expected behavior is operational monitoring around PDF to Markdown conversion.

`skills/mathos-word-to-md` and `skills/mathos-formatting` are named future skill slots. Their detailed behavior is intentionally out of scope for this first design.

`agent-memory/` stores human-readable records of runs, failures, artifacts, and user-approved notes.

`agent-proposals/` can hold future human-facing observations or pending decisions, but the first version does not allow the agent to create or modify skills.

`docs/agent/` stores human-readable documentation for the agent lifecycle and operating rules.

## Operating Loop

For each implemented stage, the agent follows this loop:

1. Select the appropriate repo-local skill or workflow.
2. Execute the skill task or command.
3. Monitor execution health.
4. Summarize stage outputs.
5. Stop or continue based on operational state.

The agent may stop a stage when operational failure becomes significant. For `mathos-pdf-to-md`, examples include repeated Python crashes, numerous conversion failures, missing API keys, missing dependencies, stalled polling, or missing output folders.

The agent must preserve logs and report the reason for stopping. If the stage completes, it must still report a summary of outputs.

## Required Output Summary

Every completed or stopped stage must include an output summary. The agent does not review the edits or judge output correctness, but it must report the inventory and status of the stage.

Each output summary should include:

- Stage name.
- Command, workflow, or skill used.
- Start and end time when available.
- Completion status: completed, stopped early, failed, or needs user intervention.
- Output folders and generated files.
- Counts such as processed files, generated files, failed files, skipped files, and warnings.
- Failure categories and representative log references.
- Location of logs, manifests, temporary outputs, and final artifacts.

## Save Mechanism

The save mechanism is a lightweight operational memory. It records execution facts, not content-quality judgments.

Saved records should include:

- Run summary: stage, command, time range, status, output locations, counts.
- Failure ledger: crashes, repeated conversion failures, skipped files, dependency errors, stopped tasks.
- Artifact index: generated folders, logs, manifests, temporary files, and final outputs.
- Human notes: optional user-approved observations or future tasks.

Records should be plain Markdown or simple JSON so a human can inspect runs and decide what to build next.

## Scope Boundaries

In scope for the first version:

- Define the repo-local agent role and operating contract.
- Establish the initial skill registry names.
- Define operational monitoring behavior for `mathos-pdf-to-md`.
- Define required output summaries for every stage.
- Define lightweight run memory templates.

Out of scope for the first version:

- Judging content correctness.
- Reviewing Markdown edits.
- Designing detailed behavior for `mathos-word-to-md` or `mathos-formatting`.
- Implementing every graph stage.
- Creating, modifying, or rewriting skills automatically.
- Building a pure meta-agent or self-improvement loop.

## Success Criteria

The design is successful when the project has a clear, repo-local agent framework that can guide implementation of the first operator version. A future implementation plan can then create the files and templates needed for the agent to coordinate `mathos-pdf-to-md`, monitor operational failures, save run records, and report output summaries.
