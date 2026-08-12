# Hierarchy Manifest

For a printed TOC, the reviewed adapter supplies `hierarchy.primary_authority`
with its reviewed source range and a complete ordered ledger of stable keys,
source-exact titles, levels, and TOC source lines. The executable
`hierarchy.entries` supplies output paths and body anchors. The planner blocks
missing, extra, reordered, retitled, or relevelled primary entries. Additional
front/back matter must be marked `supplemental: true`.

When OCR flattens several printed columns into one row, inventory records every
leader-delimited entry with its one-based raw column. Review both source-stream
and column-major proposals; a continuous printed ordinal ledger is strong
evidence for column-major order, but is not approval by itself.

When the source truly has no usable printed TOC or index, the adapter must
carry a reviewed `hierarchy.no_toc_authority` decision with a concrete reason.
Do not treat a missing `primary_authority` field as evidence that no TOC exists.

Use a `source-heading` body anchor when the exact title exists in the body. If
OCR omitted the title, use `reviewed-boundary`, record concrete evidence, set
`reviewer_confirmed: true`, and normally set `emit_title: true`. A
`structural_only` parent may share a start line with its first child; this is
required for TOCs that list a section parent and a subsection on the same
printed page. Repeated functional labels remain content children, not a
replacement hierarchy.

The applier writes every entry note, replaces each direct child range with one
standalone vault-relative `![[path/to/note.md]]` embed at that position, and
places content outside top-level entries in the root note. Generated embeds
have no list prefix, and each note embeds only its direct children so Obsidian
does not render descendants twice. `hierarchy-coverage-manifest.json` records
one owner for every raw Markdown line, a local-to-original `source_line_map`
for each immutable hierarchy snapshot, and a digest for every generated note.

Reject duplicate keys, unsafe outputs, incomplete authority coverage, order
changes, invalid levels or anchors, source drift, or non-passed review state.
