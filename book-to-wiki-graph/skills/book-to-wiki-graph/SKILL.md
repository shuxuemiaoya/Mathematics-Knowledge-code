---
name: book-to-wiki-graph
description: Convert a book PDF or source Markdown into a TOC-centered Wiki graph with an open-depth organizer layer, source-complete link-free atoms classified as knowledge, worked examples, exercises, or scenarios, deterministic validation, and organization-first Obsidian Canvas files. Use for new conversions, corpus audits, resumes, or Canvas rebuilds across subjects; do not use for document summaries or prose-only exports.
---

# Book to Wiki Graph

Build a source-faithful book graph without assuming a subject, publisher,
edition, chapter count, or fixed organizer depth.

## Read

- Read [references/architecture.md](references/architecture.md) before
  atomization or corpus repair.
- Read [references/manifests.md](references/manifests.md) when creating or
  editing `book-profile.json` or `book-graph.json`.
- Read [references/pdf-conversion.md](references/pdf-conversion.md) for PDF
  input.
- Read [references/canvas.md](references/canvas.md) before Canvas work.

## Pipeline

1. Freeze the source identity with `scripts/init_book.py`. Treat the original
   PDF or Markdown as immutable.
2. For PDF input, convert the complete book to Markdown with an OCR-capable
   converter. Preserve page order, tables, formulas, images, captions, and the
   converter's asset links. Do not atomize directly from PDF page text.
3. Extract the printed table of contents from the converted book. Use it as
   the initial organizer hierarchy, then add source-supported intermediate
   organizers only when they clarify ownership. Organizer depth is open.
4. Review the complete book and partition its teaching content into source-
   complete atoms. Every atom has exactly one category: `knowledge`,
   `worked-example`, `exercise`, or `scenario`.
5. Render organizer notes under `组织层/` and atom notes under the matching
   category in `原子层/`. Organizers contain only their heading and ordered
   embedded links to direct children. Atoms contain no outgoing note links.
6. Record the result in `book-graph.json`, including exact source ranges,
   exclusions, source order, ownership, and optional source-evidenced semantic
   relations.
7. Run `scripts/validate_book_graph.py`. Repair the manifest or staged corpus
   until it reports `status: passed`.
8. Build the Canvas bundle with `scripts/build_canvas.py`; then validate its
   `canvas-index.json`. Keep organization and semantic relations in separate
   Canvas files. Do not hand-author book-specific layout code.

## Invariants

- The only node layers are `organizer` and `atom`.
- The only atom categories are knowledge, worked example, exercise, and
  scenario introduction. Classification changes storage, not source content.
- An organizer may own organizers, atoms, or both. An organizer with no
  organizer children owns atoms only. Do not impose a maximum depth.
- Every atom is the smallest reusable unit for this corpus: it has one owner,
  no children, and no Markdown/Wiki/HTML note links. Local asset embeds are
  allowed because they are part of the source atom.
- Organizer links reproduce direct-child order. They are graph ownership, not
  summaries or duplicated teaching content.
- Every nonblank source line is covered once by an atom, an organizer heading,
  or a reviewed exclusion. Atom ranges never overlap.
- Organization Canvas files reproduce the TOC tree left to right and source
  order top to bottom. They never regroup atoms by category or contain semantic
  relation edges.
- Canvas links and semantic edges live outside atom bodies. Relations require
  source evidence in `book-graph.json` and appear only in `semantics.canvas`.
- Work in task-scoped staging. Never replace an existing corpus or Canvas
  without explicit authorization.

## Commands

```bash
python scripts/init_book.py <source> <staging_root> <book_root> \
  --output <staging_root>/book-profile.json

python scripts/validate_book_graph.py \
  <staging_root>/book-graph.json --book-root <book_root>

python scripts/build_canvas.py \
  <staging_root>/book-graph.json \
  --book-root <book_root> \
  --output-dir <book_root>/Canvas

python scripts/validate_book_graph.py \
  <staging_root>/book-graph.json \
  --book-root <book_root> \
  --canvas-index <book_root>/Canvas/canvas-index.json
```

Completion requires a passed graph validation, a resolving Canvas bundle when
enabled, unchanged source digests, and explicit counts for organizers, atoms,
categories, coverage, relations, and every Canvas role.
