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

Run the inventory:

```powershell
python scripts\inventory_book.py "<source>" --book-root "<book_root>"
```

Save its stdout as `source-inventory.json`.

## Create The Profile

```powershell
python scripts\make_book_profile.py create "<source>" `
  --vault-root "<vault_root>" `
  --book-root "<book_root>" `
  --title "<title>" `
  --edition "<edition>" `
  --book-kind "<kind>" `
  --staging-root "<staging_root>" `
  --output "<staging_root>\book-profile.json"
```

For textbooks, retain exactly `知识点`, `概念`, and `习题`; keep the generated vault-root note and asset modes unless the user explicitly chooses another policy. For other books, inspect the content and let the LLM replace the initial `content` role with useful semantic categories before validation. Adapt link, formatting, asset, or canvas policies through the same profile.

```powershell
python scripts\make_book_profile.py validate "<staging_root>\book-profile.json"
```

## Gate

Handoff only when:

- profile validation passes;
- source digest matches the inventory;
- `book_root` is inside `vault_root`;
- replacement intent is unambiguous;
- enabled category roles have unique directories;
- staging is outside the final book tree.

Return the absolute profile path and source digest. Downstream stages must reject mismatches.
