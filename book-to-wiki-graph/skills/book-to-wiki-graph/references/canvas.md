# Two-level Knowledge Constellation Contract

The Canvas bundle is a learning map, not a rendered directory tree. The book
outline remains authoritative for ownership, while reviewed atom-to-atom
relations determine visible routes and spatial clustering.

## Two zoom levels

`scripts/build_canvas.py` writes:

- `overview.canvas`, a book atlas containing the book hub and chapter cards
  only;
- `chapters/NN-<title>-<stable-id>.canvas`, one knowledge constellation for
  each chapter when relation review has passed;
- `canvas-index.json` schema v2, which binds the manifest and records roles,
  review status, paths, counts, geometry, and the layout contract.

There is no standalone `semantics.canvas`. Chapter cards in the atlas open the
corresponding chapter Canvas. Atom cards open Markdown. Every chapter Canvas
contains a back link to the atlas.

When `relation_review` is missing or incomplete, build only the atlas. Mark
chapter cards `关系待复核`, link them to chapter Markdown, and emit no unreviewed
semantic edge or broken Canvas link.

## Atlas grammar

- Place the book hub at the center and chapters on source-ordered radial rings.
- Add a neutral gray `书序` route between consecutive chapters. It is
  navigation, not a semantic claim.
- Aggregate reviewed cross-chapter atom relations by source chapter, target
  chapter, and relation tier. Label an aggregate route with its relation types
  and count.
- Do not include sections, deeper organizers, or atoms in the atlas.

## Chapter constellation grammar

- Include every knowledge and scenario atom owned by the chapter exactly once.
- Never include an individual exercise atom card. For each exercise, climb to
  the highest exercise-only organizer and render that organizer Markdown as one
  `练习星群` card. If no exercise-only wrapper exists, use the nearest owning
  organizer. Deduplicate organizer cards and show the represented exercise
  count.
- Include a worked-example atom only when the sealed relation review gives it
  semantic role `bridge`, meaning its solution carries a substantial reusable
  mathematical idea or method. Hide routine examples from Canvas without
  deleting their Markdown.
- Direct chapter sections form source-numbered regions. Direct chapter atoms
  occupy a generated `章引入` region. A deeper organizer is a linkable landmark
  only when its subtree contains a rendered atom or exercise cluster. Give each
  retained landmark exactly one neutral gray `包含` edge to the first nearest
  rendered descendant in source order. This sparse anchoring keeps the map
  legible and must not expand into the complete ownership tree.
- Backbone knowledge and scenario atoms form a deterministic center-outward
  constellation. Supporting examples, exercises, and scenarios orbit the
  closest connected core atom.
- A reviewed cross-chapter edge gets one deduplicated external atom portal at
  the chapter map perimeter. External portals do not count as internal atom
  occurrences.
- Use stable IDs and deterministic placement. Resolve all card collisions.
  For a Canvas with at least 30 cards, keep the total bounds aspect ratio
  between `0.5` and `2.0`.
- When an exercise organizer consolidates relations from multiple knowledge
  atoms, insert one unlinked `综合练习汇合` text node. It is visual grammar, not a
  Markdown node or a new fact. This is the supported use of non-file nodes for
  clarifying convergence and inclusion.
- Every substantive card must have at least one incident edge whenever the
  chapter contains more than one substantive card. This includes internal
  atoms, external portals, organizer landmarks, exercise-organizer cards, and
  virtual convergence nodes; title, legend, and back-navigation cards are
  exempt.

Atom cards retain category identity without modifying atom Markdown:

| Category | Label | Color |
| --- | --- | --- |
| `knowledge` | `知识点 · <title>` | `2` |
| `worked-example` | `例题 · <title>` | `4` |
| `exercise` | `习题 · <title>` | `6` |
| `scenario` | `情景引入 · <title>` | `5` |

Exercise organizer cards use color `6`. Virtual convergence nodes have no
Markdown link and must never appear in `book-graph.json` as corpus nodes.

Prefix backbone participants with `✦`; use `·` for supporting atoms, `§` for
organizer landmarks, and `↗ 外章` for cross-chapter portals. Use the host
application's native colors so the result remains usable in light and dark
themes; do not generate a background image.

## Relation grammar

- Backbone edges are labeled `主线 · <type>`, use color `3`, point along the
  learning flow, and form an acyclic graph.
- Supporting edges use their relation-specific label and color.
- `contrasts` and `analogous` have no arrow at either end. Other relation
  types point from prior/trigger/concept toward dependent knowledge, scenario,
  example, application, or exercise.
- Relation evidence remains in JSON manifests and never enters atom Markdown.

## Four-side port grammar

Every edge declares `fromSide` and `toSide`. The convention follows the dominant
grammar observed in the user reference Canvas (`right → left` for progression
and `bottom → top` for subordinate branches):

| Relation shape | From | To |
| --- | --- | --- |
| `prerequisite`, `develops`, `derives` | `right` | `left` |
| `motivates` | `right` | `top` |
| `illustrates`, `applies`, `practices` | `bottom` | `top` |
| `contrasts`, `analogous` | `bottom` | `top` |
| Exercise aggregation and containment | `bottom` | `top` |
| Landmark sparse containment | `bottom` | `top` |

Right-side routes advance knowledge. Bottom-side routes express examples,
applications, parallel/supporting material, or containment. Top-side entry
means the target is inspired by or subordinated to prior material; left-side
entry means it continues the forward knowledge route.

## Build and validation

```bash
python scripts/build_canvas.py <book-root>/book-graph.json \
  --book-root <book-root> \
  --output-dir <book-root>/Canvas

python scripts/validate_book_graph.py <book-root>/book-graph.json \
  --book-root <book-root> \
  --canvas-index <book-root>/Canvas/canvas-index.json
```

The builder writes atomically and requires `--overwrite` for existing output.
Validation checks exact visible-atom selection, collapsed exercise coverage,
featured-example selection, sparse landmark containment, all substantive-card
connectivity, virtual junctions, port sides, region, relation, target, category,
navigation, counts, bounds, overlap, and chapter coverage.
