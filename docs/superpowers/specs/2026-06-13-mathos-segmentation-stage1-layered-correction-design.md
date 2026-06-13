# MathOS Segmentation Stage One Layered Correction Design

Date: 2026-06-13

## Summary

This correction modifies the existing `mathos-segmentation-stage1` operator in place. It does not create a new skill, new CLI, or Stage One v2.

The corrected operator still runs after `mathos-formatting`, still writes a source-stem Obsidian sandbox folder, still preserves the original source Markdown, and still exposes `plan` and `segment` commands. The change is the segmentation model:

- Before: one flat master directory linking to deepest numbered headings.
- After: a layered Obsidian directory package where every non-leaf note links only to its immediate children, and only leaf notes contain raw source text slices.

## Goals

- Build a full layered heading tree from the formatted textbook body.
- Keep the master directory clean by linking only to top-level chapter notes.
- Keep every non-leaf note as a pure directory note containing only `# 目录`, a blank line, and immediate-child file links.
- Write raw source slices only into leaf notes.
- Preserve full structural prefixes in filenames, such as `6.1.1 向量的实际背景与概念.md`.
- Generate clean Obsidian file links, such as `[[6.1 平面向量的概念]]`, with no `#`, `##`, or heading-anchor syntax inside the link.
- Merge special heading pairs such as `## 阅读与思考` plus `### 向量及向量符号的由来` into one leaf node named `阅读与思考 向量及向量符号的由来`.
- Preserve non-destructive behavior: the source Markdown is never modified or deleted.

## Non-Goals

- Do not create a new skill name or parallel `v2` implementation.
- Do not call an LLM.
- Do not classify concepts, problems, explorations, examples, or exercises.
- Do not polish or rewrite raw leaf content.
- Do not use Obsidian heading-anchor links such as `[[# 第六章 ...]]` or `[[## 6.1 ...]]`.
- Do not split special merged pairs into separate parent and child notes.

## Corrected Output Shape

For a source:

```text
高中\课本\【人教版】高中必修 第二册数学电子课本.md
```

the sandbox folder remains:

```text
高中\课本\【人教版】高中必修 第二册数学电子课本\
```

The master directory file remains:

```text
000_【人教版】高中必修 第二册数学电子课本目录.md
```

but its content changes from flat deepest-heading links to top-level chapter links:

```markdown
# 目录

- [[第六章 平面向量及其应用]]
- [[第七章 复数]]
- [[第八章 立体几何初步]]
```

A chapter note such as:

```text
第六章 平面向量及其应用.md
```

contains only its immediate children:

```markdown
# 目录

- [[6.1 平面向量的概念]]
- [[阅读与思考 向量及向量符号的由来]]
- [[6.2 平面向量的运算]]
- [[6.3 平面向量基本定理及坐标表示]]
- [[6.4 平面向量的应用]]
- [[阅读与思考 海伦和秦九韶]]
- [[小结]]
- [[复习参考题6]]
- [[数学探究 用向量法研究三角形的性质]]
```

A section note such as:

```text
6.1 平面向量的概念.md
```

contains only immediate children:

```markdown
# 目录

- [[6.1.1 向量的实际背景与概念]]
- [[6.1.2 向量的几何表示]]
- [[6.1.3 相等向量与共线向量]]
- [[习题6.1]]
```

A leaf note such as:

```text
6.1.1 向量的实际背景与概念.md
```

contains the raw source slice for that heading. The script must not prepend a new heading, front matter, comments, or metadata.

## File Link Semantics

All directory notes use file links to physical note files:

```markdown
- [[第六章 平面向量及其应用]]
- [[6.1 平面向量的概念]]
- [[6.1.1 向量的实际背景与概念]]
```

The link text is the note filename stem. The implementation must strip Markdown heading markers from link targets. These are invalid for this operator:

```markdown
- [[# 第六章 平面向量及其应用]]
- [[## 6.1 平面向量的概念]]
```

When filenames are disambiguated, directory links must target the actual disambiguated note stem.

## Leaf Naming

Leaf filenames must retain their full structural prefix:

```text
6.1.1 向量的实际背景与概念.md
6.1.2 向量的几何表示.md
6.1.3 相等向量与共线向量.md
```

This keeps Obsidian file explorer sorting aligned with textbook order even outside directory notes.

Non-numbered leaves also keep meaningful textbook labels:

```text
阅读与思考 向量及向量符号的由来.md
小结.md
复习参考题6.md
数学探究 用向量法研究三角形的性质.md
```

## Tree Construction

The corrected splitter should build a `DirectoryNode` tree from body headings after the formatted TOC/front matter has been stripped by `mathos-formatting`.

The tree should treat textbook chapter headings as top-level structural nodes. Examples:

```text
# 第六章 平面向量及其应用
# 第七章 复数
# 第八章 立体几何初步
```

Numbered section headings become children according to number depth:

```text
## 6.1 平面向量的概念
### 6.1.1 向量的实际背景与概念
### 6.1.2 向量的几何表示
```

The parent-child relationship must be strict:

- master directory -> chapter nodes only;
- chapter node -> section/special nodes only;
- section node -> immediate child leaves only;
- non-leaf nodes never contain raw body text.

## Special Heading Pair Merge

Some textbook entries are represented in the body as a generic heading followed by a specific subheading:

```markdown
## 阅读与思考

### 向量及向量符号的由来
```

The corrected splitter must merge this pair into one leaf node:

```text
阅读与思考 向量及向量符号的由来.md
```

The raw slice for that leaf starts at the generic heading:

```markdown
## 阅读与思考
```

and continues through the specific subheading and its body until the next valid sibling heading, for example:

```markdown
## 6.2 平面向量的运算
```

The `### 向量及向量符号的由来` heading is swallowed into the leaf body. It must not create a separate child note.

The same merge behavior applies to repeated textbook special labels when followed by a single specific subheading:

- `阅读与思考` + following specific heading;
- `数学探究` + following specific heading.

The implementation may keep the special label list explicit and conservative. It should not merge arbitrary `##` + `###` pairs.

## Leaf Slice Boundaries

Leaf slices must start at the source heading that introduced the leaf:

- standard numbered leaf: starts at its own numbered heading;
- merged special leaf: starts at the generic special heading, not the specific child heading;
- non-numbered standalone leaf such as `小结`: starts at its own heading.

Leaf slices end before the next heading that is outside the leaf's subtree:

- a standard `6.1.1` leaf ends before `6.1.2`;
- the final leaf under `6.1` ends before the next `##` sibling;
- a merged `阅读与思考 ...` leaf ends before the next `##` sibling;
- the final leaf under a chapter ends before the next chapter heading.

## Directory File Rules

Every non-leaf note, including the master file, must contain only:

- `# 目录`;
- a blank line;
- one `- [[...]]` line per immediate child.

No non-leaf note may include:

- raw textbook paragraphs;
- YAML front matter;
- source path comments;
- generated explanations;
- links to grandchildren.

## Plan Command Behavior

`plan` remains non-writing. Its JSON should report:

- total node count;
- directory node count;
- leaf node count;
- top-level child count;
- special merges;
- disambiguations;
- warnings;
- planned files;
- next `segment` command.

The old `segments` count should be reinterpreted or renamed carefully in run records. To avoid ambiguity, new records should include both:

- `nodes`: all planned note files;
- `leaf_nodes`: raw-slice files only.

## Segment Command Behavior

`segment` writes:

- one master directory file;
- one note file for every tree node;
- directory content for non-leaf nodes;
- raw slices for leaf nodes;
- run records under `agent-memory/records/<date>-segmentation-stage1-<slug>/`.

It still refuses to write without `--yes`, and still refuses to overwrite an existing sandbox folder unless `--overwrite` is explicitly passed.

## Verification

Verification must check:

- the master file links only to top-level child files;
- every non-leaf file contains only immediate-child links;
- no directory file links to grandchildren;
- every generated link target has a matching `.md` file in the sandbox folder;
- every leaf node has a non-empty raw slice;
- merged special-pair leaves include both the generic and specific headings in the raw slice;
- no standalone `阅读与思考.md` file is generated for merged pairs;
- no `#` or `##` marker appears inside wikilink targets;
- original source Markdown hash remains unchanged.

## Testing Requirements

Add or update tests for:

- master links only to chapters for a sample containing chapters, sections, and leaves;
- chapter note links only to immediate children;
- section note links only to immediate children;
- leaf note writes raw source text;
- non-leaf note contains no raw source text;
- full numeric prefix is retained for leaf filenames;
- wikilinks use clean filename stems with no heading markers;
- `阅读与思考` + specific child heading is merged into one leaf;
- merged special leaf raw slice starts at `## 阅读与思考` and includes the `###` subheading;
- no separate `阅读与思考.md` file is generated for the merged pair;
- duplicate/case-insensitive filename disambiguation still works;
- `plan` writes nothing;
- `segment` writes package and records;
- source file remains unchanged.

## Compatibility Notes

This is a behavior correction for the existing operator. It is acceptable for existing flat Stage One outputs to be regenerated with `--overwrite` after review.

Existing command names and skill documentation should remain stable. The docs should be updated to describe layered directory output instead of flat deepest-heading output.
