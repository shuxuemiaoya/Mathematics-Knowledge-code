# Two-pass Teaching Relation Review

Run relation review after Markdown materialization so every endpoint uses its
final stable atom key. The current Agent is the default reviewer. An external
model is optional and requires an exact model plus `--execute`.

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

## First pass

Run `relate_book.py prepare`. Jobs are chapter-scoped and split only when their
source text exceeds the configured packet size. For every atom return:

- `atom_key`;
- `role`: `core`, `bridge`, or `satellite`;
- grounded `teaches` and `assumes` concept phrases.

Then propose relations with `from_key`, `to_key`, `type`, `tier`,
`evidence_kind`, endpoint `evidence_ranges`, a concrete `rationale`, and
`confidence`. The model may not rewrite atom text.

Use `bridge` only for a worked example whose solution exposes a substantial,
reusable mathematical idea or method (for example modeling, transformation,
invariant, multiple-solution comparison, or generalization). Routine
substitution and calculation examples remain `satellite`. `apply` copies the
reviewed bridge-example keys into `relation_review.featured_example_keys` for
Canvas selection; it never changes the example Markdown.

## Second pass

`prepare-audit` creates one audit per chapter plus one cross-chapter audit. It
includes every source-adjacent pair, each teaching satellite's nearest
knowledge candidate, concept-signature dependencies, first-pass relations,
and cross-chapter concept candidates.

Review every `candidate_id` and return the complete final relation set for the
scope. The model may add, remove, reverse, retype, or retier a relation. A
genuinely independent atom needs a source-specific reason; independence is not
a substitute for reviewing an unclear relationship.

## Gates

- Explicit relations require confidence `>= 0.90`.
- Pedagogical inferences require confidence `>= 0.95` and evidence from both
  endpoint atoms.
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
python scripts/relate_book.py prepare <book-graph.json> \
  --output-dir <relation-staging>

python scripts/relate_book.py validate-round1 \
  <relation-staging>/relation-jobs.json \
  <relation-staging>/round-1-relations.json

python scripts/relate_book.py prepare-audit \
  <relation-staging>/relation-jobs.json \
  <relation-staging>/round-1-relations.json \
  --output-dir <relation-staging>

python scripts/relate_book.py finalize \
  <relation-staging>/relation-jobs.json \
  <relation-staging>/round-1-relations.json \
  <relation-staging>/round-2-jobs.json \
  <relation-staging>/round-2-relations.json \
  --output-dir <relation-staging>

python scripts/relate_book.py apply \
  <book-graph.json> <relation-staging>/relation-final.json \
  --output <book-graph-with-relations.json>
```

`apply` refuses unresolved or stale results and never overwrites without
`--overwrite`.
