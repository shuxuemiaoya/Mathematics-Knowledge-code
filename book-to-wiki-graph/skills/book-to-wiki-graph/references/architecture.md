# Organizer and Atom Architecture

## Two node layers

Every Markdown note is exactly one of:

- `organizer`: owns an ordered list of direct children;
- `atom`: owns nothing and contains one smallest source-complete unit.

Book, part, chapter, section, topic, appendix, and similar terms are organizer
roles, not additional layers. Definition, theorem, proof, example, problem,
activity, case study, and narrative describe atom content, not extra layers.

## Open-depth organizer hierarchy

Start with the printed TOC. Preserve its hierarchy, direct ownership, and
reading order. Add an intermediate organizer only when the source or an
explicit human review supports that ownership boundary.

Do not impose a fixed number of levels or a subject-specific wrapper scheme.
An organizer may own organizers, atoms, or both. Mixed children remain in the
order in which their earliest source content appears. In the common case, only
the deepest organizer owns atoms; this is a tendency, not a validity rule.

A nonterminal organizer note does not repeat its own filename/title in the body.
It then has one
embedded Markdown note link per direct child. Every organizer-child embed is
preceded by the child's global-depth heading: `#` for the book root, `##` for a
chapter, `###` for the next level, and so on (capped at Markdown `H6`). Atom
embeds receive no added heading. A terminal organizer that links directly to
atoms therefore contains no heading at all. Organizer notes contain no teaching
prose, summaries, duplicated atom bodies, or links to non-direct descendants.

Keep a directory only for an organizer that owns another organizer. Materialize
an organizer with only atom children as one clearly named Markdown file directly in
its parent's directory; never create a subdirectory whose only local file is
that organizer note.

### Structural headings versus activity labels

A Markdown heading is not automatically an organizer. Printed TOC entries and
source-supported reusable knowledge topics are organizational. Pedagogical
labels such as observe, think, try, discuss, communicate, operate, or explore
normally introduce one atomic activity and belong inside that atom's source
range. The marker text itself is preserved as a plain source line and the LLM
must record whether it is a scenario, exercise, or explicitly merged scaffold.
An inline practice heading may remain as source presentation metadata,
but its questions belong to the preceding or explicitly targeted knowledge
topic. A terminal formal exercise-set/group heading may remain a direct section
organizer when it owns multiple questions.

Within a TOC section, place a section-wide introduction first, reviewed
knowledge-topic organizers next, and the terminal exercise set last. A short
prior-knowledge question is a standalone `section-introduction` when several
sibling topics collectively answer it; a prompt serving only one immediate
explanation stays inside that knowledge atom. Name a synthesized topic for the
subject it teaches, never for the activity label used to teach it. Keep
adjacent formally defined concepts separate when their dependency roles and
reuse boundaries differ, even if one printed heading visually groups them.

## Atomic units

An atom preserves a complete source-backed teaching unit. For exposition, the
default unit is the local teaching arc: motivation or short prompt, definition,
conditions, notation, explanation, derivation, and nearby conclusion. Do not
split that arc because a converter inserted a blank line, image, formula,
activity label, or box boundary. Split only when both sides can be named,
understood, and reused independently.

A short “observe”, “think”, or “try” prompt may be merged with the knowledge it
elicits only with an explicit disposition and preserved marker; a complete
unanswered post-knowledge question is a reflection scenario. A standalone
scenario must be a complete narrative, real-world context, experiment setup,
or learning motivation. Keep an example stem with
its analysis, solution, and nearby conclusion. Keep a top-level exercise with
all subparts, figures, tables, and supplied material.

A short bridge may remain `scenario_role: knowledge-motivation` when it
explicitly points backward to learned material, opens a distinct next topic,
and can support the reviewed chain `learned knowledge → bridge → new knowledge`.
Otherwise it is ordinary instructional scaffolding and merges into the
knowledge it elicits.

Scope precedes paragraph shape when classifying introductions. Use
`book-introduction` for a preface/reader guide, `chapter-introduction` for a
chapter opening, `section-introduction` for a passage framing multiple child
topics, and `knowledge-motivation` for a complete problem/context aimed at one
topic. A book/chapter/section introduction is one complete atom per owner and
role, including its contiguous prose, questions, figures and captions. Reject
continuation and media-only fragments. A knowledge motivation likewise keeps
its whole setup and final question together.

A complete question asked after teaching—especially one requiring comparison,
synthesis, extension, or open inquiry—remains independent with
`scenario_role: reflection-question`. It is stored under `原子层/思考题` but
participates in the graph as a scenario that learned knowledge can motivate.

Assign exactly one category:

| Manifest category | Directory | Complete unit | Canvas color |
| --- | --- | --- | --- |
| `knowledge` | `原子层/知识点/` | exposition, definition, proposition, proof, method, explanation | `2` |
| `worked-example` | `原子层/例题/` | solved example with stem and solution | `4` |
| `exercise` | `原子层/习题/` | unsolved problem with all subparts/material | `6` |
| `scenario` | `原子层/情景引入/` | substantial context, narrative, experiment, or motivation | `5` |

The scenario subrole `reflection-question` uses `原子层/思考题/NNNN-T.md`.

Atoms have no children and no outgoing note links. Reject Wikilinks, ordinary
Markdown note links, embedded note links, and HTML anchors in atom bodies.
Local source image/media embeds are allowed. Render atom bodies without
Markdown heading lines. Store primary atoms and formulas under opaque
sequence-and-category codes:
`K` knowledge, `W` worked example, `E` exercise, `S` scenario, and `T` thought
question (for example, `0001-K.md` or `0013-T.md`). Definition-only concept
cards are the filename exception: use the canonical concept name, adding a
stable short suffix only for collisions. Human-readable primary-atom titles
remain manifest metadata and link labels, not filenames or headings inside
atom notes.

Every organization note carries YAML properties independent of its visible
heading policy. The properties identify the organizer, immediate parent,
source book and digest, global depth, full hierarchy path, source heading
ranges/anchor, structural role, direct child composition, descendant atom
count, update date, and review state. The root uses explicit null parent
fields. Generated concept/formula indexes under `组织层/` use the same property
shape so no organizational note becomes provenance-blind.

## Hard constraints and audit thresholds

Organizer ownership, reviewed exclusions, explicit worked-example starts, and
top-level exercise starts are hard constraints. Empty lines, images, formulas,
and boxed conclusions are soft boundary evidence. Activity labels are source
content and require an explicit disposition.

Knowledge under 150 normalized characters or containing one nonblank line is
always audited. It remains independent only when it is a formal definition,
theorem, or law, has a concrete independence reason, and meets the configured
short-atom confidence threshold (default `0.95`). General decisions must meet
the configured confidence threshold (default `0.90`).

## Coverage and order

Each atom records an inclusive one-based `source_range`. Each organizer records
the source heading lines it owns. Printed TOC pages, running headers, page
numbers, and conversion artifacts are explicit reviewed exclusions.

Combining atom ranges, organizer heading ranges, and exclusions must cover
every nonblank source line exactly once. Primary atom ranges never overlap, and
`source_order` equals primary atoms sorted by source position. Classification affects
storage and Canvas color only; it never changes reading order.

Sibling organizer subtrees also obey interval order: each child's latest
source position must precede the next child's earliest position. A non-exercise
printed organizer with only exercise descendants is invalid. Category-aware
runs cannot proceed without a passed digest-bound organizer review. An existing
printed organizer may own reviewed runs immediately before and after its own
heading; no individual run crosses that heading.

## Teaching relations and learning maps

Freeze stable virtual atom identities before materializing Markdown. Then
perform a three-pass dual-layer relation review: first extract canonical concepts
and atom roles, second disambiguate concepts and judge hybrid candidates, and
third audit the complete graph using WCC, DAG, direction, redundancy, evidence,
and isolation checks. Read
[relations.md](relations.md) before producing either pass.

Relations never change organizer ownership or atom prose. Explicit source
connections and pedagogical inferences remain distinguishable. Every inferred
edge cites both endpoint ranges and uses the higher confidence threshold.

Canvas uses three semantic scales. The book atlas contains only chapters and
aggregated cross-chapter routes. A chapter core Canvas contains knowledge and
scenario atoms plus only the worked examples reviewed as major-method `bridge`
examples; exercises appear only as counts on section portals. Each section
portal opens a detail Canvas where exercise atoms collapse into organizer-note
entries with one primary practice edge apiece. Reviewed relations and spatial
regions express the learning map without redrawing the directory tree or
duplicating organizer/atom labels. Direct sections are large Canvas groups and
deeper organizers with visible cards are nested group envelopes. Knowledge cards
use deterministic compact clusters, with a local left-to-right learning flow
only where reviewed edges require it and a two-dimensional grid for unrelated
regions;
right-side targets never move left and bottom-side targets never move above
their source. Canonical concepts and derived formula cards
remain in JSON and Markdown indexes rather than Canvas. Explicit edge
sides distinguish forward development (`right` to `left`), inspiration
(`right` to `top`), and subordinate/parallel branches (`bottom` to `top`).
Spatial containment communicates ownership. A labelled `归属` edge may connect
an audited independent node to its organizer portal; source order never asserts
dependency.
Do not redraw the complete hierarchy as a left-to-right tree. Read
[canvas.md](canvas.md) before building or repairing Canvas output.

## v0.7 relation closure before materialization

The default path now freezes category-aware ranges and their local semantic
signatures first, runs the three relation passes against stable virtual atom
keys, and materializes only after both reviews pass. The graph audit may send
`merge`, `split`, or `resegment` feedback to atomization at most twice. Any
boundary change invalidates the affected relation digest.

In category-aware mode, knowledge boundaries are LLM-exclusive: source
paragraph shape and provisional draft spans cannot choose atom count. The model
must keep parallel formal definitions separate even when a subsection title
combines them and no transition word connects them.

Primary atoms alone cover source and appear in `source_order`. Derived concept
and formula cards duplicate a minimal continuous excerpt within a primary
knowledge atom (or a reviewed bridge example for formulas), appear in
`derived_order`, and never count toward coverage. Canvas hides both derived
cards and canonical concept nodes; an explicit `归属` edge replaces legacy
source-order fallback for a reviewed independent visible node.
