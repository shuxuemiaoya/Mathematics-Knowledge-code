# Textbook Node Architecture

Use this contract for source-faithful textbook conversion and for refining an
existing textbook corpus. Directory category and graph ownership are separate:
`知识点` or `习题` says where a file is stored; `node_type` and
`organizer_type` say what the file does.

## Physical folders mirror ownership

Category directories remain the top-level partition, but notes inside a
category must not be flattened into one lesson directory. Mirror reviewed
ownership with the folder-index convention:

1. every node that owns lower-level notes has a same-named folder;
2. the owner's note is stored inside that folder with the same name;
3. each leaf note is stored in its direct owner's folder;
4. a cross-category child restarts under its category root while retaining its
   chapter context.

For example, the reviewed `1.1 集合的概念` architecture is physically shaped
like this (the exact theme names still come from semantic review):

```text
知识点/第一章 集合与常用逻辑用语/1.1 集合的概念/
├── 1.1 集合的概念.md
├── 集合的基本概念/
│   ├── 集合的基本概念.md
│   ├── 情景导入 1.md
│   └── 集合.md
├── 集合的表达方式/
│   ├── 集合的表达方式.md
│   ├── 情景导入 2.md
│   ├── 列举法/
│   │   ├── 列举法.md
│   │   └── 例题 1.md
│   ├── 描述法/
│   │   ├── 描述法.md
│   │   └── 例题 2.md
│   └── 自然语言、列举法和描述法表示集合时各自的特点.md
└── 练习 1/
    ├── 练习 1.md
    ├── 课内练习 1.md
    ├── 课内练习 2.md
    └── 课内练习 3.md
```

Directories express containment, not reading order. Render every ownership
edge with the embedded Markdown-note form `![标题](目标.md)` at its original
source position. This `!` is required for organizer expansion in Obsidian. Do
not use bullet navigation syntax for ownership edges.

## Source atoms

Create source atoms only for complete source-backed units:

- `scenario`: the source prose, question, or situation that introduces one
  knowledge theme;
- `knowledge`: a coherent knowledge explanation with a complete teaching or
  derivation process;
- `worked-example`: one complete worked example, including its stem, analysis,
  solution, proof, diagrams, and answer;
- `practice-question`: one inline-practice question;
- `section-exercise-question`: one question belonging to the section exercise
  aggregate.

Do not create a source atom for a bare section lead-in or a synthesized
summary. Do not split a complete knowledge process merely to increase node
count. Use exact source names for source atoms and printed exercise
aggregates. Give synthesized knowledge-theme organizers concise semantic names
such as `集合的表达方式`; never use placeholders such as `组织1`.

An atom must not start with an artificial Markdown heading that merely repeats
its filename, such as `# 例题 1`. Preserve a meaningful heading inside the
source body when it is not a generated file title. The worked-example atom is
the problem itself, not an organizer that links another copy of the problem.

## Organizer ownership

Use `node_type: organizer` with one `organizer_type`:

- `book`: orders book-level material;
- `chapter`: orders chapter material;
- `section`: first-layer lesson/section organizer;
- `knowledge-theme`: groups a contiguous source-ordered sequence of related
  `scenario` and `knowledge` atoms;
- `practice`: links only the inline `practice-question` atoms under one printed
  `练习 N` block;
- `section-exercise`: links only the questions under the printed section
  exercise aggregate such as `习题1.1 集合的概念`.

Inside a section-exercise organizer, retain only the printed group labels
(`复习巩固`、`综合运用`、`拓广探索`), source presentation images, and the embedded
question links in their original order. Create exactly one atom for every
top-level numbered question and record a complete sequential `question_number`
series from 1 through n. Never place the whole exercise body in the final `Tn`
atom when earlier question boundaries are uncertain.

Enforce these edges:

| Parent | Allowed owned children |
| --- | --- |
| `section` | `knowledge-theme`, `practice`, `section-exercise`, or an ungrouped source-backed atom except `worked-example` and question atoms |
| `knowledge-theme` | `scenario`, `knowledge` |
| `knowledge` atom | `worked-example` |
| `practice` | `practice-question` |
| `section-exercise` | `section-exercise-question` |

An example must therefore be linked from its corresponding knowledge atom,
never directly from the section organizer. A `练习 N` organizer must never
link the section exercise aggregate. Keep that aggregate as a separate
second-layer target of the section organizer.

If a section organizer still contains actual exposition, move that complete
body into a `knowledge` atom and replace it at the same source position with a
link. A section organizer is not a fallback knowledge note.

## Source-order expansion

Record exact source ranges for every source-backed node. Require siblings to
be disjoint and ordered by their source starts. Members of a knowledge-theme
organizer must form one contiguous semantic run; do not group by adjacency
alone, and do not group related passages separated by another source role.

Validate order after recursive expansion:

```text
section
  -> knowledge-theme -> scenario/knowledge -> worked-example
  -> practice -> practice-question
  -> section-exercise -> section-exercise-question
```

The expanded sequence must reproduce the original file sequence exactly. A
moved child link occupies the child's original source position. Do not append
links later, alphabetize them, or add another grouping absent from the source.

## Existing-corpus refinement

Inventory the existing files and freeze hashes before editing. Reuse complete
existing source atoms; do not recreate them from OCR or overwrite them with a
new copy. Limit edits to ownership links, organizer creation, exact source-name
corrections, and repairs explicitly justified by the frozen source.

Apply changes in task-scoped staging. Audit the staged tree before replacing
the intended targets. On failure, discard the staged edits and leave the
existing corpus unchanged. Report unrelated pre-existing broken links
separately; they do not make an unchanged atom a failure of the current
architecture operation.

## Required manifest review

For a new textbook profile set
`decomposition.require_textbook_node_architecture: true`. Before splitting,
set `node_architecture.status: passed` only after a complete review records:

- `reviewed_entire_book: true`;
- `source_order_expansion: passed`;
- `source_content_preservation: passed`;
- `source_names_preserved: passed` for printed sections, atoms, practice
  blocks, and exercise aggregates; synthesized theme organizers are exempt;
- `physical_hierarchy: passed`, with every owner rendered as a same-named
  folder-index note and every leaf inside its direct owner's folder;
- one `node_type` for every node and one `organizer_type` for every organizer;
- `emit_title: false` for source atoms and second-layer theme/practice/exercise
  organizers.

The deterministic split draft is intentionally `review_required`. It cannot
infer semantic themes, example ownership, or question ownership safely from
headings or adjacency alone.
