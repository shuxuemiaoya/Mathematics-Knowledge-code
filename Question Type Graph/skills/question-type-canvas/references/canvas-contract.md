# Structural Canvas Contract

Build groups or cards for hierarchy entries and cards for reviewed functional
nodes. Exclude every atomic question. Use deterministic IDs derived from
semantic keys and relative Markdown links resolving inside the configured
vault root.

Use color `6` for `question-type` and `subtype` roles by default. Other roles
remain neutral unless the profile supplies an allowed palette. Emit only
containment and source-order edges in this phase; do not create knowledge-point
nodes, semantic relations, or placeholder backlinks.

Reject duplicate IDs, unsupported node shapes, invalid endpoints, unresolved
links, atomic question cards, or existing output without explicit overwrite.
