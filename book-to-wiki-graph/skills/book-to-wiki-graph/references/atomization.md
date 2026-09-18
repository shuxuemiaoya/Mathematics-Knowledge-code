# Category-aware Semantic Atomization

Use this contract after the organizer hierarchy and direct-content ownership
have been reviewed. The input is a draft `book-graph.json`: its atom boundaries
may be heuristic, but its organizer tree, heading ranges, exclusions, source
digest, and direct owners must already be trustworthy. In
`llm-category-aware-graph` mode, a missing or stale digest-bound organizer
review blocks both preparation and materialization.

## Hard and soft boundaries

Hard boundaries cannot be crossed or reclassified without human review:

- organizer ownership and selected top-level scope;
- reviewed exclusions and organizer heading ranges;
- explicit worked-example starts;
- top-level exercise starts and their complete subparts.

Blank lines, images, formulas, boxed conclusions, and activity labels are soft
boundary evidence, but activity labels are not disposable: each printed
`观察`/`思考`/`尝试`/`交流`/`探究` marker must be preserved in a source slice
and explicitly dispositioned by the LLM as scenario, exercise, or
`merged-with-knowledge`.

## First pass

Run `atomize_book.py prepare`. Each job contains immutable numbered source
lines, the draft atoms, detected hard boundaries, organizer owner, top-level
scope, and a packet digest.

For every job, create one `round-1-decisions.json` entry:

```json
{
  "job_id": "job-0001-...",
  "packet_sha256": "<packet digest>",
  "activity_dispositions": [
    {"line": 104, "atom_id": "review-local-id", "disposition": "scenario", "rationale": "完整问题引发后续概念"}
  ],
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

Derived concept cards are definition references. Their evidence must remain
inside a knowledge atom and select only the formal definition/property/rule
sentence with immediate conditions or formula; examples, prompts, questions,
and activity scaffolding are never copied into the concept card. If a textbook
places an inline illustration on the same physical line, the materializer
clips that illustrative clause from the derived card while leaving the parent
knowledge atom unchanged.

### Scenario scope before paragraph shape

Choose a scenario role before choosing its boundaries:

- `book-introduction`: preface, reader guide, or whole-book orientation;
- `chapter-introduction`: one chapter-opening discourse;
- `section-introduction`: one framing passage/question answered by several
  sibling topics;
- `knowledge-motivation`: one complete problem, example, experiment, or
  real-world context aimed at one target knowledge topic;
- `reflection-question`: a complete post-teaching inquiry.

A book/chapter/section introduction is exactly one contiguous atom per owner
and role. Keep all paragraphs, questions, figures and captions through the last
introductory line before the next structural heading. Paragraph breaks, page
breaks and image placement are never atom boundaries. Titles such as `续 2`
or `part 2`, multiple same-role atoms under one owner, and image-only
continuations enter the blocking review queue.

A knowledge motivation keeps the complete context, figure/caption and final
question. It may appear just before the printed heading of the topic it
introduces. The retained heading divides model packets, but the organizer
review may assign reviewed source runs on both sides of that heading to the
same existing printed organizer.

### LLM-exclusive knowledge boundaries

For `llm-category-aware-graph`, the LLM alone decides the number, titles, and
boundaries of knowledge atoms. Draft atoms are provisional coverage/context
hints, never binding partitions. Deterministic validators check only continuous
source ranges, hard ownership boundaries, evidence, and complete coverage.
Formal definition starts are semantic anchors even without a transition word:
adjacent independently reusable definitions (such as 全称量词 and 存在量词)
must be separate atoms. A compound section heading is not evidence that its
concepts should be merged.

Each materialized concept card names exactly one term. Use the term itself as
the label and filename (`列举法.md`, not `列举法的定义.md`). If a canonical graph
node is useful for reasoning but lacks formal definition-form source evidence,
keep it in JSON only and do not create a Markdown concept card.

## Second pass

`prepare-audit` joins packet seams belonging to the same owner run and creates
an audit for every round-one adjacency. A round-two decision must:

- review every supplied boundary as `keep`, `merge`, or `resegment`;
- give a reason and confidence for each action;
- return the complete final contiguous partition for the audit range;
- preserve all hard boundaries;
- preserve activity markers and either classify their complete prompt as a
  scenario/exercise or explicitly merge them into the knowledge they introduce;
- keep a short prior-knowledge question as a direct
  `scenario_role: section-introduction` when several sibling knowledge topics
  collectively answer it; place it before those topics and never absorb it
  into only the first topic;
- keep a short `knowledge-motivation` separately only when it explicitly
  bridges learned content to a distinct next topic and the relation pass can
  support `learned knowledge → bridge → new knowledge`;
- merge paragraph-, continuation-, or image-level fragments of one
  book/chapter/section introduction into one complete scoped atom;
- verify every `knowledge-motivation` contains the complete problem/context,
  figure or caption, and final question rather than only one fragment;
- retain a complete post-knowledge comparison, synthesis, extension, or open
  inquiry as `category: scenario` with
  `scenario_role: reflection-question`; store it as a thought question rather
  than treating it as an example or routine exercise;
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

## Category-aware graph mode

`llm-category-aware-graph` is the default. Both model rounds return, alongside
the complete partition, `knowledge_signatures`, `local_relations`, and
`derived_card_candidates`. Knowledge uses complete teaching semantics;
worked examples preserve stem-analysis-solution-conclusion; one top-level
exercise preserves every subpart and resource; a short activity prompt may
merge into the knowledge it elicits only with an explicit disposition and the
marker preserved. A post-knowledge reflection question is the
exception: it remains an independent scenario-semantic atom, because it can
connect learned knowledge to later or extra-text inquiry. Topic grouping does
not erase atomic boundaries: independently reusable methods such as enumeration
and description remain separate knowledge atoms under their shared organizer.
Likewise, adjacent defined concepts with distinct dependency roles remain
separate; a prerequisite context such as a universal set is not merged into the
dependent operation such as complement. Inline practice questions attach to
the knowledge topic they exercise, while only the terminal formal exercise set
remains a direct section-level organizer.

The relation audit may return evidence-bound boundary feedback. Run
`prepare-feedback` and `finalize-feedback`; do not edit ranges in place. At most
two automatic cycles are permitted. Legacy `llm-two-pass` keeps the focused
post-partition role audit described above.
