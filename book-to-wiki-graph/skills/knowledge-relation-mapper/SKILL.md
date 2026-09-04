---
name: knowledge-relation-mapper
description: Build or repair an evidence-audited educational knowledge graph from an already atomized book or knowledge base. Use when canonical concepts, concept disambiguation, prerequisite/development logic, orphan repair, GraphRAG-like candidate recall, Canvas semantic projection, or optional Neo4j export is needed; do not use for PDF conversion or atom boundary creation.
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

1. Verify that atomization and Markdown materialization have passed. Do not
   rewrite atoms or change organizer ownership here.
2. Run `scripts/relate_book.py prepare-concepts`. Treat atoms as immutable
   TextUnits. The current Agent is the default reviewer; emit exact source-line
   evidence for every concept and atom-concept role.
3. Run `validate-concepts`. Resolve every structural error. Send questionable
   labels, exercise-only concepts, aliases, or low confidence to review.
4. Run `prepare-relations`. Review every supplied hard and ranked candidate as
   related, reverse-related, or unrelated. Do not invent un-recalled edges.
5. Run `validate-relations`, then `prepare-audit`. In round three return a full
   replacement graph after checking cycles, direction, redundancy, connected
   components, orphan roles, cross-chapter seams, and unjustified isolation.
6. Run `finalize`. Only a `passed` artifact with zero unresolved items may be
   applied to `book-graph.json` or rendered as a semantic Canvas.
7. Optionally run `export_neo4j.py`. Run `sync_neo4j.py --execute` only after the
   user explicitly authorizes a database write and credentials are available.

## Hard rules

- Concepts are reusable mathematical ideas, definitions, properties, theorems,
  rules, procedures, representations, or methods. Never use a whole problem,
  activity label, truncated sentence, or exercise number as a concept name.
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
- A human queue contains only unresolved exceptions. Do not bypass it, lower a
  threshold, or mark an item resolved without evidence.

## Commands

```bash
python scripts/relate_book.py prepare-concepts <book-graph.json> \
  --output-dir <relation-dir> [--concept-registry <read-only.json>]

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
