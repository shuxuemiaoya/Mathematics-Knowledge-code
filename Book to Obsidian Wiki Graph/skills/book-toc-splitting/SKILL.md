---
name: book-toc-splitting
description: Split TOC-formatted book Markdown into categorized Obsidian notes using the TOC as the parent hierarchy and reviewed nested source ranges, while replacing every moved child block with a resolving Markdown link at the same position in its parent. Use immediately after book-toc-formatting; for textbooks enforce knowledge, concept, and exercise categories, while allowing profile-recorded LLM-selected categories for other books.
---

# Book TOC Splitting

Own physical note boundaries, category placement, parent links, and coverage. Do not extract additional formal concepts or standardize callouts and typography.

## Plan

Read `references/split-manifest.md` and create `split-manifest.json`.

- Use every TOC entry exactly once as a parent or leaf note.
- Add nested non-TOC ranges for coherent topics, formal-definition blocks, or standalone exercises when useful.
- Inventory every demoted H4-H6 content heading in `semantic_review.headings`; mark it `split` with a `node_key` or `retain` with a specific reason.
- Always split numbered textbook subsections such as `6.1.1` into `knowledge` and section exercises such as `习题6.1` into `exercise`.
- Keep ranges nested or disjoint; never overlap siblings.
- Preserve source order and complete source blocks.
- Leave introductions, transitions, and ordinary lesson practice in their parent unless intentionally moved.

For textbooks, use only:

- `knowledge` → `知识点`;
- `concept` → `概念`;
- `exercise` → `习题`.

For other books, let the LLM determine useful categories and record them in the profile before splitting.

## Split

```powershell
python .\skills\book-toc-splitting\scripts\split_book_by_toc.py `
  "<staging>\<book>.toc-formatted.md" `
  "<staging>\toc-manifest.json" `
  "<staging>\split-manifest.json" `
  --profile "<staging>\book-profile.json"
```

The splitter must:

- reject a textbook manifest that omits the semantic-review ledger or retains a numbered subsection/section exercise;
- create one note per split node;
- replace each direct child range with a standard Markdown link in its parent at the original source position;
- compute relative or vault-root targets from the profile;
- retain the parent heading, introductions, transitions, and unsplit material;
- copy referenced assets into the category-local location and materialize each output image destination according to `links.asset_mode`;
- for `vault-root` assets, write encoded `/课本/...` destinations after copying;
- write `coverage-manifest.json` in staging;
- refuse an existing output root rather than infer replacement.

The parent-link pattern must match the supplied 人教版 example: a lesson note remains an ordered reading path, while linked child bodies live in categorized files.

## Handoff

Require every TOC key and split range to be assigned, every generated target to exist, every parent link to resolve, and all copied asset paths to resolve. Then invoke `book-graph-concepts`, followed by `book-graph-markdown`.
