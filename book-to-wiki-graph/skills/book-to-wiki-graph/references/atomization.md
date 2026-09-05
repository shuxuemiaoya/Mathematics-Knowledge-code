# Two-pass Semantic Atomization

Use this contract after the organizer hierarchy and direct-content ownership
have been reviewed. The input is a draft `book-graph.json`: its atom boundaries
may be heuristic, but its organizer tree, heading ranges, exclusions, source
digest, and direct owners must already be trustworthy.

## Hard and soft boundaries

Hard boundaries cannot be crossed or reclassified without human review:

- organizer ownership and selected top-level scope;
- reviewed exclusions and organizer heading ranges;
- explicit worked-example starts;
- top-level exercise starts and their complete subparts.

Blank lines, images, formulas, boxed conclusions, and ordinary activity labels
are soft evidence only. They do not justify a boundary when the teaching arc
continues.

## First pass

Run `atomize_book.py prepare`. Each job contains immutable numbered source
lines, the draft atoms, detected hard boundaries, organizer owner, top-level
scope, and a packet digest.

For every job, create one `round-1-decisions.json` entry:

```json
{
  "job_id": "job-0001-...",
  "packet_sha256": "<packet digest>",
  "atoms": [
    {
      "atom_id": "review-local-id",
      "owner_key": "organizer-key",
      "source_range": [100, 118],
      "category": "knowledge",
      "title": "A source-grounded title",
      "boundary_reason": "Why both boundaries are valid",
      "cohesion_reason": "Why these lines are one complete unit",
      "confidence": 0.97
    }
  ]
}
```

Seal the document with `artifact_sha256`, calculated from canonical JSON after
omitting that field. Decisions may contain ranges and metadata only. Fields
such as `body`, `content`, `markdown`, or rewritten text are rejected.

## Second pass

`prepare-audit` joins packet seams belonging to the same owner run and creates
an audit for every round-one adjacency. A round-two decision must:

- review every supplied boundary as `keep`, `merge`, or `resegment`;
- give a reason and confidence for each action;
- return the complete final contiguous partition for the audit range;
- preserve all hard boundaries;
- merge short prompts with the knowledge they introduce;
- keep examples and exercises source-complete.

For a short knowledge atom that legitimately remains independent, add
`standalone_kind` as `formal-definition`, `theorem`, or `law`, plus a concrete
`standalone_reason`; confidence must be at least the configured short-atom
threshold.

## Blocking behavior

`finalize` writes both `atomization-final.json` and
`atomization-review-queue.json`. Materialization is forbidden unless the final
artifact is `passed` and the queue has zero unresolved items. Structural
errors, stale digests, incomplete adjacency review, low confidence, hard
boundary violations, and unjustified short knowledge atoms all block.

The current Agent is the default reviewer. If the user explicitly chooses an
external model, run `run_atomization_model.py` with an exact `--model` and
`--execute`. The script uses Responses API Structured Outputs, stores only the
decisions and reviewer identity, and resumes only when the input artifact
digest and model match. It never has an implicit model and never records the
API key.

## Focused teaching-role audit

After two-pass boundaries pass, run `prepare-role-review`. This final recall
stage finds atoms whose category, boundary, or display title is still
suspicious: chapter-opening exercises, knowledge that looks like an unsolved
task, activity headings without a conclusion, multiple teaching roles, worked
solutions classified as knowledge, and overlong titles.

Every flagged item needs an explicit `keep` or `replace` decision. `keep`
requires a concrete teaching-cohesion reason. `replace` must partition the
original range exactly and may split, reclassify, concisely retitle, or reassign
inside the same top-level scope. It cannot consume adjacent source or rewrite
text. The usual short-knowledge independence rule applies again to replacement
atoms. An overlong title cannot pass unchanged.

Run `validate-role-review`, then `finalize-role-review`. When the profile sets
`teaching_role_audit` to `required-before-materialization`, the materialized
manifest must bind a passed role review with zero unresolved items. Relation
mapping also refuses a corpus whose required role audit is missing or stale.
