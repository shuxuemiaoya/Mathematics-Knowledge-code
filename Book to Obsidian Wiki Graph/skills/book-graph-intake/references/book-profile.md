# Per-Book Profile Contract

Create one `book-profile.json` in task-scoped staging. It is the only book-specific configuration read by downstream stages.

## Required sections

- `book`: title, edition, language, and broad kind.
- `source`: immutable path, kind, and frozen SHA-256.
- `paths`: vault root, final book root, and staging root.
- `categories`: semantic role to directory mapping.
- `links`: note, canvas, and asset link modes.
- `formatting`: callout policy.
- `decomposition`: source-order and source-completeness invariants.
- `canvas`: enabled flag, semantic palette, and optional frozen same-series
  `style_reference`.
- `workspace`: backup policy.
- optional `reference`: approved corpus path, frozen tree SHA-256, and either
  `style-only` or `same-book-content-and-style` scope.

## Adaptation rules

- For textbooks, always keep `knowledge` → `知识点`, `concept` → `概念`, and
  `exercise` → `习题`.
- Enable a side-material role only when the printed TOC or source contains it:
  `reading` → `趣味阅读`, `history` → `数学历史`, `method` → `思维或方法`, or
  `tool` → `工具`. Enabled roles with no owned notes are a planning defect; do
  not create empty category directories.
- For other books, inspect the book first and replace the generated `content` category with LLM-selected semantic roles and directories when useful.
- Change directory names through `categories`; downstream skills use `role`, not a hard-coded Chinese path.
- Disable an unsupported category with `enabled: false`. Do not create its directory.
- Add a new role only when a downstream stage has a clear ownership rule for it.
- Set `canvas.enabled: false` for books that should produce linked notes without a canvas.
- Use `book.kind` as a routing hint, not as permission to weaken source preservation.
- Default textbook note links and assets to vault-root paths so moved notes keep stable Obsidian targets; other books may use relative note links.
- Default textbook `formatting.callout_body_mode` to `quoted-body`: a callout
  owns a continuous quoted body, and example analysis/solutions use nested
  quoted callouts.
- Default `decomposition.non_toc_split_default` to `retain` and require an
  explicit, high-confidence independent-teaching-arc decision to override it.
- Default `decomposition.require_lesson_flow_manifest` to `true` for new
  textbook profiles. Use
  `max_retained_teaching_block_nonblank_lines` (default `40`) as a review
  boundary, not as permission to summarize or discard longer content.
- Keep source identity and output paths immutable after intake. Validation must
  reject a profile copied or moved outside `paths.staging_root`; create a new
  profile if source, vault, output, or staging identity changes.
- Freeze a user-named style corpus at intake. Use it as presentation and
  decomposition evidence, never as reusable conversion output. Reject a run
  when that reference tree changes after profile creation.
- Freeze a same-series Canvas style reference as
  `canvas.style_reference: {path, sha256, scope: "same-series-style"}`. Its
  path must name one existing `.canvas` file and its digest must remain stable.
  This visual contract is independent of the optional corpus-level
  `reference`; it controls layout grammar, not sibling content reuse.

## Handoff invariant

Every downstream manifest must include:

```json
{
  "schema_version": 1,
  "profile": "<absolute path to book-profile.json>",
  "source_sha256": "<same digest as the profile>"
}
```

Reject a handoff when the profile is missing, invalid, or carries a different source digest.
