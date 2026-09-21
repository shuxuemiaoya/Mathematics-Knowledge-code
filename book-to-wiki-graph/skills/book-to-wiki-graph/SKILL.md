---
name: book-to-wiki-graph
description: Convert a book PDF or source Markdown into a TOC-centered Wiki graph with category-aware joint atomization, pre-materialization relation feedback, derived concept/formula cards, and three-level Obsidian knowledge constellations. Use for book conversion, corpus or relation audits, resumes, atomization repair, and learning-map Canvas rebuilds across subjects; do not use for summaries or prose-only exports.
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
   content they introduce. Place a section-wide introduction first, reusable
   knowledge topics next, and the terminal formal exercise set last. A short
   prior-knowledge question is a direct `section-introduction` when several
   sibling topics collectively answer it. Attach inline practice to its target
   topic, and keep adjacent defined concepts separate when their dependency and
   reuse roles differ. A printed instructional subsection must not be left with
   exercises only, and no synthesized topic subtree may extend past the next
   retained printed heading. Existing printed organizers may own reviewed
   source runs on both sides of their own heading. Lock the reviewed ownership
   before model atomization; category-aware preparation and materialization
   reject a missing or stale organizer review.
4. Run `scripts/atomize_book.py prepare` against the reviewed draft graph.
   The current Agent is the default reviewer. Each category-aware decision
   returns one complete source partition plus every knowledge atom's
   `teaches/assumes/outputs` signature, local evidence-bound relations, and
   source-contained concept/formula candidates.
   In category-aware mode the LLM exclusively decides knowledge-atom count and
   boundaries; baseline spans are non-binding coverage context. Formal
   definitions are semantic anchors even without transition words, so parallel
   definitions such as 全称量词 and 存在量词 remain separate reusable topics.
   Deterministic code validates ranges, ownership, evidence, and coverage only.
5. Run `validate-round1`, then `prepare-audit`. Round two reviews every boundary
   and local relation together. Merge one teaching process; split or resegment
   independently reusable knowledge with a different dependency structure.
6. Run `finalize`. Stop if the final status is not `passed` or
   `atomization-review-queue.json` has unresolved items.
   When repairing a legacy, already-materialized corpus whose sealed final
   split one book/chapter/section introduction into paragraph or image
   continuations, do not hand-edit Markdown. After the current Agent confirms
   the exact source-complete merge, use
   `scripts/migrate_scoped_introductions.py` to rebind atomization and relation
   finals, then rematerialize into staging. The migration accepts only one
   owner/role and blank-only gaps, removes redundant heading-free introduction
   wrappers, deletes fragment-to-fragment pseudo-relations, and leaves other
   boundary defects blocked for their normal organizer review.
   If rematerialization then exposes a legacy printed subsection as
   exercise-only, or a source-labelled exercise run crosses its next sibling,
   do not weaken validation. Use
   `scripts/migrate_legacy_organizer_ownership.py` against the validated legacy
   materialized manifest. It may only nest a reviewed heading-free teaching
   topic under its printed subsection or create reviewed exercise-group
   organizers. Atom ranges, categories, prose, and semantic claims stay fixed;
   owner keys, organizer paths, and bound digests are updated together.
7. Before Markdown materialization, invoke `$knowledge-relation-mapper` with
   `prepare-concepts ... --atomization-final ...`. Stable temporary keys are
   computed from organizer, range, and category. Its first pass extracts
   book-scoped canonical concept
   proposals, and maps every atom to an explicit teaching role with source-line
   evidence. Do not recreate concepts from exercise wording alone.
8. Its second pass disambiguates concepts and judges every hybrid candidate
   from source order, ownership, explicit mentions, text search, optional
   embeddings, graph neighbourhoods, and cross-chapter recurrence. Its third
   pass audits WCC, DAG cycles, backward prerequisite edges, redundancy,
   evidence, and unjustified isolation. Only exceptional unresolved cases go
   to the human queue. It may return evidence-backed `merge`, `split`, or
   `resegment` feedback when graph structure exposes a bad knowledge boundary.
9. Run `prepare-feedback` and `finalize-feedback` when required, then invalidate
   and rerun affected relation artifacts. Stop after two automatic cycles and
   block unstable cases for human review.
10. Only when both finals pass with zero unresolved items, run
    `materialize_book.py --relation-final`. It writes primary atoms, derived
    cards, organizer notes, indexes, and relations as one frozen result. The
    legacy role-review and post-materialization `apply` path remains available
    only for old `llm-two-pass` artifacts.
11. Validate the graph, build the three-level Canvas bundle, then validate again
    with `--canvas-index`. The builder emits a sibling PNG for every Canvas.
    Run `canvas_review.py prepare`, open every listed `png_path` with the image
    viewer (for this host, `view_image`) and inspect it with the current Agent,
    write structured decisions, and finalize the review before validating with
    `--canvas-review`. Logic completeness, relation direction, and unexplained
    islands are reviewed before visual polish; PNGs are visual evidence while
    JSON remains authoritative. Optional Neo4j export never edits it.

## Semantic boundaries

- Knowledge is a complete teaching unit: keep the definition, conditions,
  notation, explanation, derivation, and nearby conclusion together. Split
  only when both sides can be named, understood, and reused independently.
- The LLM, not paragraph shape, owns the partition. A compound section title is
  a recall hint rather than a reason to merge; independently reusable parallel
  definitions remain separate even when no transition phrase appears.
- Preserve every printed activity marker (`观察`, `思考`, `尝试`, `交流`,
  `探究`, etc.) in the source slice. The LLM must explicitly disposition each
  marker as a scenario, exercise, or `merged-with-knowledge` with a reason;
  silent deletion is invalid. A complete prompt is normally a scenario (a
  post-knowledge unanswered question is `reflection-question`). Merge a short
  marker only when its prompt and the immediately following definition form
  one inseparable teaching unit, and keep the marker as a plain source line.
- Classify introductions at their actual scope. A preface or reader guide is
  `book-introduction`; a chapter opening is `chapter-introduction`; a section
  opening that frames several child topics is `section-introduction`; and a
  complete problem or real-world context aimed at one topic is
  `knowledge-motivation`. Each book/chapter/section introduction is one
  source-complete discourse atom per owner and role, including every contiguous
  paragraph, question, figure and caption until the next structural heading.
  Never emit `续 2`/`part 2` or image-only introduction fragments.
- Keep a knowledge motivation's whole statement, figure/caption and final
  question together. It may be owned by a printed subsection even when the
  prompt occurs immediately before that subsection's heading; the retained
  heading splits model packets but does not force the prompt into an unrelated
  sibling topic.
- Keep a short prior-knowledge question as the section's first direct
  `section-introduction` when several sibling topics collectively answer it;
  do not absorb it into only the first topic. Inline practice belongs to the
  preceding or explicitly targeted topic, while the terminal formal exercise
  set remains the section's last direct organizer.
- Keep each worked example's stem, analysis, solution, and nearby conclusion
  together. Keep each top-level exercise with all subparts, figures, tables,
  and supplied material.
- Organizer ownership, exclusions, explicit example starts, and top-level
  exercise starts are hard constraints. Blank lines, images, formulas and
  boxes are soft evidence; activity labels remain source content and require
  an explicit LLM disposition.
- Knowledge shorter than 150 normalized characters or with one nonblank line
  requires second-pass audit. It may remain independent only as a formal
  definition, theorem, or law with a concrete reason and confidence at or above
  the configured short-atom threshold (default `0.95`).

## Graph and Canvas invariants

- The only Markdown node layers are `organizer` and `atom`. Primary atom
  categories are `knowledge`, `worked-example`, `exercise`, and `scenario`;
  derived categories are `concept` and `formula`.
- An organizer may own organizers, atoms, or both. Preserve its mixed direct
  `children` order. Do not impose a maximum depth or mandatory wrapper level.
- Atoms have one owner, no children, and no Markdown/Wiki/HTML note links.
  Source image/media embeds are allowed. Atom bodies contain no Markdown
  headings. Primary atom and formula filenames use opaque sequence-plus-category
  codes such as `0001-K.md`, with the number restarting independently in each
  destination folder; definition-only concept cards are the exception
  and use their canonical concept name with a stable suffix only for collisions.
- An organizer with only atom children is a single clearly named Markdown file in
  its parent's directory, not a one-file subdirectory. Organizers that own
  other organizers retain a directory. An organizer note does not repeat its
  own filename/title in the body. It supplies each organizer child's
  global-depth heading (`#` for the root, `##` for the next level, then `###`,
  and so on) before its embed. A terminal organizer that links atoms contains
  embeds only and no heading.
- Every organizer note begins with queryable Obsidian properties: stable key,
  immediate parent title/key/file (explicit `null` at the root), source name and
  digest, global level, root-to-self hierarchy path, heading ranges and source
  anchor, structural role, direct child counts, descendant atom count, update
  date, and review status. Apply the same provenance contract to generated
  concept/formula index notes under `组织层/`; frontmatter does not count as a
  body heading.
- Every nonblank source line is covered exactly once by a primary atom, organizer
  heading, or reviewed exclusion. Atom ranges never overlap.
- Every organizer child subtree ends before the next sibling's earliest source
  anchor. A printed non-exercise organizer whose primary descendants are all
  exercises is invalid: rerun organizer ownership review before atomization.
- `source_order` contains only primary atoms. `derived_order` contains exact
  source excerpts inside `derived_from_key`; these duplicates do not count
  toward coverage. Concept cards use collision-safe canonical names and formula
  cards use `NNNN-F.md`;
  contain no headings or note links, and are found through per-chapter index
  notes that do not enter Canvas.
- Reviewed semantic data forms an atom/concept dual graph and never modifies
  atom prose. Canonical concepts have source evidence; atom-concept roles state
  how each atom teaches or uses them; concept relations express prerequisite,
  development, derivation, hierarchy, contrast, or analogy. The compatible
  atom `relations` projection carries `basis_keys` back to concept relations.
  Directed edges follow learning flow, inferred edges cite both endpoints, and
  backbone relations remain acyclic.
- Every atom Markdown note begins with Obsidian properties for `atom_key`,
  `owner_key`, `source_pdf`, `source_sha256`, `source_range`, `used_by`,
  `updated_at`, `review_status`, estimated study time, difficulty, importance,
  and learning objectives. Knowledge notes additionally
  expose estimated learning minutes, difficulty, importance, and learning
  objectives; examples, exercises, scenarios, and derived cards carry their
  corresponding completeness or role properties.
- A complete post-knowledge comparison, synthesis, extension, or open inquiry
  is a scenario-semantic atom with `scenario_role: reflection-question`. Store
  it independently under `原子层/思考题/NNNN-T.md`; do not classify it as a
  worked example or routine exercise. A short prompt that merely scaffolds the
  immediately following explanation still belongs inside that knowledge atom.
- A short bridge that explicitly refers to learned content and opens a distinct
  next topic may stand alone as `scenario_role: knowledge-motivation`; accept
  it only when relation review can establish `learned knowledge → bridge → new
  knowledge`. A generic activity prompt is not such a bridge.
- A shared organizer may group several independently reusable knowledge atoms.
  For example, `集合的表达方式` owns separate `列举法` and `描述法` atoms rather
  than forcing them into one atom merely because they share a topic.
- Concept cards are definition references, not copied teaching passages. The
  model cites only a formal definition/property/rule sentence and immediate
  conditions or formula; examples, activity prompts, and questions stay in the
  parent knowledge atom (an inline illustrative clause may be clipped only in
  the derived card). Use the canonical concept name as the Markdown filename;
  add a deterministic short suffix only when two distinct concepts collide.
- Organizer paths use clear titles (for example `第一章…/1.1…`) and retain a
  generated numeric prefix only when needed to resolve a real collision.
- `overview.canvas` contains the book hub and chapters only. It aggregates
  cross-chapter routes and links each chapter to one chapter knowledge Canvas.
- A chapter Canvas is a low-noise core map: display every knowledge/scenario
  atom and only worked examples marked `bridge`, but no exercise card or
  practice edge. Direct sections are numbered star regions with click-through
  portals to section detail maps; do not duplicate organizer landmarks beside
  equivalent atom or concept cards.
- A section detail Canvas repeats that section's visible teaching atoms and
  collapses all exercises into their highest exercise-only organizer Markdown
  entries. Each entry has at most one primary practice edge and is placed in
  the same local star region as its knowledge anchor. Routine examples remain
  reachable through organizer notes. New graphs render no concept or formula
  nodes. A truly independent visible atom may connect bottom-to-top to its
  organizer portal with an explicit `归属` edge; never use `书序` as a disguised
  dependency. Reject unexplained islands and all overlapping nodes.
- Follow the port grammar adapted from the reference knowledge map: progressive
  knowledge leaves from the right and enters the next node from the left;
  `motivates` enters the inspired node from the top; example/application,
  exercise containment, contrast, and analogy branch from the bottom and enter
  from the top. Encode every edge with explicit `fromSide` and `toSide`.
- Category changes color and label only. Use stable, collision-free compact
  constellation clusters (rightward progression and downward branches only
  where an actual edge requires them), generous node spacing, nested organizer
  `group` envelopes, and theme-adaptive native colors. Unrelated regions use a
  deterministic two-dimensional packing rather than a diagonal chain. A target
  of a right-side semantic edge must never be left of its source; a target of a
  bottom-side edge must never be above its source. The map title is a quiet
  navigation header, not a spoke hub.

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

# Legacy repair only, after an Agent has reviewed the complete source span.
python scripts/migrate_scoped_introductions.py \
  <legacy_base_manifest> <legacy_atomization_final> <legacy_relation_final> \
  --output-dir <repair_staging>

python scripts/migrate_legacy_organizer_ownership.py \
  <repaired_base_manifest> <repaired_atomization_final> \
  <repaired_relation_final> <legacy_materialized_manifest> \
  --output-dir <repair_staging_2>

python ../knowledge-relation-mapper/scripts/relate_book.py prepare-concepts \
  <staging_root>/refined-draft-book-graph.json \
  --atomization-final <staging_root>/atomization-final.json \
  --output-dir <relation_staging>

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

python scripts/atomize_book.py prepare-feedback \
  <staging_root>/atomization-final.json \
  <relation_staging>/relation-final.json --output-dir <staging_root>

python scripts/atomize_book.py finalize-feedback \
  <staging_root>/atomization-final.json \
  <staging_root>/atomization-feedback-jobs.json \
  <staging_root>/atomization-feedback-decisions.json --output-dir <staging_root>

python scripts/materialize_book.py \
  <staging_root>/refined-draft-book-graph.json \
  <staging_root>/atomization-final.json \
  --relation-final <relation_staging>/relation-final.json \
  --book-root <book_root> --output-manifest <book_root>/book-graph.json

python scripts/validate_book_graph.py <book_root>/book-graph.json \
  --book-root <book_root>

python scripts/build_canvas.py <book_root>/book-graph.json \
  --book-root <book_root> --output-dir <book_root>/Canvas

python scripts/validate_book_graph.py <book_root>/book-graph.json \
  --book-root <book_root> \
  --canvas-index <book_root>/Canvas/canvas-index.json
python scripts/canvas_review.py prepare <book-root>/Canvas/canvas-index.json \
  --output <staging-root>/canvas-review-jobs.json

# The current Agent views every jobs[*].png_path and writes decisions with
# logic evidence before visual suggestions.
python scripts/canvas_review.py seal-decisions \
  <staging-root>/canvas-review-jobs.json \
  <staging-root>/canvas-review-draft.json \
  --output <staging-root>/canvas-review-decisions.json
python scripts/canvas_review.py finalize \
  <staging-root>/canvas-review-jobs.json \
  <staging-root>/canvas-review-decisions.json \
  --output-dir <staging-root>/canvas-review

python scripts/validate_book_graph.py <book-root>/book-graph.json \
  --book-root <book-root> \
  --canvas-index <book-root>/Canvas/canvas-index.json \
  --canvas-review <staging-root>/canvas-review/canvas-review-final.json
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
