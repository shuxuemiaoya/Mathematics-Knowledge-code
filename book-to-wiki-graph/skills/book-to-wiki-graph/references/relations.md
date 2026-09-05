# Three-pass Dual-layer Teaching Relation Review

Run relation review after Markdown materialization so every endpoint uses its
final stable atom key. Invoke the plugin's independent
`$knowledge-relation-mapper` Skill and follow its `workflow.md` and `schema.md`.
The current Agent is the default reviewer. An external model is optional and
requires an exact model plus `--execute`.

## Relation ontology and direction

Every directed edge follows the learning process:

| Type | Meaning |
| --- | --- |
| `prerequisite` | The source is required before the target. |
| `develops` | The target extends, refines, or generalizes the source. |
| `derives` | The target follows logically from the source. |
| `motivates` | The source raises, frames, or triggers the target. |
| `illustrates` | The target illustrates the source concept. |
| `applies` | The target applies the source concept. |
| `practices` | The target practices the source concept. |
| `contrasts` | The endpoints clarify one another by contrast. |
| `analogous` | The endpoints share a useful analogy. |

`contrasts` and `analogous` are symmetric and store endpoints in lexical key
order. A learned idea that prompts a later question and then a new idea is:

```text
learned atom -> motivates -> scenario atom -> motivates -> new atom
```

## First pass — concepts

Run `knowledge-relation-mapper/scripts/relate_book.py prepare-concepts`. Treat
each final atom as an immutable TextUnit. Extract canonical concept proposals,
definitions, aliases, kinds, exact source evidence, atom-concept teaching roles,
and the `core`/`bridge`/`satellite` display role for every atom.

Concept names must be reusable mathematical units, never a full question,
activity label, exercise number, or truncated sentence. Exercises map existing
concepts and do not originate a concept from question wording alone.

Use `bridge` only for a worked example whose solution exposes a substantial,
reusable mathematical idea or method (for example modeling, transformation,
invariant, multiple-solution comparison, or generalization). Routine
substitution and calculation examples remain `satellite`. `apply` copies the
reviewed bridge-example keys into `relation_review.featured_example_keys` for
Canvas selection; it never changes the example Markdown.

## Second pass — disambiguation and hybrid candidates

`prepare-relations` creates concept merge, concept relation, and atom projection
candidates from source proximity, organizer neighbourhood, explicit mentions,
teaches/assumes roles, full-text lexical similarity, optional embeddings,
existing graph two-hop neighbours, and cross-chapter concept recurrence. Hard
candidates are retained; other candidates are capped at 12 per atom.

Review every `candidate_id` as forward, reverse, or unrelated. Embeddings only
recall candidates. They never merge concepts or create a relation. Concept
merges need confidence `>= 0.97`; same-name/different-definition items remain
separate.

## Third pass — graph structure

`prepare-audit` constructs a whole-graph audit. Check WCC, backbone DAG cycles,
backward prerequisite relations, duplicates, direction conflicts, inferred
transitive redundancy, concept grounding, teaching-role orphans, packet seams,
and cross-chapter connections. Return the complete corrected graph. Every
secondary component needs a specific mathematical independence reason.

## Gates

- Explicit relations require confidence `>= 0.90`.
- Pedagogical inferences require confidence `>= 0.95`; all final relations
  retain resolvable evidence from both ends.
- Backbone edges are limited to `prerequisite`, `develops`, `derives`, and
  `motivates`; their endpoints must be knowledge or scenario atoms.
- The backbone is acyclic.
- Every worked example and exercise connects to knowledge. A scenario connects
  to the knowledge that triggers it, the knowledge it motivates, or both.
- Self-relations, duplicates, opposite directed claims, stale digests,
  incomplete candidate review, unsupported evidence ranges, and unjustified
  orphans enter `relation-review-queue.json`.
- Prefer a connected backbone over independent knowledge islands. A knowledge
  or scenario atom may be independent only when its source-specific reason is
  reviewed; “the relation is unclear” is not sufficient.

An unresolved queue blocks semantic chapter maps but not the relation-free
book atlas or the Markdown corpus.

## Commands

```bash
python ../knowledge-relation-mapper/scripts/relate_book.py prepare-concepts \
  <book-graph.json> --output-dir <relation-staging>

python ../knowledge-relation-mapper/scripts/relate_book.py prepare-relations \
  <relation-staging>/concept-jobs.json \
  <relation-staging>/round-1-concepts.json --output-dir <relation-staging>

python ../knowledge-relation-mapper/scripts/relate_book.py prepare-audit \
  <relation-staging>/relation-jobs.json \
  <relation-staging>/round-2-relations.json \
  --output-dir <relation-staging>

python ../knowledge-relation-mapper/scripts/relate_book.py finalize \
  <relation-staging>/concept-jobs.json \
  <relation-staging>/round-1-concepts.json \
  <relation-staging>/relation-jobs.json \
  <relation-staging>/round-2-relations.json \
  <relation-staging>/graph-audit-jobs.json \
  <relation-staging>/round-3-audit.json \
  --output-dir <relation-staging>

python ../knowledge-relation-mapper/scripts/relate_book.py apply \
  <book-graph.json> <relation-staging>/relation-final.json \
  --output <book-graph-with-relations.json>
```

`apply` refuses unresolved or stale results and never overwrites without
`--overwrite`.
