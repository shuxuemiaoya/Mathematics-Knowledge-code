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
- `canvas`: enabled flag and semantic palette.
- `workspace`: backup policy.

## Adaptation rules

- For textbooks, keep exactly `knowledge` → `知识点`, `concept` → `概念`, and `exercise` → `习题`.
- For other books, inspect the book first and replace the generated `content` category with LLM-selected semantic roles and directories when useful.
- Change directory names through `categories`; downstream skills use `role`, not a hard-coded Chinese path.
- Disable an unsupported category with `enabled: false`. Do not create its directory.
- Add a new role only when a downstream stage has a clear ownership rule for it.
- Set `canvas.enabled: false` for books that should produce linked notes without a canvas.
- Use `book.kind` as a routing hint, not as permission to weaken source preservation.
- Default textbook note links and assets to vault-root paths so moved notes keep stable Obsidian targets; other books may use relative note links.
- Keep source identity and output paths immutable after intake. Create a new profile if either changes.

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
