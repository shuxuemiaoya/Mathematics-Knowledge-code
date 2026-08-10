---
name: book-graph-canvas
description: Plan a reviewable semantic graph manifest and compile it into a validated Obsidian canvas using a book profile's enabled roles, link policy, node/edge palette, and frozen same-series visual reference. Use only after the note corpus passes its pre-canvas audit, when a book needs a mathematical or domain-logic map rather than a table-of-contents diagram.
---

# Book Graph Canvas

Own `graph-manifest.json` and `.canvas` compilation. Do not edit source notes or bypass the pre-canvas audit.

## Inputs

Require:

- valid profile and matching source digest;
- `canvas.enabled: true`;
- pre-canvas audit with `status: passed`;
- complete note, coverage, and concept manifests.
- the live path and SHA-256 of `canvas.style_reference` when the profile
  declares one.

Read `references/canvas-manifest.md`.

## Plan

When the profile declares a reviewed same-book reference with scope
`same-book-content-and-style` and that reference contains a `.canvas`, start
from the reference layout instead of inventing a chapter grid:

```powershell
python scripts\plan_from_reference_canvas.py `
  "<reference_book_root>\<reference>.canvas" `
  "<staging>\book-profile.json" `
  "<staging>\graph-manifest.json"
```

If the user supplies a same-book canvas comparison target, bind its containing
corpus into the profile before planning; do not ignore it merely because an
older profile omitted `reference`. The planner converts resolving Wikilinks to
standard Markdown links and writes an identity-bound `reference_review`.

The initial plan is always `review_required`. Review every skipped reference
node and edge. A skipped item may be accepted
only when it is external to the current book, absent from the current corpus,
or intentionally represented by a documented current equivalent. Add
current-only source-supported nodes without flattening the inherited domain
and topic groups.

Record the decisions in JSON and approve them deterministically:

```powershell
python scripts\finalize_reference_canvas_review.py `
  "<staging>\graph-manifest.json" `
  "<staging>\canvas-reference-decisions.json" `
  --reviewer-confirmed
```

The compiler rejects an unapproved review, changed reference digest, missing
retained node/edge, or flattened retained group-containment relationship.

1. Create groups for coherent chapters, domains, or topic clusters.
2. Create text cards for selected notes, concepts, exercises, methods, readings, tools, or source-supported annotations.
3. Use stable semantic keys.
4. Use unlabeled edges for containment and local progression.
5. Add labels or semantic colors only for source-supported relations.
6. Build canvas links from the profile's canvas link mode.
7. Keep the manifest in staging for review.

For a same-book reference canvas, the reviewed manifest must preserve its
domain/topic grouping and meaningful topology unless a source-backed
deviation is recorded. A chapter-only grid is not an acceptable replacement.
Do not create a per-book graph builder with literal chapter names, source-order
number ranges, fixed concept names, or a hand-authored relation list. Express
book-specific semantics only in the reviewed staging manifest; keep agent code
and validators corpus-independent.

When `canvas.style_reference` is configured, treat it as the visual grammar for
group density and nesting, overall aspect, card-size rhythm, annotation-card
use, and edge label/color use. Reproduce those proportions within the
comparator tolerances while deriving every title, note, and relation from the
current book. Canonical Markdown links and graph validity override legacy
Wikilinks, plain dead cards, or invalid topology in the reference.

## Compile

```powershell
python scripts\build_canvas.py `
  "<staging>\graph-manifest.json" `
  "<book_root>\<book>.canvas" `
  --vault-root "<vault_root>" `
  --profile "<staging>\book-profile.json"
```

The compiler must reject invalid fields, keys, colors, endpoints, links, or an existing output unless explicit overwrite is authorized.

Then compare the compiled Canvas with the frozen same-series reference:

```powershell
python scripts\compare_canvas_style.py `
  "<staging>\book-profile.json" `
  "<book_root>\<book>.canvas" `
  --output "<staging>\canvas-style-report.json"
```

If the report is `style_review_required`, revise the semantic manifest and
layout, rebuild, and rerun the comparison. Do not complete the Canvas stage by
waiving or relabeling a blocking visual difference.

## Handoff

Return manifest, Canvas, and style-report paths plus node, group, edge, color,
unresolved-link, and style metrics. A configured style reference requires
`canvas-style-report.status: passed`; completion still requires the final audit.
