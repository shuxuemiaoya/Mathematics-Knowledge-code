# 人教版高中必修第一册 Example Architecture

## Purpose

Use this standalone agent reference to understand the architecture demonstrated by:

```text
C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\临时\
├── 【人教版】高中必修 第一册数学电子课本.pdf
└── 课本\【人教版】高中必修 第一册数学电子课本\
```

Treat it as a process model, not a byte-for-byte template. Copy successful structural decisions; do not reproduce defects in the current live snapshot.

## Source Profile

The source is a 270-page, A4 mathematics textbook PDF of about 42.4 MB.

Representative visual classes:

- cover and publication front matter;
- a multi-page table of contents;
- chapter-opening narrative pages;
- ordinary lessons with examples, prompts, definitions, diagrams, and exercises;
- review exercises;
- readings, technology applications, explorations, and a mathematical modelling project;
- an index.

The source therefore requires structural OCR/Markdown conversion, semantic classification, asset preservation, and logic mapping. A heading-only splitter is insufficient.

## Final Corpus Shape

The inspected live example contained:

| Category | Markdown files |
| --- | ---: |
| Root/front matter | 2 |
| `知识点` | 124 |
| `概念` | 115 |
| `习题` | 30 |
| `思维或方法` | 3 |
| `趣味阅读` | 13 |
| `拓展知识点` | 5 |
| **Total** | **292** |

It also contained 266 raster images distributed primarily under category-local `images` directories.

The counts above describe the legacy example exactly. The revised standalone
pipeline always keeps the core `知识点`, `概念`, and `习题` roles, and preserves
an additional side-material role only when the printed TOC/source supports it
and the profile enables it. It does not recreate empty legacy directories.

The book-local canvas contained:

- 319 total nodes;
- 45 `group` nodes;
- 274 `text` nodes;
- 215 edges.

## Successful Content Layers

### Book entry

The root book note preserves front matter and the book introduction, then links to chapter navigation notes and book-level special material.

### Chapter navigation

Each chapter note preserves its introduction and links in source order to lessons, readings, chapter summaries, and review exercises.

### Lesson entry

A lesson entry remains the first-layer ordered organizer. It contains its
source heading and links to second-layer knowledge-theme, practice, and
section-exercise files in source order. Source-backed introductions and
transitions belong to `scenario` atoms; complete exposition belongs to
`knowledge` atoms. The lesson entry does not directly link worked examples or
individual questions.

Its physical directory is not flat. Each knowledge theme and practice group is
a same-named subfolder containing its same-named index note and direct leaves.
A knowledge atom with worked examples becomes the same kind of folder-index,
with the example notes inside it. The embedded links still define reading
order.

The accepted split does not rewrite the lesson into a summary. It changes presentation boundaries while preserving the original sequence.

### Knowledge topics

Substantial teaching arcs become `knowledge` atoms. They retain complete
definitions, proofs, formulas, tables, images, and reasoning relevant to that
topic, and link their worked-example atoms at the examples' original source
positions. Related contiguous scenario/knowledge atoms may be grouped by a
semantic organizer such as `集合的表达方式`.

### Practice and exercise layers

Each printed `练习 N` becomes a link-only practice organizer containing only
its inline-practice question atoms. The printed section aggregate
`习题X.Y <小节标题>` is a separate second-layer organizer containing only its
own exercise-question atoms; it is never embedded inside `练习 N`.

Every section exercise and review exercise is split at its complete sequential
top-level question numbers. Preserve the book's printed group headings in the
organizer. After splitting, inspect internal `(1)…(n)` subparts against the PDF
for column interleaving, missing labels, and list numbers misread as equation
`\tag` values; fix only with source-backed exact repairs.

Source atoms and second-layer theme/practice/exercise organizers do not receive
artificial Markdown headings that repeat their filenames.

### Concepts

Formal definitions become flat `概念/<name>.md` notes. The definition occurrence in the knowledge note links to the concept note. Concept notes may link to other defined concepts when the source definition genuinely depends on them.

### Side material

- `习题`: section and chapter review exercises;
- `思维或方法`: explicit mathematical methods or modelling activities;
- `趣味阅读`: readings, history, technology applications, and writing activities;
- `拓展知识点`: useful but non-core extensions supported by a source context.

## Successful Canvas Grammar

The canvas is organized by mathematical logic rather than page order alone:

- chapter and topic regions are groups;
- lesson/topic cards sit within those groups;
- concepts, exercises, readings, methods, tools, and extensions branch from relevant knowledge;
- most containment/progression edges are unlabeled;
- named edges express relations such as substitution, transformation, generalization, inverse use, or parameter effects.

Observed node colors:

| Color | Meaning |
| --- | --- |
| `1` | super-core knowledge |
| `2` | knowledge point or concept |
| `3` | interdisciplinary or outside-chapter knowledge |
| `4` | thinking method or technique |
| `5` | story, history, or extracurricular reading |
| `6` | question type |
| `#c800ff` | mathematical tool |
| absent | organizational or intentionally neutral |

Observed edge colors:

| Color | Meaning |
| --- | --- |
| `2` | reasoning or inference |
| `4` | inspiration or method transfer |
| `5` | calculation |
| `6` | application |
| absent | containment, classification, or local sequence |

## Do Not Copy Current Snapshot Defects

A whole-tree audit of the live snapshot on 2026-07-23 found useful warning signs:

- residual Wikilinks remained even though the dominant convention was standard Markdown links;
- several concept-source backlinks pointed to the wrong directory level;
- some image references lacked a corresponding local asset;
- several canvas cards used relative paths that did not resolve from the canvas location;
- some canvas cards referenced adjacent vault content that must be validated against the actual vault root.

These defects explain why the new workflow uses strict pre-canvas and final audits. A visually plausible Obsidian corpus is not complete until every internal target resolves.

## Process Reconstruction

The stable end-to-end process is:

1. inspect PDF layout and TOC;
2. convert PDF to Markdown and extracted assets;
3. build a manifest from the printed TOC;
4. align TOC entries to H1-H3 and demote all other headings below H3;
5. split by the TOC hierarchy and reviewed nested source ranges;
   reject a TOC-only manifest, split every numbered subsection and section
   exercise, retain unnumbered non-TOC blocks by default, and record a
   confidence-backed disposition for every H4-H6 content heading;
   then inspect every long generated knowledge-node body, including numbered
   H4-H6 subsections, for headerless teaching arcs such as a definition
   followed by its examples, because many accepted example notes (`集合`,
   `最大值与最小值`, and similar topics) did not begin at an explicit source
   heading;
   within each lesson, split retained prose again at every functional heading
   or label, exposition/definition cue, worked-example label, and practice
   heading; never approve one logical block across the next boundary;
6. retain child links in parent notes at their original source positions;
   render those navigation links as bullet items, promote independent semantic
   note entry headings to H3, and disambiguate generic chapter summaries with
   their chapter title;
7. categorize textbook output into the three core roles plus only
   source-supported auxiliary reading, history, method, or tool roles;
8. extract only formally defined concepts;
   structure each concept note as H1 title, source backlink, H2 definition,
   and the complete copied definition;
9. standardize callouts, formulas, tables, and images without changing protected content;
   convert functional labels to continuous quoted callout containers, keep all
   body lines at the required quote depth, and do not pass audit with residual
   raw markers, missing quoted bodies, invalid nested callouts, duplicated
   source labels, or later definitions/examples/practice swallowed by an
   earlier callout;
10. validate all note and asset targets;
11. design and compile an optional domain-based logic canvas;
12. run a whole-corpus audit.
