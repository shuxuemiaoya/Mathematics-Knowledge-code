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
├── 第六章 平面向量及其应用.md
├── 6.1 平面向量的概念.md
├── 6.1.1 向量的实际背景与概念.md
└── 阅读与思考 向量及向量符号的由来.md
```

The master directory links only to top-level chapter files.

Every non-leaf note contains only `# 目录` plus immediate-child file links.

Leaf notes contain raw source slices. The operator does not prepend headings, front matter, comments, or metadata.

Special pairs such as `## 阅读与思考` followed by `### 向量及向量符号的由来` are merged into one leaf note.

The original source Markdown is updated in-place to serve as the master directory note (containing the book preface and links to H1 chapters), and a backup of the original source file is created next to it with a `.md.bak` suffix.

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
