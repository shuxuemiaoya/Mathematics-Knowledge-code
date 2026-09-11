---
name: knowledge-relation-mapper
description: Build or repair an evidence-audited educational knowledge graph from frozen atom ranges or an already materialized knowledge base. Use for canonical concepts, prerequisite/development logic, orphan repair, GraphRAG-like recall, pre-materialization boundary feedback, Canvas projection, or optional Neo4j export; do not use for PDF conversion.
---

# Knowledge Relation Mapper

Construct a dual-layer teaching graph: immutable source atoms ground canonical
concepts, and reviewed concept relations explain the atom projection used by
Canvas. JSON is always authoritative. Neo4j is an optional analysis copy.

## Read

- Read [references/workflow.md](references/workflow.md) before running any pass.
- Read [references/schema.md](references/schema.md) before creating or repairing
  model decisions, evidence, concepts, or relations.
- Read [references/neo4j.md](references/neo4j.md) only for export, sync, WCC, or
  Leiden work.

## Workflow

1. Prefer the pre-materialization route: verify a passed category-aware
   `atomization-final.json`, then run `prepare-concepts` on the reviewed base
   manifest with `--atomization-final`. The legacy materialized-manifest route
   remains supported. Never rewrite source or change organizer ownership.
2. Treat frozen atom ranges as immutable
   TextUnits. The current Agent is the default reviewer; emit exact source-line
   evidence for every concept and atom-concept role.
3. Run `validate-concepts`. Resolve every structural error. Send questionable
   labels, exercise-only concepts, aliases, or low confidence to review.
4. Run `prepare-relations`. Review every supplied hard and ranked candidate as
   related, reverse-related, or unrelated. Do not invent un-recalled edges.
5. Run `validate-relations`, then `prepare-audit`. In round three return a full
   replacement graph after checking cycles, direction, redundancy, connected
   components, orphan roles, cross-chapter seams, unjustified isolation, and
   whether the graph contradicts a knowledge boundary. Emit boundary feedback
   only with exact affected atoms, ranges, two-sided evidence, and confidence.
6. Run `finalize`. A `boundary_revision_required` result returns to the main
   Skill's `prepare-feedback`/`finalize-feedback` loop. Only `passed` with zero
   unresolved items may be materialized or rendered.
7. Optionally run `export_neo4j.py`. Run `sync_neo4j.py --execute` only after the
   user explicitly authorizes a database write and credentials are available.

## Hard rules

- Concepts are reusable mathematical ideas, definitions, properties, theorems,
  rules, procedures, representations, or methods. Never use a whole problem,
  activity label, truncated sentence, or exercise number as a concept name.
- A materialized concept card represents exactly one formally defined term.
  Use the term itself as `preferred_label` (`列举法`, not `列举法的定义` or
  `列举法的概念、格式与约定`). Split a compound editorial label when the
  source defines more than one reusable term. Concepts without a formal
  definition may remain virtual JSON nodes but do not become Markdown cards.
- A concept's evidence is definition-form only: keep the formal
  definition/property/rule sentence plus immediate conditions or formula, and
  exclude examples, thought prompts, questions, and activity scaffolding.
- A `reflection-question` atom remains scenario-semantic: map it to the learned
  concepts that trigger it, but never create a concept from its wording alone.
- A `section-introduction` framing question creates no concept from its wording.
  Map it to the concepts collectively answering it and require at least one
  outgoing `motivates` edge to the first knowledge unit that begins the answer;
  add sibling targets only when each has direct evidence in the question.
- A short `knowledge-motivation` is valid only when it is a real bridge: require
  evidence for learned knowledge feeding the prompt and for the distinct new
  knowledge it opens. If either side is absent, return boundary feedback to
  merge it into the surrounding teaching unit.
- Exercises map to existing concepts; they do not create concepts solely from
  their wording. A worked example becomes `bridge` only for a substantial,
  reusable mathematical method.
- Embeddings propose candidates only. They never merge concepts or create an
  edge automatically. Every final edge records its recall source and evidence.
- Inferred edges require evidence from both ends and the configured higher
  confidence threshold. Same-name/different-definition concepts stay separate.
- Backbone prerequisite/development/derivation relations are acyclic and point
  forward in learning order. Explicit transitive edges may remain supporting;
  inferred transitive redundancy is reviewed.
- Every knowledge atom teaches or explains a concept; every concept is grounded
  by atom evidence. Scenarios connect trigger or target concepts. Examples and
  exercises map to what they illustrate, apply, or practise.
- A secondary connected component needs a specific mathematical independence
  reason. “Relationship unclear” is never sufficient.
- Every visible knowledge atom has a reviewed semantic edge. If it is genuinely
  independent, record a concrete reason so Canvas may use an explicit `归属`
  edge; never invent a book-order dependency.
- Boundary feedback may merge, split, or resegment, but it cannot cross
  organizer ownership. It invalidates the affected chapter and cross-chapter
  relation digests. Stop after two automatic cycles.
- A human queue contains only unresolved exceptions. Do not bypass it, lower a
  threshold, or mark an item resolved without evidence.

## Commands

```bash
python scripts/relate_book.py prepare-concepts <book-graph.json> \
  --output-dir <relation-dir> [--concept-registry <read-only.json>]

# Preferred before Markdown materialization:
python scripts/relate_book.py prepare-concepts <reviewed-draft-book-graph.json> \
  --atomization-final <atomization-final.json> --output-dir <relation-dir>

python scripts/relate_book.py validate-concepts \
  <relation-dir>/concept-jobs.json <relation-dir>/round-1-concepts.json

python scripts/relate_book.py prepare-relations \
  <relation-dir>/concept-jobs.json <relation-dir>/round-1-concepts.json \
  --output-dir <relation-dir> [--embeddings <relation-embeddings.json>]

python scripts/relate_book.py validate-relations \
  <relation-dir>/relation-jobs.json <relation-dir>/round-2-relations.json

python scripts/relate_book.py prepare-audit \
  <relation-dir>/relation-jobs.json <relation-dir>/round-2-relations.json \
  --output-dir <relation-dir>

python scripts/relate_book.py finalize \
  <relation-dir>/concept-jobs.json <relation-dir>/round-1-concepts.json \
  <relation-dir>/relation-jobs.json <relation-dir>/round-2-relations.json \
  <relation-dir>/graph-audit-jobs.json <relation-dir>/round-3-audit.json \
  --output-dir <relation-dir>

python scripts/relate_book.py apply <book-graph.json> \
  <relation-dir>/relation-final.json --output <book-graph.enriched.json>
```

`apply` is the compatibility route for a graph that was already materialized.
For a relation final bound to `atomization-final.json`, pass it to the main
Skill's `materialize_book.py --relation-final` instead.

External calls have no implicit model and require explicit execution:

```bash
python scripts/run_relation_model.py <phase-jobs.json> \
  --phase concepts|relations|audit --model <exact-model-id> --execute \
  --output <phase-decisions.json>

python scripts/run_embeddings.py <concept-jobs.json> <round-1-concepts.json> \
  --model <exact-embedding-model> --execute \
  --output <relation-embeddings.json>
```

Report concept count, merges, candidate channels, acceptance rates, relation
distribution, component sizes, unresolved exceptions, and representative
before/after decisions. More edges are not inherently better.
