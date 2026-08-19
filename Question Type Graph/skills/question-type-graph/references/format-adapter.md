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
  "filename_policy": {"colon_replacement": "_"},
  "output_policy": {"generate_index": true, "generate_canvas": true},
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
    "question_scopes": [{"roles": ["training-band"]}],
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
    "recovered_answers": [
      {"context": "chapter-1", "number": "2", "body": "【2】A\n解析：PDF-visible authoritative solution", "after_line": 210, "source_page": 8, "anchor_pattern": "^reviewed damaged raw block", "reviewer_confirmed": true}
    ],
    "ignore_ranges": []
  }
}
```

`output_policy` is optional for backward compatibility and both switches
default to `true`. Set `generate_index: false` when a reviewed format should
publish its hierarchy entry notes without a synthetic `root_output` note. Set
`generate_canvas: false` when the format should not publish a structural
Canvas, even if the profile was initialized with Canvas enabled. On transition
from enabled to disabled, the coordinator removes only hash-matching outputs
owned by the relevant stage; audit rejects a stale index, `.canvas`, or
`graph-manifest.json`. Single-topic teacher editions such as
`专题01 导数的运算(教师版)` use both switches as `false`.
For this format, when the source PDF already sits in a dedicated topic
directory, bind the profile `graph_root` directly to that directory and record
the reviewed direct-root layout in `inventory_evidence.output_layout`; do not
append another PDF-title wrapper directory. Hierarchy outputs remain relative
to that graph root.

`filename_policy.colon_replacement` records the mandatory generated-path rule.
The runtime normalizes every component of `root_output` and `entries[].output`
even when the reviewed adapter contains `:` or `：`; final audit treats either
character in any generated file or directory path as a hard error.

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
If the source itself repeats or resets a printed number and every following
record therefore needs the same semantic offset, use reviewed,
source-anchored `content.question_number_shift_ranges` and matching
`answers.answer_number_shift_ranges`. Both endpoints require drift anchors;
the immutable source body retains its printed numbering.

Use `content.question_scopes` when the same numeric syntax occurs in theory,
instructions, worked examples, and exercises. Each scope may select one
`context`, several `contexts`, configured functional `roles`, and/or a local
`start_line`/`end_line` range. A numeric candidate must match at least one
scope. Prefer a role/context scope over adding book-specific exclusions to a
global regex; line ranges remain raw hierarchy-snapshot lines and therefore
require the same visual review discipline as other fixed boundaries.
If an OCR column spillover places a complete source span after a later-numbered
question, record a reviewer-confirmed `content.virtual_span_relocations` entry.
Bind its start, exclusive end, and insertion point to hierarchy-note raw
line/column coordinates and drift anchors. This changes semantic reading order
without editing the frozen corpus; the continuous question-ledger audit must
then pass.
When the PDF visibly contains a complete question that the frozen raw Markdown
omits, record a reviewer-transcribed `content.recovered_questions` entry with
its context, printed number, exact body, PDF page, insertion anchor, and
`reviewer_confirmed: true`. This is a provenance-marked virtual recovery; do
not edit the raw Markdown or invent a question from its answer.
Add `source_bbox: [x0, y0, x1, y1]` when the reviewed MinerU block is known.
Ordinary detected questions receive page/bbox provenance automatically when
the generated source-provenance index resolves their original Markdown line.

When the question exists but OCR omitted only PDF-visible text inside it, use
`content.recovered_question_fragments` instead of duplicating the whole
question. Each entry requires `context`, hierarchy-snapshot `raw_line` and
one-based `raw_column`, `position: before|after`, exact `text`, `source_page`,
optional `source_bbox`, a drift-resistant `anchor_text` or `anchor_pattern`, and
`reviewer_confirmed: true`. The coordinate identifies the existing OCR
character before or after which the fragment is inserted in the semantic
virtual copy. Fragment recovery cannot replace or delete OCR text, leaves the
frozen corpus unchanged, and is carried into question frontmatter and final
audit provenance. The compiler assigns each recovery to the resulting
`question` or `answer` span automatically: question fragments are recorded in
the Q note, while fragments inside a separated publisher solution are recorded
and audited in its A1 note. Do not encode that destination manually.

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
When the authoritative PDF visibly contains an answer block that raw Markdown
omits or corrupts beyond safe parsing, use `answers.recovered_answers` instead.
Transcribe the complete numbered answer and analysis, bind it to an exact raw
insertion anchor with `after_line`, record the PDF `source_page`, and require
`reviewer_confirmed: true`. Never use this field for an inferred or AI-authored
answer.
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

For publisher examples and variants, add `content.question_kind_rules` with
`kind: worked-example` and a reviewed header regex. Use `question_scopes.kinds`
to keep these candidates separate from ordinary exercises, and set an optional
`folder` such as the publisher's example folder. Worked-example semantics are
global: atomization, `重要程度: 重要`, a stem-only question note, a separate
authoritative `<QID>A1.md` publisher-analysis note, and exclusion from external
answer matching. Configure `worked_example_solution_patterns` for exact
publisher solution boundaries. `preserve_internal_headings: true` is permitted
only when solution headings belong to the example source span before splitting.

Teacher editions may print an authoritative answer immediately after each
exercise, or even between subparts of one top-level example. Do not register
such a PDF as `combined` when question and answer spans overlap. Register it as
`questions` and classify the solved items with
`answer_handling: separate-authoritative`. A non-worked-example kind such as
`inline-solved-exercise` gets the same standalone authoritative A1 behavior but
does not inherit `重要程度: 重要`.

Each separate-authoritative kind rule may define:

- `solution_layout: tail` for one continuous solution suffix, or
  `solution_layout: interleaved` for alternating subpart stems and solutions;
- `solution_start_patterns` for publisher answer/analysis openers;
- `solution_resume_patterns` for the next genuine subpart stem, required by
  `interleaved` and deliberately narrow enough to reject numbered derivation
  steps inside a solution;
- `authoritative_callout_title` for its A1 outer callout;
- `answer_shape: composite` when the top-level question has several subanswers
  and must not be audited as one single-choice result;
- `sequence_policy: continuous` when publisher-solved numeric exercises still
  require a continuous `1..N` ledger even though external matching is skipped.

When answer rows repeat the question number, make the ordinary question regex
exclude publisher answer labels before consuming optional whitespace. For
example, `^(?P<number>\d+)[.．、](?!\s*(?:答案|解析)\b)\s*` rejects
`1. 答案...`; placing `\s*` before the negative lookahead permits regex
backtracking and can accidentally create a duplicate question.
