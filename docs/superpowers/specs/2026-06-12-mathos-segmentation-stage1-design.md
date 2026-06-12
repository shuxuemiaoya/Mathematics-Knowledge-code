# MathOS Segmentation Stage One Design

Date: 2026-06-12

## Summary

`mathos-segmentation-stage1` is a downstream MathOS operator that runs after `mathos-formatting`. It converts one formatted long Markdown file into a self-contained Obsidian sandbox package:

- a master directory file containing only a clean heading tree and short Obsidian links;
- one raw segment note per target numbered heading;
- run records that make the operation auditable and resumable.

The skill does not clean text, judge mathematical correctness, identify concepts, classify exercises, or rewrite formulas. Its only job is deterministic skeletal segmentation.

## Context

The current MathOS flow is:

```text
PDF / Word -> Markdown -> Formatting -> Segmentation Stage One -> Segmentation Stage Two
```

Stage One consumes the output of `mathos-formatting`. It assumes the source Markdown has already been formatted enough that numbered headings can be trusted as physical boundaries.

Stage Two will later inspect these raw segment notes with an LLM to identify concepts, problems, explorations, and exercises, then move or split notes into more specialized folders.

## Goals

- Split formatted Markdown into the smallest useful physical units as quickly as possible.
- Default to the deepest numbered heading level detected in the source.
- Generate an Obsidian-native master backbone using pure short links.
- Preserve heading numbers in filenames so search results and moved notes retain logical order.
- Keep every generated artifact for a source file inside one sandbox folder named exactly after the source file stem.
- Leave the original source Markdown untouched as an immutable audit trail.
- Record machine-readable run state and manifests under `agent-memory/records`.

## Non-Goals

- Do not call an LLM.
- Do not repair OCR errors, formulas, or formatting.
- Do not classify content into concept, problem, exploration, or exercise folders.
- Do not modify or delete the original source Markdown.
- Do not produce polished atomic notes.
- Do not infer mathematical correctness or completeness.

## Operator Shape

The skill should follow the existing MathOS pattern: thin skill instructions, durable logic in scripts.

```text
skills/mathos-segmentation-stage1/
├── SKILL.md
└── scripts/
    └── mathos_segmentation_stage1.py
```

The `SKILL.md` should describe when to use the operator, required inputs, stop conditions, command shapes, and output summary requirements.

The Python script should implement all repeatable logic and write compact run records.

## Commands

### `plan`

```powershell
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py plan `
  "<source.md>" `
  --vault-root "<vault root>" `
  --yes
```

`plan` scans the source Markdown and reports:

- source path;
- vault root;
- output sandbox folder;
- planned master directory path;
- detected numbered heading levels;
- selected target depth;
- planned segment count;
- duplicate filename disambiguations;
- empty or suspicious segment candidates;
- largest planned segments;
- exact next `segment` command.

It must not write content files.

### `segment`

```powershell
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment `
  "<source.md>" `
  --vault-root "<vault root>" `
  --yes
```

`segment` writes the sandbox package and run records. It should refuse to write if the sandbox folder already exists unless an explicit overwrite flag is provided.

An optional `--target-depth <n>` may override the default deepest numbered heading level.

## File Semantics

For this source:

```text
高中\课本\【人教版】高中必修 第一册数学电子课本.md
```

the output package is:

```text
高中\课本\【人教版】高中必修 第一册数学电子课本\
├── 000_【人教版】高中必修 第一册数学电子课本目录.md
├── 1.1.1 集合的概念.md
├── 1.1.2 集合的基本关系.md
└── 1.2.1 函数的概念.md
```

The parent directory receives only the sandbox folder. No generated segment files or helper files are scattered directly into the parent directory.

The original source Markdown remains untouched:

```text
高中\课本\【人教版】高中必修 第一册数学电子课本.md
```

## Master Directory Format

The master directory file is the only intentionally structured content artifact.

It must contain only:

- `# 目录`;
- tree-like Markdown list indentation;
- pure Obsidian short links.

Example:

```markdown
# 目录

- [[1.1.1 集合的概念]]
- [[1.1.2 集合的基本关系]]
- [[1.2.1 函数的概念]]
```

The master file must not include prose explanations, YAML front matter, status metadata, source excerpts, or generated comments.

Because segment files live in the same physical folder as the master directory, links should use note titles only. This keeps the syntax clean and lets Obsidian update links if Stage Two later moves notes into other folders.

## Segment File Format

Each segment file contains the raw text slice exactly as taken from the formatted source Markdown.

The script must not prepend:

- a new H1 heading;
- YAML front matter;
- metadata comments;
- source path annotations;
- generated summaries.

The boundary heading from the source is included only if it is part of the raw slice. Stage One should not synthesize replacement headings.

## Heading Detection

The splitter treats numbered Markdown headings as the structural contract. It should detect heading numbers such as:

```text
1
1.1
1.1.1
10.2.3
```

The default target depth is the deepest numbered heading level detected in the source. Parent numbered headings become tree nodes in the master directory. Target-depth headings become linked segment notes.

If the user passes `--target-depth`, the script uses that depth instead and reports the override in the manifest.

## Filename Rules

Segment filenames must preserve structural heading numbers:

```text
1.1.1 集合的概念.md
```

A filename without its number is invalid:

```text
集合的概念.md
```

If two planned filenames collide, the script should first rely on the heading number to make them distinct. If a collision still remains, append a sequential suffix:

```text
1.1.2 练习.md
1.1.2 练习 - 02.md
```

The manifest must record every disambiguation.

## Run Records

Each run writes records under:

```text
agent-memory/records/<date>-segmentation-stage1-<slug>/
```

Required files:

- `run-state.json`: compact status, counts, key paths, warnings, and next step.
- `manifest.json`: full segment plan, written files, heading tree, disambiguations, hashes, and warnings.
- `run-summary.md`: human-readable output summary.

Optional file:

- `warnings.json`: detailed warning list if the warning payload is too large for `run-state.json`.

Run records live in the code repo. Generated Obsidian content lives in the content vault.

## Stop Conditions

Stop before writing or preserve partial records when any of these occur:

- source file is missing or empty;
- source path is not under the provided vault root;
- no numbered headings are detected;
- selected target depth produces zero segments;
- output sandbox folder already exists and overwrite was not explicitly requested;
- duplicate filenames cannot be safely disambiguated;
- a planned segment would be empty;
- any write fails partway through;
- original source hash changes during execution.

## Verification

After `segment`, the script verifies:

- the sandbox folder exists;
- the master directory exists inside the sandbox folder;
- the master directory contains only `# 目录`, Markdown list indentation, blank lines, and `[[...]]` links;
- every link target has exactly one matching `.md` segment file in the sandbox folder;
- segment file count equals manifest segment count;
- original source Markdown hash is unchanged;
- `run-state.json` records status, paths, counts, warnings, and next step.

If verification fails, `run-state.json` should mark the run as failed and point to the manifest or warning details.

## Required Output Summary

Every completed or stopped run must report:

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

## Approved Design Decisions

- Stage One runs after `mathos-formatting`.
- Use the deterministic heading splitter approach.
- Output directly into the content vault.
- Encapsulate all generated content for one source file inside a single sandbox folder named exactly after the source file stem.
- Use native short Obsidian links because master and segment files live together.
- Do not add headings or metadata to segment files.
- Never delete or modify the original formatted source Markdown during Stage One.
