# Book to Wiki Graph Agent Contract

This plugin is independent from `Book to Obsidian Wiki Graph`. Do not import
its textbook-, mathematics-, publisher-, or edition-specific rules.

## Goal

Convert a complete book into two node layers:

- organizers: an open-depth, TOC-centered ownership hierarchy;
- atoms: source-complete, childless, outgoing-note-link-free knowledge,
  worked-example, exercise, or scenario notes.

The organization-first Canvas bundle is compiled from `book-graph.json`; atom
bodies never need graph links. Its overview and chapter files reproduce the
book hierarchy and source order, while reviewed semantic relations live in a
separate Canvas. Keep all book-specific titles, ranges, categories, and
relations in staging manifests rather than code.

## Required sequence

```text
freeze source -> PDF to Markdown when needed -> extract TOC -> review hierarchy
-> atomize complete source -> render organizers/atoms -> validate
-> organization/semantic Canvas bundle -> validate final corpus and bundle
```

Use task-scoped staging and atomic output. Do not overwrite an existing book
tree, manifest, or Canvas by inference.
