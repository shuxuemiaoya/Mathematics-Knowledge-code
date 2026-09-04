---
name: book-to-wiki-graph
description: Convert a book PDF or source Markdown into a TOC-centered Wiki graph with open-depth organizers, two-pass semantic atomization, three-pass atom-concept relation mapping, and two-level Obsidian knowledge constellations. Use for book conversion, corpus or relation audits, resumes, atomization repair, and learning-map Canvas rebuilds across subjects; do not use for summaries or prose-only exports.
---

# Book to Wiki Graph

Build a source-faithful graph without assuming a subject, publisher, edition,
chapter count, or fixed organizer depth. The old `Book to Obsidian Wiki Graph`
plugin is separate and must not be modified by this workflow.

## Read

- Read [references/architecture.md](references/architecture.md) before
  atomization or corpus repair.
- Read [references/organizers.md](references/organizers.md) before deciding
  whether source headings are organizers or atom content.
- Read [references/atomization.md](references/atomization.md) before producing
  either model pass or resolving its review queue.
- Read [references/relations.md](references/relations.md) before producing
  relation decisions, resolving a relation queue, or building a semantic map.
- Read [references/manifests.md](references/manifests.md) when creating or
  editing `book-profile.json` or `book-graph.json`.
- Read [references/pdf-conversion.md](references/pdf-conversion.md) for PDF
  input.
- Read [references/canvas.md](references/canvas.md) before Canvas work.

## Pipeline

1. Freeze the source with `scripts/init_book.py`. Treat the source and its
   digest as immutable.
2. For PDF input, use `scripts/convert_pdf.py`. MinerU is the default converter;
   other PDF tools may supplement diagnosis or repair. Preserve page order,
   formulas, tables, images, captions, and auditable resource links.
3. Extract the printed TOC as an open-depth organizer tree, then apply a
   digest-bound organizer review with `scripts/refine_organizers.py`. Keep
   chapters/sections and source-supported knowledge topics as organizers;
   demote pedagogical labels such as observe/think/try/discuss into the atom
   content they introduce. Practice and exercise-set headings may remain
   organizers. Lock the reviewed ownership before model atomization.
4. Run `scripts/atomize_book.py prepare` against the reviewed draft graph.
   The current Agent is the default reviewer. Produce range-only round-one
   decisions that repartition each organizer's direct prose into complete
   teaching units.
5. Run `validate-round1`, then `prepare-audit`. In round two, review every
   adjacent atom as `keep`, `merge`, or `resegment`, and return the full final
   partition. Never rewrite the source text.
6. Run `finalize`. Stop if the final status is not `passed` or
   `atomization-review-queue.json` has unresolved items.
7. Run `scripts/materialize_book.py`. It copies approved source content while
   omitting Markdown heading lines from atom bodies, rewrites/copies assets,
   renders compact organizer notes, and binds both review passes into
   `book-graph.json`.
8. After materialization, invoke `$knowledge-relation-mapper`. Its first pass
   treats atoms as immutable TextUnits, extracts book-scoped canonical concept
   proposals, and maps every atom to an explicit teaching role with source-line
   evidence. Do not recreate concepts from exercise wording alone.
9. Its second pass disambiguates concepts and judges every hybrid candidate
   from source order, ownership, explicit mentions, text search, optional
   embeddings, graph neighbourhoods, and cross-chapter recurrence. Its third
   pass audits WCC, DAG cycles, backward prerequisite edges, redundancy,
   evidence, and unjustified isolation. Only exceptional unresolved cases go
   to the human queue; unresolved relations block semantic chapter maps, not
   the Markdown corpus or navigation atlas.
10. Apply only a passed `relation-final.json`. Validate the enriched dual-layer
    graph, build the two-level Canvas bundle with selective virtual concept
    hubs, then validate again with `--canvas-index`. JSON remains authoritative;
    optional Neo4j export never edits it.

## Semantic boundaries

- Knowledge is a complete teaching unit: keep the definition, conditions,
  notation, explanation, derivation, and nearby conclusion together. Split
  only when both sides can be named, understood, and reused independently.
- Merge a short observation/thinking prompt with the knowledge it elicits.
  A scenario atom requires a complete narrative, real-world context,
  experiment setup, or learning motivation.
- Keep each worked example's stem, analysis, solution, and nearby conclusion
  together. Keep each top-level exercise with all subparts, figures, tables,
  and supplied material.
- Organizer ownership, exclusions, explicit example starts, and top-level
  exercise starts are hard constraints. Blank lines, images, formulas, boxes,
  and ordinary activity labels are soft evidence only.
- Knowledge shorter than 150 normalized characters or with one nonblank line
  requires second-pass audit. It may remain independent only as a formal
  definition, theorem, or law with a concrete reason and confidence at or above
  the configured short-atom threshold (default `0.95`).

## Graph and Canvas invariants

- The only Markdown node layers are `organizer` and `atom`; the only atom
  categories are `knowledge`, `worked-example`, `exercise`, and `scenario`.
- An organizer may own organizers, atoms, or both. Preserve its mixed direct
  `children` order. Do not impose a maximum depth or mandatory wrapper level.
- Atoms have one owner, no children, and no Markdown/Wiki/HTML note links.
  Source image/media embeds are allowed. Atom bodies contain no Markdown
  headings, and atom filenames are opaque sequence-plus-category codes such as
  `0001-K.md`, never prose titles.
- An organizer with only atom children is a single numbered Markdown file in
  its parent's directory, not a one-file subdirectory. Organizers that own
  other organizers retain a directory. Organizer notes do not repeat their own
  title: the parent supplies each organizer child's root-relative directory
  heading (`#` for a top-level child, `##` for the next level, then `###`, and
  so on). A terminal organizer that links atoms contains embeds only and no
  heading.
- Every nonblank source line is covered exactly once by an atom, organizer
  heading, or reviewed exclusion. Atom ranges never overlap.
- Reviewed semantic data forms an atom/concept dual graph and never modifies
  atom prose. Canonical concepts have source evidence; atom-concept roles state
  how each atom teaches or uses them; concept relations express prerequisite,
  development, derivation, hierarchy, contrast, or analogy. The compatible
  atom `relations` projection carries `basis_keys` back to concept relations.
  Directed edges follow learning flow, inferred edges cite both endpoints, and
  backbone relations remain acyclic.
- `overview.canvas` contains the book hub and chapters only. It aggregates
  cross-chapter routes and links each chapter to one chapter knowledge Canvas.
- A chapter Canvas displays every knowledge and scenario atom, but never emits
  individual exercise cards. Collapse exercises into the highest available
  exercise-only organizer Markdown card (or their nearest organizer when no
  exercise-only wrapper exists). Show a worked-example atom only when relation
  review marks it `bridge` for a substantial reusable mathematical idea or
  method; routine examples remain reachable through organizer notes.
- Use direct sections as regions and deeper organizers as landmarks. Suppress a
  landmark with no visible descendant; connect every retained landmark to its
  nearest rendered descendant with exactly one neutral `包含` edge. This sparse
  anchor is not a reconstruction of the full ownership tree. Cross-chapter
  endpoints are deduplicated perimeter portals. A multi-concept exercise set
  may use an unlinked virtual junction node to make inclusion and convergence
  legible; virtual nodes never pretend to be Markdown files. Reject isolated
  substantive cards, including landmarks and exercise clusters.
- Follow the port grammar adapted from the reference knowledge map: progressive
  knowledge leaves from the right and enters the next node from the left;
  `motivates` enters the inspired node from the top; example/application,
  exercise containment, contrast, and analogy branch from the bottom and enter
  from the top. Encode every edge with explicit `fromSide` and `toSide`.
- Category changes color and label only. Use stable, collision-free,
  center-outward constellation placement and theme-adaptive native colors.

## Commands

```bash
python scripts/init_book.py <source> <staging_root> <book_root> \
  --output <staging_root>/book-profile.json

python scripts/convert_pdf.py <book.pdf> \
  --output <staging_root>/book.raw.md \
  --env-file <project>/.env \
  --report <staging_root>/conversion-report.json

python scripts/refine_organizers.py \
  <staging_root>/draft-book-graph.json \
  <staging_root>/organizer-review.json \
  --output <staging_root>/refined-draft-book-graph.json \
  --report <staging_root>/organizer-review-report.json

python scripts/atomize_book.py prepare <staging_root>/refined-draft-book-graph.json \
  --output-dir <staging_root>

python scripts/atomize_book.py validate-round1 \
  <staging_root>/atomization-jobs.json \
  <staging_root>/round-1-decisions.json \
  --output <staging_root>/round-1-validation.json

python scripts/atomize_book.py prepare-audit \
  <staging_root>/atomization-jobs.json \
  <staging_root>/round-1-decisions.json \
  --output-dir <staging_root>

python scripts/atomize_book.py finalize \
  <staging_root>/atomization-jobs.json \
  <staging_root>/round-1-decisions.json \
  <staging_root>/round-2-jobs.json \
  <staging_root>/round-2-decisions.json \
  --output-dir <staging_root>

python scripts/materialize_book.py \
  <staging_root>/refined-draft-book-graph.json \
  <staging_root>/atomization-final.json \
  --book-root <book_root> \
  --output-manifest <book_root>/book-graph.json

python ../knowledge-relation-mapper/scripts/relate_book.py prepare-concepts \
  <book_root>/book-graph.json --output-dir <relation_staging>

python ../knowledge-relation-mapper/scripts/relate_book.py prepare-relations \
  <relation_staging>/concept-jobs.json \
  <relation_staging>/round-1-concepts.json --output-dir <relation_staging>

python ../knowledge-relation-mapper/scripts/relate_book.py prepare-audit \
  <relation_staging>/relation-jobs.json \
  <relation_staging>/round-2-relations.json --output-dir <relation_staging>

python ../knowledge-relation-mapper/scripts/relate_book.py finalize \
  <relation_staging>/concept-jobs.json \
  <relation_staging>/round-1-concepts.json \
  <relation_staging>/relation-jobs.json \
  <relation_staging>/round-2-relations.json \
  <relation_staging>/graph-audit-jobs.json \
  <relation_staging>/round-3-audit.json --output-dir <relation_staging>

python ../knowledge-relation-mapper/scripts/relate_book.py apply \
  <book_root>/book-graph.json <relation_staging>/relation-final.json \
  --output <book_root>/book-graph.with-relations.json

python scripts/validate_book_graph.py <book_root>/book-graph.with-relations.json \
  --book-root <book_root>

python scripts/build_canvas.py <book_root>/book-graph.with-relations.json \
  --book-root <book_root> --output-dir <book_root>/Canvas

python scripts/validate_book_graph.py <book_root>/book-graph.with-relations.json \
  --book-root <book_root> \
  --canvas-index <book_root>/Canvas/canvas-index.json
```

For optional external execution, require an exact model and explicit consent:

```bash
python scripts/run_atomization_model.py <jobs-or-audits.json> \
  --round 1 --model <exact-model-id> --execute \
  --output <decisions.json>

python ../knowledge-relation-mapper/scripts/run_relation_model.py <phase-jobs.json> \
  --phase concepts|relations|audit --model <exact-model-id> --execute \
  --output <relation-decisions.json>
```

Completion requires unchanged source digests, zero unresolved atomization and
relation review items for semantic maps, passed graph and Canvas validation,
and explicit counts for organizers, atoms, categories, resources, relations,
and every Canvas role.
