# Audit Contract

Run two gates:

1. Pre-canvas audit after notes, concepts, links, callouts, and assets are complete.
2. Final audit after canvas compilation when `canvas.enabled` is true.

Require a machine-readable report with `status`, `errors`, `warnings`, and counts.

## Failure conditions

- source digest changed;
- a coverage unit is missing, duplicated, or blocked;
- an empty Markdown or concept note exists;
- a concept has no resolving inbound definition link;
- a Markdown, image, or canvas link does not resolve;
- a forbidden Wikilink remains;
- a top-level callout is malformed or violates the profile spacing rule;
- a functional textbook block remains unstandardized, including plain observation/thinking/exploration headings or worked-example lines outside callouts;
- canvas JSON is invalid;
- node IDs collide;
- an edge endpoint is absent;
- a node or edge color is outside the profile palette.

Do not treat a script exit code or a successful canvas compilation as completion. Completion requires the appropriate audit report to say `status: passed`.
