# Format Adapter

Store one reviewed adapter in staging. Reusable code consumes semantic roles;
literal publisher labels and page assumptions live here.
The executable v1 contract is also published as
[`format-adapter.schema.json`](format-adapter.schema.json); runtime validation
adds regex compilation, named-group, uniqueness, authority, and profile-mode checks.

Minimum shape:

```json
{
  "schema_version": 1,
  "status": "passed",
  "reviewer_confirmed": true,
  "profile": "C:/absolute/question-type-profile.json",
  "hierarchy": {
    "source_role": "questions",
    "root_output": "index.md",
    "primary_authority": {
      "status": "passed",
      "reviewer_confirmed": true,
      "start_line": 10,
      "end_line": 40,
      "entries": [
        {"key": "chapter-1", "title": "authoritative source title", "level": 1, "source_line": 12}
      ]
    },
    "entries": [
      {
        "key": "chapter-1",
        "output": "chapter-1/chapter-1.md",
        "body_anchor": {
          "kind": "reviewed-boundary",
          "start_line": 100,
          "evidence": "reviewed first body block for this TOC entry",
          "reviewer_confirmed": true
        },
        "emit_title": true,
        "answer_context": "chapter-1"
      }
    ]
  },
  "content": {
    "unknown_label_policy": "review",
    "question_folder": "questions",
    "question_repository_root": "/optional/central/question/repository",
    "question_title_template": "Question {number}",
    "question_patterns": ["^(?P<number>\\d+)[.．、]\\s*"],
    "inline_question_patterns": ["(?<!\\d)(?P<number>\\d+)[.．、]\\s*"],
    "roles": [
      {"role": "training-band", "depth": 0, "pattern": "source-specific regex", "answer_context": true},
      {"role": "question-type", "depth": 1, "pattern": "source-specific regex"},
      {"role": "knowledge-item", "depth": 1, "pattern": "source-specific regex", "heading_only": true}
    ]
  },
  "answers": {
    "source_role": "answers",
    "callout_title": "全练一本通解析",
    "contexts": [{"key": "chapter-1", "pattern": "source-specific regex", "start_line": 200, "anchor_text": "## source heading"}],
    "answer_patterns": ["^(?P<number>\\d+)[.．、]\\s*"],
    "inline_answer_patterns": ["(?<!\\d)(?P<number>\\d+)[.．、]\\s*"],
    "implicit_answers": [
      {"context": "chapter-1", "number": "1", "start_line": 205, "anchor_text": "reviewed first answer body line"}
    ],
    "ignore_ranges": []
  }
}
```

`question_patterns` and `answer_patterns` recognize a virtual line at its
start. Their optional `inline_*_patterns` counterparts identify additional
records concatenated onto one OCR line. If the inline field is absent, the
corresponding ordinary patterns are reused; set an empty inline list to disable
same-line splitting. Every pattern requires a named `number` group. The shared
virtual-line parser preserves raw line, raw column, and subline provenance.
If OCR changes a printed question number while preserving the question body,
record the reviewed correction in `content.question_number_overrides` using
the hierarchy context, hierarchy-note raw line, optional one-based raw column,
correct number, and a drift anchor. The original OCR text remains preserved in
the atomic note while matching uses the corrected identity.

For a content-derived no-TOC hierarchy, replace `primary_authority` with an
explicit `no_toc_authority` object containing `status: passed`,
`reviewer_confirmed: true`, and a non-empty evidence-based `reason`; omission
of both authority forms is an error. Record the reviewed entries and exact
start lines. Training-band entries nested below a
TOC node must be marked `supplemental: true`. Use `structural_only: true` when
a parent has no independent body range and shares its first child's anchor.
For combined inputs, set the answer role to `combined` and freeze a
non-overlapping `answers.region`. Save a series preset only after removing
paths, titles, line ranges, and content-specific regex captures.

A path-free series preset may provide `inventory.role_hints`, for example
`[{"role": "knowledge_guide", "pattern": "series-specific label regex"}]`.
Inventory applies only those reviewed hints; without them it reports repeated
literals with `proposed_role: null` instead of guessing from a built-in
publisher vocabulary. Adapter review remains mandatory in either case.

Set `answer_context: true` on a repeated functional role when question numbers
restart inside those blocks. Its stable context is
`{note_key}:{role}:{occurrence}` by default; use `answer_context_template` only
when the answer-source context keys require another reviewed convention.
Generated paths default to a conservative 220-character budget and fall back
to deterministic `_compact` names without changing visible note titles.
Set `heading_only: true` when a role regex could also match ordinary body text
such as numbered subparts; this prevents a subpart from truncating its owning
top-level question or functional node.

If a missing OCR training-band label causes exercise roles to nest beneath a
theory role, configure `content.detached_role_folders`, for example
`[{"from_ancestor_role":"knowledge_guide","roles":["basic-point","question-type"],"folder":"Questions"}]`.
The exercise roots then become siblings of the theory node and are written
under the reviewed folder without hardcoding publisher labels in the compiler.

`answers.contexts[].start_line` is always a raw Markdown line number, even when
an OCR line contains multiple inline answer headers. Add `anchor_text` or
`anchor_pattern` when freezing a fixed boundary so drift fails before matching.
When OCR preserves a publisher solution but drops only its printed answer
header, record it in `answers.implicit_answers` with the exact context, number,
raw `start_line`, and an `anchor_text` or `anchor_pattern`. This is a reviewed
recovery of authoritative content, not a supplemental solution.
For an inline header omission or OCR-misread number, also record the one-based
`raw_column` of the affected virtual line. Omitting `raw_column` means column 1
and preserves the ordinary whole-line recovery behavior.
When the publisher block unambiguously proves a choice but OCR drops both the
printed answer and the concluding `故选`, freeze the reviewer-confirmed option in
`answers.choice_answer_overrides` with context, number, answer start line, and
a drift anchor. This is a source-backed rendering correction; never derive it
from isolated capital letters or use it to resolve uncertain mathematics.
When an authoritative non-choice solution contains an unambiguous result but
its OCR layout prevents safe automatic prefix extraction, freeze that exact
result in `answers.short_answer_overrides` with context, number, answer start
line, and a drift anchor. Use this only for source-backed results; otherwise
retain `详见解析` rather than solving or guessing during answer rendering.
Set `content.question_repository_root` only when a new vault registry must seed
above an additional central QID repository; ongoing allocation uses the locked
vault registry.

For books with mixed theory sections, map the source-specific labels to a
semantic role such as `knowledge_guide` in `content.roles`; the segmentation
engine then extracts lightweight Functional Nodes without needing those label
literals in reusable code.
