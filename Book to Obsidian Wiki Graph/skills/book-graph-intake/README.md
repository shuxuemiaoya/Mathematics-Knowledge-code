---
name: book-graph-intake
description: Inspect a source PDF, Markdown book, or existing book tree; freeze source identity; choose vault, output, and staging paths; and create or validate the per-book profile used by all Book to Obsidian Wiki Graph stages. Use for a new conversion, adapting the workflow to another book or taxonomy, or resuming a run whose source and target identity must be verified.
---

# Book Graph Intake

Own source identity and book-specific configuration. Do not perform semantic splitting or final-note edits.

## Contract

Read `references/book-profile.md`. Produce:

- `source-inventory.json`;
- `book-profile.json`.

Keep these artifacts in the profile's task-scoped staging directory, not in the final book tree.

## Inspect

1. Resolve one source PDF, Markdown file, or explicit existing source tree.
2. Resolve `vault_root`, `book_root`, title, edition, language, and book kind.
3. Inspect the target. Classify it as new, resumable, auditable, or blocked by ambiguous replacement intent.
4. For a PDF, inspect representative page types and the printed TOC.
5. Record a stable source digest and never mutate the source.
6. When Canvas is enabled, inspect immediate sibling book directories for an
   existing same-publisher, same-series `.canvas`. Prefer a user-named Canvas;
   otherwise use the deterministic discovery result. The first completed book
   in a series may establish the baseline when no sibling Canvas exists.

Run the inventory:

```powershell
python scripts\inventory_book.py "<source>" --book-root "<book_root>"
```

Save its stdout as `source-inventory.json`.

Discover a same-series visual reference without reading old conversion staging:

```powershell
python scripts\discover_sibling_canvas_style.py `
  "<books_root>" "<book_root>" `
  --output "<staging_root>\canvas-style-discovery.json"
```

## Create The Profile

```powershell
python scripts\make_book_profile.py create "<source>" `
  --vault-root "/Users/oven/Documents/ovenmathmap" `
  --book-root "/Users/oven/Documents/ovenmathmap\<input_relative_path>\<book_folder>" `
  --title "<title>" `
  --edition "<edition>" `
  --book-kind "<kind>" `
  --staging-root "<staging_root>" `
  --reference-corpus "<approved_reference_book_root>" `
  --reference-scope "style-only|same-book-content-and-style" `
  --canvas-style-reference "<approved_same_series_sibling.canvas>" `
  --output "<staging_root>\book-profile.json"
```

When the user names an approved output corpus as the desired style, freeze it
in the profile with `--reference-corpus`. Use `style-only` for a different
book and `same-book-content-and-style` only for the same title and edition.
Never silently substitute another old run or treat the reference as cached
conversion output.

`--canvas-style-reference` is narrower than `--reference-corpus`: it freezes
only a same-series visual contract under `canvas.style_reference`. It does not
authorize copying sibling content, legacy link syntax, or invalid graph
structure. Omit it only when discovery reports `not_found` and no Canvas has
yet been completed for the series.

For textbooks, always retain `知识点`, `概念`, and `习题`. Inspect the printed
TOC and enable only source-supported side-material roles by repeating
`--textbook-aux-role reading|history|method|tool`; these map to `趣味阅读`,
`数学历史`, `思维或方法`, and `工具`. Do not enable a role merely to reproduce an
empty legacy directory. Keep the generated vault-root note and asset modes
unless the user explicitly chooses another policy. For other books, inspect
the content and let the LLM replace the initial `content` role with useful
semantic categories before validation. Adapt link, formatting, asset, or
canvas policies through the same profile.

For new textbook profiles, keep
`decomposition.require_lesson_flow_manifest: true`. This makes the complete
lesson-flow review a required split-stage artifact and prevents later stages
from substituting keyword-based logical grouping.

```powershell
python scripts\make_book_profile.py validate "<staging_root>\book-profile.json"
```

## Gate

Handoff only when:

- profile validation passes;
- source digest matches the inventory;
- the profile file still resides in its frozen `paths.staging_root` and the
  source/vault paths exist; reject a moved or copied run instead of rebasing it;
- `book_root` is inside `vault_root`;
- replacement intent is unambiguous;
- enabled category roles have unique directories;
- every enabled textbook auxiliary role is evidenced by the source or printed TOC;
- a configured reference path and tree digest still match the approved corpus;
- a configured Canvas style-reference path and file digest still match the
  approved sibling Canvas;
- staging is outside the final book tree.

Return the absolute profile path and source digest. Downstream stages must reject mismatches.
