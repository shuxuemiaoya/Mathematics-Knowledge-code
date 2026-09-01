# Organization-first Canvas Contract

The Canvas bundle visualizes the reviewed ownership in `book-graph.json`.
Its primary job is to make the book's original outline, direct ownership, and
reading order visible after atomization. It never parses atom bodies to invent
structure or relations.

## Outputs

`scripts/build_canvas.py` writes one bundle below the requested output
directory:

- `overview.canvas`: the complete organizer tree and no atoms;
- `chapters/NN-<title>-<stable-id>.canvas`: one detail Canvas for every
  organizer directly owned by the book root;
- `semantics.canvas`: only when the manifest contains reviewed relations;
- `canvas-index.json`: source binding, paths, roles, layout policy, and counts
  for the complete bundle.

The chapter filename is sanitized, source-ordered, and disambiguated with a
stable key-derived suffix. Do not derive behavior from a literal chapter name.

## Organization grammar

- Hierarchy always expands left to right.
- Direct siblings always appear top to bottom in `children` order. The graph
  validator independently checks that order against source positions.
- Neutral, unlabeled edges express direct ownership only.
- The overview contains every organizer exactly once. Its top-level organizer
  cards open their chapter Canvas; all other cards open organizer Markdown.
- A chapter Canvas contains its root organizer and every descendant organizer
  and atom exactly once. Every card opens its Markdown note.
- Overview background groups bound each top-level organizer subtree. Chapter
  background groups bound each direct child-organizer subtree. Deeper
  hierarchy remains visible through tree edges rather than recursively nested
  groups.
- Do not wrap rows, change orientation according to size, or regroup atoms by
  category. A long Canvas is preferable to losing the book's reading order.

Atoms are leaf cards and retain mixed source order. Their label and color
identify classification without modifying the atom note:

| Category | Card label | Color |
| --- | --- | --- |
| `knowledge` | `知识点 · <title>` | `2` |
| `worked-example` | `例题 · <title>` | `4` |
| `exercise` | `习题 · <title>` | `6` |
| `scenario` | `情景引入 · <title>` | `5` |

Organizer cards use color `1`.

## Semantic grammar

Organization Canvas files contain no manifest `relations`. When reviewed
relations exist, `semantics.canvas` contains only their endpoint cards and
labeled relation edges. Relation evidence remains in `book-graph.json`; it is
never written into atom Markdown.

## Build and gate

Build only after graph validation passes:

```bash
python scripts/build_canvas.py <staging>/book-graph.json \
  --book-root <book-root> \
  --output-dir <book-root>/Canvas

python scripts/validate_book_graph.py <staging>/book-graph.json \
  --book-root <book-root> \
  --canvas-index <book-root>/Canvas/canvas-index.json
```

The builder rejects direct root-owned atoms because every atom must belong to
one top-level detail Canvas. It preflights all bundle paths and refuses to
replace any generated file unless `--overwrite` is explicit.

Final validation requires exact card, group, edge, link-target, color,
direction, sibling-order, chapter-coverage, atom-coverage, and count parity.
