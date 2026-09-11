# Three-pass workflow

## Pass 1 — canonical concept proposals

`prepare-concepts` packages atoms by chapter and direct organizer boundary with
one neighbouring packet of context. Preserve packet IDs and digests. For every
primary atom return at least one atom-concept link and one semantic display role.
Context atoms may support disambiguation but are not re-owned.

The reviewer extracts reusable concepts from knowledge, scenarios, and major
method examples. Exercises only map to a proposal grounded outside the exercise.
Each proposal provides a preferred label, aliases, a concise definition, one
fixed kind, and exact source evidence. `validate-concepts` rejects stale packets,
missing atom coverage, invalid line ranges, and invalid roles; suspicious names
and exercise-only concepts go to review.

For `scenario_role: reflection-question`, reuse the scenario relation grammar:
learned knowledge points into the question with `motivates`; if grounded later
or external knowledge answers the inquiry, the question may point to that target
with `motivates`. The question wording itself is not a concept proposal.

For `scenario_role: section-introduction`, map the atom to the concepts that
collectively answer its framing question, but create no concept from the
question wording. Require an outgoing `motivates` edge to the first knowledge
unit that begins the answer. Additional sibling targets are allowed only when
the wording and both endpoint ranges support each edge; book order alone is not
evidence.

For a short `scenario_role: knowledge-motivation`, require both sides of the
bridge in the audit: learned content must motivate the prompt, and the prompt
must motivate a distinct target topic. A one-sided short prompt is evidence of
an atomization error and should produce boundary feedback rather than an
artificial relation.

## Pass 2 — candidate decision and disambiguation

`prepare-relations` combines these recall channels:

- source-window proximity;
- direct organizer neighbourhood;
- explicit concept mention;
- teaches/assumes and shared-concept links;
- lexical full-text similarity;
- optional embedding similarity;
- existing reviewed edges and their two-hop neighbourhood;
- cross-chapter concept recurrence.

Hard candidates are never truncated. Ranked soft candidates are capped per atom
by `max_ranked_candidates_per_atom`. Each candidate records channels and scores.
The reviewer must acknowledge every candidate ID. Omitted atom/concept relation
records mean “no relation”; every merge candidate requires `merge` or
`keep-separate`. Direction may be reversed from the unordered candidate pair.

## Pass 3 — full graph audit

`prepare-audit` canonicalizes accepted merges and computes WCC, backbone DAG
cycles, structural cycles, backward learning edges, inferred transitive
redundancy, ungrounded concepts, and role orphans. The reviewer acknowledges
every issue and returns a complete replacement graph, not a patch.

Round three may merge or separate concepts, add/delete/reverse/retype relations,
change tiers, and repair links. A declared independent atom or component needs a
specific mathematical reason. Any validation error, confidence review, label
review, unexplained WCC, cycle, or orphan keeps `relation-final.json` from
passing and blocks semantic chapter Canvas generation.

## Resume and integrity

All artifacts carry content digests and bindings to their exact predecessor.
External model execution writes a sealed partial artifact after each packet and
resumes only when input digest and model ID match. Changed source, profile,
manifest, earlier decisions, embeddings, or model identity requires regeneration.

The Agent may review packets directly without an API call. In that case it must
produce the same schemas and identify itself in each artifact's `reviewer` field.

## Boundary feedback loop

With `prepare-concepts --atomization-final`, atoms are stable virtual records,
not yet-written Markdown. Local relations from atomization enter hard candidate
recall. Round three may return `boundary_feedback` only when dependency evidence
shows that ranges must merge, split, or be resegmented. The main Skill owns the
revision and permits at most two automatic cycles. A changed atomization digest
invalidates relation, audit, and cross-chapter decisions.
