---
name: book-graph-canvas
description: Plan a reviewable semantic graph manifest and compile it into a validated Obsidian canvas using a book profile's enabled roles, link policy, and node/edge palette. Use only after the note corpus passes its pre-canvas audit, when a book needs a mathematical or domain-logic map rather than a table-of-contents diagram.
---

# Book Graph Canvas

Own `graph-manifest.json` and `.canvas` compilation. Do not edit source notes or bypass the pre-canvas audit.

## Inputs

Require:

- valid profile and matching source digest;
- `canvas.enabled: true`;
- pre-canvas audit with `status: passed`;
- complete note, coverage, and concept manifests.

Read `references/canvas-manifest.md`.

## Plan

1. Create groups for coherent chapters, domains, or topic clusters.
2. Create text cards for selected notes, concepts, exercises, methods, readings, tools, or source-supported annotations.
3. Use stable semantic keys.
4. Use unlabeled edges for containment and local progression.
5. Add labels or semantic colors only for source-supported relations.
6. Build canvas links from the profile's canvas link mode.
7. Keep the manifest in staging for review.

## Compile

```powershell
python scripts\build_canvas.py `
  "<staging>\graph-manifest.json" `
  "<book_root>\<book>.canvas" `
  --vault-root "<vault_root>" `
  --profile "<staging>\book-profile.json"
```

The compiler must reject invalid fields, keys, colors, endpoints, links, or an existing output unless explicit overwrite is authorized.

## Handoff

Return manifest and canvas paths plus node, group, edge, color, and unresolved-link counts. Completion still requires the final audit.
