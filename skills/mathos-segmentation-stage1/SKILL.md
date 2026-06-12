---
name: mathos-segmentation-stage1
description: Use after mathos-formatting to split one formatted Markdown file into an Obsidian sandbox package with a master directory and raw segment notes.
---

# MathOS Segmentation Stage One Operator

Status: operational.

Use this operator after `mathos-formatting` when one formatted long Markdown file should be split by numbered headings into raw Obsidian notes.

This skill does not call an LLM, clean content, classify concepts, classify exercises, judge mathematical correctness, or modify the original source Markdown.

## Workflow

Run a plan first:

```powershell
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py plan `
  "<source.md>" `
  --vault-root "<vault root>" `
  --yes
```

Then write the sandbox package:

```powershell
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment `
  "<source.md>" `
  --vault-root "<vault root>" `
  --yes
```

Use `--target-depth <n>` only when the deepest numbered heading level is not the desired physical unit.

Use `--overwrite` only after confirming the existing sandbox folder may be replaced.

## Output Semantics

For `高中\课本\book.md`, output is written to:

```text
高中\课本\book\
├── 000_book目录.md
├── 1.1.1 first segment.md
└── 1.1.2 second segment.md
```

The master directory uses short Obsidian links because it lives beside the segment files.

Segment files contain raw source slices. The operator does not prepend headings, front matter, comments, or metadata.

The original source Markdown is never modified or deleted.

## Stop Conditions

Stop and report when:

- source file is missing, empty, or not Markdown;
- source path is not under the provided vault root;
- no numbered headings are detected;
- target depth produces zero segments;
- output sandbox folder already exists without `--overwrite`;
- a planned segment would be empty;
- writing or verification fails;
- original source hash changes during execution.

## Required Output Summary

Report:

- Stage name: `segmentation-stage1`;
- Skill: `skills/mathos-segmentation-stage1`;
- Source Markdown path;
- Vault root;
- Command used;
- Completion status;
- Stop reason, if stopped;
- Sandbox folder path;
- Master directory path;
- Segment count;
- Warning count;
- Duplicate disambiguation count;
- Run record folder;
- Next operational step.
