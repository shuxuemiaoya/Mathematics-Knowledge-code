# Book to Wiki Graph Agent Contract

This plugin is independent from `Book to Obsidian Wiki Graph`. Do not import
textbook-, subject-, publisher-, or edition-specific hierarchy rules.

## Goal

Convert any complete book into exactly two Markdown node layers:

- organizers: an open-depth, TOC-centered ownership hierarchy. A nonterminal
  organizer note begins with its own global-depth heading, then contains
  ordered direct-child embeds; each organizer-child embed is preceded by that
  child's global-depth heading (`#`, then `##`, then `###`, capped at `H6`). A
  terminal organizer linking atoms has no heading. Such leaves are flat,
  clearly named notes in the parent directory rather than one-file folders;
- atoms: source-complete, childless, outgoing-note-link-free primary knowledge,
  worked-example, exercise, or substantial-scenario notes, plus derived concept
  and formula excerpts. Primary files use `K/W/E/S/T`; formula files use `F`,
  while definition-only concept cards use their canonical concept names,
  never participate in source coverage, and point back through
  `derived_from_key`.

An organizer may own organizer children, atom children, or both. Preserve the
mixed `children` source order. Usually only the deepest organizers own atoms,
but never invent wrapper organizers merely to force that shape.

Every organizer Markdown note begins with Obsidian properties. Record its
stable key, immediate parent title/key/file (or explicit `null` for the book
root), source filename and digest, global organizer level, root-to-self
hierarchy path, owned heading ranges and source anchor, structural role,
direct child counts, descendant atom count, update date, and review status.
Generated concept/formula index notes under `组织层/` follow the same provenance
contract. Frontmatter does not change the heading or embed rules above.

## Required sequence

```text
freeze source -> PDF to Markdown when needed -> review TOC and ownership
-> demote pedagogical activity labels and create reviewed knowledge topics
-> prepare category-aware atomization jobs -> joint boundary/signature/local-relation pass
-> validate round one -> prepare every-adjacency audit
-> Agent/model round-two keep/merge/resegment review -> finalize
-> require zero unresolved review items -> invoke knowledge-relation-mapper on frozen virtual atoms
-> canonical concept extraction -> hybrid relation decisions -> full graph audit
-> feed merge/split/resegment back to atomization at most twice
-> require both reviews to pass -> materialize ranges and relations together
-> write derived cards/indexes -> build three-level knowledge constellation bundle
-> validate complete Canvas bundle
```

In `llm-category-aware-graph` mode the LLM has exclusive authority over the
number and boundaries of knowledge atoms. Baseline draft spans are only
coverage/context hints; deterministic code validates ranges, ownership,
source coverage, evidence, and links but never chooses a merge or split.
Formal definitions are semantic anchors even without transition words, so
parallel definitions such as 全称量词 and 存在量词 remain separate reusable
topics under a compound section.

MinerU is the default PDF converter. Other PDF tools may supplement it for
diagnosis or repair, but source identity, page order, formulas, tables, images,
and resource links must remain auditable.

Printed or OCR headings such as “observe”, “think”, “try”, “discuss”, and
“explore” describe an activity inside an atom; they are not organizers merely
because they were rendered as Markdown headings. Under a TOC section, place a
section-wide introduction first, reusable knowledge-topic organizers next, and
the terminal formal exercise set last. A short prior-knowledge question is a
direct `section-introduction` when several sibling topics collectively answer
it; do not absorb it into the first topic. Inline practice belongs to the
preceding or explicitly targeted topic, not beside that topic at section level.
Keep adjacent formally defined concepts separate when their dependency and
reuse roles differ. Apply a digest-bound organizer review before atomization so
demoted headings remain traceable in exact source ranges.

## Atomization rules

- A knowledge atom is a complete teaching unit. Keep its definition,
  conditions, notation, explanation, derivation, and nearby conclusion
  together. Blank lines, images, formulas, boxes, and ordinary activity labels
  are soft boundaries only.
- A short observation, question, or thinking prompt stays with the knowledge it
  elicits. Only a complete narrative, real-world context, experiment setup, or
  learning motivation may be a `scenario` atom.
- A short `knowledge-motivation` may stand alone when it explicitly connects
  learned content to a distinct next topic. It must support a reviewed incoming
  and outgoing `motivates` chain; otherwise merge it into the knowledge it
  scaffolds.
- A complete post-knowledge comparison, synthesis, extension, or open inquiry
  is the exception: keep it independently as `category: scenario` with
  `scenario_role: reflection-question`, store it under
  `原子层/思考题/NNNN-T.md`, and relate it as a motivating inquiry. Do not turn
  it into an exercise merely because it is phrased as a question.
- A topic organizer may own several independently reusable knowledge atoms;
  enumeration and description methods, for example, stay separate under one
  shared representation-method organizer.
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
branches bottom-to-top. Knowledge cards use a generous compact-cluster layout:
actual right-side targets never move left of their source and actual bottom-side
targets never move above it; unrelated regions are packed into a stable two-
dimensional field instead of a forced diagonal. Every nested organizer with
visible cards is encoded as a Canvas `group` envelope inside its section region.
The title/header is navigation only and never fans out spokes to every region.
An incomplete relation review permits the atlas but
never an unreviewed semantic chapter or section map.

Work in task-scoped staging and write outputs atomically. Never replace an
existing corpus, manifest, or Canvas without explicit authorization.
