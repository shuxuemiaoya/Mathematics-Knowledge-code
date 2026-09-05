# Three-level Knowledge Constellation Contract

The Canvas bundle is a learning map, not a rendered directory tree. The book
outline remains authoritative for ownership, while reviewed canonical concepts,
atom-concept roles, and their atom projection determine visible routes and
spatial clustering.

## Three zoom levels

`scripts/build_canvas.py` writes:

- `overview.canvas`, a book atlas containing the book hub and chapter cards
  only;
- `chapters/NN-<title>-<stable-id>.canvas`, one low-noise core constellation
  per chapter when relation review has passed;
- `sections/NN-NN-<title>-<stable-id>.canvas`, one detail map per direct
  section, including the generated chapter-introduction section when present;
- `canvas-index.json` schema v3, which binds the manifest and records all three
  roles, review status, paths, counts, geometry, visual-quality metrics, and the
  layout contract.

There is no standalone `semantics.canvas`. Chapter cards open chapter core
maps; section portals open detail maps; atom and exercise-entry cards open
Markdown. Each lower level contains a link back to its parent map.

When `relation_review` is missing or incomplete, build only the atlas. Mark
chapter cards `关系待复核`, link them to chapter Markdown, and emit no unreviewed
semantic edge or broken Canvas link at either lower level.

## Atlas grammar

- Place the book hub at the center and chapters on source-ordered radial rings.
- Add a neutral gray `书序` route between consecutive chapters. It is
  navigation, not a semantic claim.
- Aggregate reviewed cross-chapter atom relations by source chapter, target
  chapter, and relation tier. Label an aggregate route with its relation types
  and count.
- Do not include sections, deeper organizers, or atoms in the atlas.

## Chapter core grammar

- Include every knowledge and scenario atom owned by the chapter exactly once.
- Never include an individual exercise atom, exercise organizer card, or
  `practices` edge. Show only an exercise count on each section portal.
- Include a worked-example atom only when the sealed relation review gives it
  semantic role `bridge`, meaning its solution carries a substantial reusable
  mathematical idea or method. Hide routine examples from Canvas without
  deleting their Markdown.
- Direct chapter sections form source-numbered regions. Direct chapter atoms
  occupy a generated `章引入` region. Each region has exactly one click-through
  portal showing its visible-atom and exercise counts. Do not add deeper
  organizer landmarks: spatial regions and portals already encode ownership.
- Backbone knowledge and scenario atoms form a deterministic center-outward
  constellation. Supporting examples, exercises, and scenarios orbit the
  closest connected core atom.
- Reviewed cross-chapter routes aggregate at atlas level; a future external
  atom portal may be added only if it is deduplicated and validated.
- Render a canonical concept as an unlinked `✦ 规范概念` hub only when it
  connects at least two visible display nodes, has concept-relation degree at
  least three, crosses direct-section regions, or participates in an approved
  cross-chapter relation. Otherwise project the relation through the earliest
  `introduces` knowledge atom, falling back deterministically to the earliest
  visible grounded atom. Do not draw both the hub relation and its grounded
  atom projection.
- Use stable IDs and deterministic placement. Resolve all card collisions.
  For a Canvas with at least 30 cards, keep the total bounds aspect ratio
  between `0.5` and `2.0`.
- Every substantive card must have at least one incident edge whenever the
  chapter contains more than one substantive card. This includes internal
  atoms, section portals, external portals, and concept hubs; title, legend,
  and back-navigation cards are exempt. When an otherwise sound atom has no
  reviewed edge, add one gray, labelled `书序` navigation edge to its nearest
  visible source neighbour rather than inventing a semantic relation.

## Section detail grammar

- Repeat every knowledge/scenario atom and reviewed `bridge` example in that
  section exactly once. This repetition is intentional level-of-detail, not a
  duplicate within one map.
- Never render an individual exercise atom. Climb to the highest exercise-only
  organizer, deduplicate it, link its Markdown note, and show the represented
  exercise count.
- Give each exercise organizer at most one primary `练习 · N题` edge. Choose
  the anchor by reviewed relation support, then source proximity. Place the
  entry in the same local star region as its anchor so practice lines do not
  span the whole map.
- Use source-supported knowledge subtopics as regions. When a section contains
  exercises but no visible teaching atom, use one `练习与习题` region linked
  radially from the map hub.
- Do not recreate one-to-one organizer, atom, and concept cards with the same
  label. Organization is a region, the source note is the atom card, and a
  one-to-one concept is folded into that card.

Atom cards retain category identity without modifying atom Markdown:

| Category | Label | Color |
| --- | --- | --- |
| `knowledge` | `知识点 · <title>` | `2` |
| `worked-example` | `例题 · <title>` | `4` |
| `exercise` | `习题 · <title>` | `6` |
| `scenario` | `情景引入 · <title>` | `5` |

Exercise organizer cards use color `6`. Virtual concept hubs have no Markdown
link and must never appear in `book-graph.json` as corpus nodes.

Prefix backbone participants with `✦`; use `·` for supporting atoms and
`↗ 外章` for cross-chapter portals. Use the host
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
| Concept prerequisite/development/derivation | `right` | `left` |
| Concept hierarchy, contrast, and analogy | `bottom` | `top` |

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
Validation checks atlas/chapter/section coverage, exact visible-atom selection,
absence of exercises and practice edges at chapter scale, collapsed exercise
coverage and one-primary-edge limits at section scale, featured-example
selection, strict concept-hub rules, all substantive-card connectivity, port
sides, targets, colors, navigation, counts, bounds, overlap, and recorded
visual-quality metrics.
