# Book to Wiki Graph Agent Contract

This plugin is independent from `Book to Obsidian Wiki Graph`. Do not import
textbook-, subject-, publisher-, or edition-specific hierarchy rules.

## Goal

Convert any complete book into exactly two Markdown node layers:

- organizers: an open-depth, TOC-centered ownership hierarchy whose notes
  contain only ordered direct-child embeds and do not repeat their own title.
  Each organizer-child embed is preceded by its root-relative heading (`#`,
  then `##`, then `###`, capped at `H6`). A terminal organizer linking atoms
  has no heading. Such leaves are flat numbered notes in the parent directory
  rather than one-file folders;
- atoms: source-complete, childless, outgoing-note-link-free knowledge,
  worked-example, exercise, or substantial-scenario notes. Atom bodies have no
  Markdown headings and use opaque sequence-plus-category filenames such as
  `0001-K.md`.

An organizer may own organizer children, atom children, or both. Preserve the
mixed `children` source order. Usually only the deepest organizers own atoms,
but never invent wrapper organizers merely to force that shape.

## Required sequence

```text
freeze source -> PDF to Markdown when needed -> review TOC and ownership
-> demote pedagogical activity labels and create reviewed knowledge topics
-> prepare range-only atomization jobs -> Agent/model round-one partition
-> validate round one -> prepare every-adjacency audit
-> Agent/model round-two keep/merge/resegment review -> finalize
-> require zero unresolved review items -> audit atom teaching roles and titles
-> require zero unresolved role items -> materialize source ranges while
   omitting atom Markdown heading lines
-> validate corpus -> invoke knowledge-relation-mapper
-> canonical concept extraction -> hybrid relation decisions -> full graph audit
-> require zero unresolved relation items for semantic maps
-> apply relations -> build three-level knowledge constellation bundle
-> validate complete Canvas bundle
```

MinerU is the default PDF converter. Other PDF tools may supplement it for
diagnosis or repair, but source identity, page order, formulas, tables, images,
and resource links must remain auditable.

Printed or OCR headings such as “observe”, “think”, “try”, “discuss”, and
“explore” describe an activity inside an atom; they are not organizers merely
because they were rendered as Markdown headings. Under a TOC section, create
source-supported knowledge-topic organizers for reusable subject units, while
practice and exercise-set headings may remain structural organizers. Apply a
digest-bound organizer review before atomization so demoted headings become
part of the following atom's exact source range.

## Atomization rules

- A knowledge atom is a complete teaching unit. Keep its definition,
  conditions, notation, explanation, derivation, and nearby conclusion
  together. Blank lines, images, formulas, boxes, and ordinary activity labels
  are soft boundaries only.
- A short observation, question, or thinking prompt stays with the knowledge it
  elicits. Only a complete narrative, real-world context, experiment setup, or
  learning motivation may be a `scenario` atom.
- A worked example includes its complete stem, analysis, solution, and nearby
  conclusion. An exercise includes the top-level problem, every subpart,
  figure, table, and supplied material.
- Organizer ownership, exclusions, explicit example starts, and top-level
  exercise starts are hard boundaries.
- A knowledge atom shorter than 150 normalized characters or containing only
  one nonblank line requires second-pass review. It may remain alone only as a
  formal definition, theorem, or law with a concrete independence reason and
  confidence of at least 0.95.

Model decisions contain continuous source ranges and review metadata only.
They never rewrite source prose. Low confidence, stale digests, pass conflicts,
or hard-boundary violations block materialization.

## Relation and Canvas contract

Review relations only after atoms have stable materialized keys. Invoke the
plugin's `knowledge-relation-mapper` Skill: pass one extracts source-grounded
canonical concepts and atom roles, pass two disambiguates concepts and judges
hybrid candidates, and pass three audits the complete graph using WCC and DAG
checks. Explicit relations require confidence `0.90`; pedagogical inferences
require `0.95` and evidence from both endpoints. Concept merges require `0.97`.
Backbone relations are acyclic. JSON is authoritative; Neo4j is optional and
read-only with respect to the manifest.

`overview.canvas` contains the book hub and chapters only, with source-order
navigation plus reviewed cross-chapter aggregation. Each chapter opens a
low-noise core constellation containing knowledge/scenario atoms, selective
canonical-concept hubs, and only major-method examples reviewed as `bridge`;
it contains no exercise cards or practice edges. Its direct sections are
click-through star regions. Each section opens a detail Canvas where exercise
atoms are collapsed into exercise-organizer Markdown entries with at most one
primary practice edge. One-to-one concept hubs and duplicate organizer
landmarks are folded away. Every edge declares its side grammar: development
is right-to-left, inspiration right-to-top, and subordinate or parallel
branches bottom-to-top. An incomplete relation review permits the atlas but
never an unreviewed semantic chapter or section map.

Work in task-scoped staging and write outputs atomically. Never replace an
existing corpus, manifest, or Canvas without explicit authorization.
