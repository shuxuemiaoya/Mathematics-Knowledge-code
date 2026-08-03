# Lesson-Flow Manifest Contract

Create `lesson-flow-manifest.json` after the split-manifest draft and before
physical splitting. It records the reviewed teaching flow of every numbered
textbook lesson and numbered in-lesson subsection, whether or not that heading
appears as an independent printed-TOC entry.

When the profile freezes a same-book reference, the input split manifest must
already contain its passed, reviewer-confirmed semantic adoption with matching
reference and proposal-report digests. Planning and validation reject an older
split created before that reference was bound.

Generate the draft:

```powershell
python scripts\lesson_flow_manifest.py plan `
  "<formatted_markdown>" "<split_manifest>" "<profile>" `
  "<lesson_flow_manifest>"
```

The draft is intentionally `review_required`. Read each complete lesson, adjust
split ranges first, then classify every source line into contiguous ordered
blocks. Set the manifest and every lesson to passed only after review.
Use each lesson's `draft_findings` first: the planner reports missing opening
previews and retained ranges above the configured size boundary before review.
Before passing, either remove a finding after correcting its boundary or record
the reviewed resolution with `resolved: true`; unresolved findings are
blocking.

The first block of every numbered lesson or subsection must be
`entry-context`. It contains the heading and a meaningful opening preview;
`entry-context` cannot appear again later in that lesson.

## Logical roles

- `entry-context`: lesson heading plus its opening preview;
- `context`: situation, motivation, prior-knowledge activation;
- `question`: a task or question posed to the learner;
- `analysis`: exploration, reasoning, derivation, or response;
- `exposition`: a bounded explanatory teaching block that remains on the
  lesson page in source order and is rendered as ordinary Markdown;
- `topic`: an independently reusable teaching arc moved to a knowledge or
  concept child;
- `worked-example`: one complete worked example retained on the lesson entry;
- `representative-example`: one deliberate worked-example anchor retained on
  the lesson entry;
- `transition`: verbatim bridge or summary that connects adjacent topics;
- `practice`: ordinary lesson practice retained locally or routed to an
  exercise child;
- `navigation`: an explicit reading-path block retained on the lesson entry.
- `section-heading`: a reviewed navigation-only numbered subsection heading
  retained on the lesson entry and promoted from H4-H6 to H3.

Do not use `exposition` as a generic catch-all. It is only for coherent
explanation that genuinely belongs on the lesson page. If a range contains
several functions, split it into smaller contiguous blocks without reordering
source text.

Functional headings or standalone labels (`观察`, `思考`, `探究`, and similar),
exposition or formal-definition cues (`可以发现`, `一般地`, and equivalent
definition sentences), every worked-example label, and every practice heading
are hard boundaries. The planner splits retained ranges at these lines. A
reviewer may refine a boundary but may not merge a block across the next hard
boundary. This prevents situation callouts from swallowing definitions and
prevents later examples or lesson practice from becoming part of an earlier
question or solution.

## Ownership

Use `retain-parent` for `entry-context`, `context`, `question`, `analysis`,
`exposition`, `worked-example`, `representative-example`, `transition`, and
`navigation`. A `representative-example` must set
`representative_anchor: true`; an ordinary `worked-example` keeps it false.
Every worked example occupies its own block.

Use `move-child` for `topic`; its range must exactly equal a direct knowledge
or concept child range. A moved `practice` block must exactly equal a direct
exercise child range.

Every direct child appears exactly once. Every lesson source line appears
exactly once across its blocks. Context and transitions cannot be swallowed by
a child range.

## Quality gate

Each lesson must record:

- `reviewed_entire_lesson: true`;
- a specific reason and confidence at or above the profile threshold;
- all six checks as `passed` or, when genuinely absent, `not_applicable`;
- `source_order_preserved` and `complete_source_coverage` as `passed`.

When an introduction, transition, topic, or practice role is present, its
matching preservation/routing check must be `passed`; it cannot be marked
`not_applicable`.

A lesson with child links must retain at least one substantive preview beyond
its heading. This blocks link-only entry pages such as the failed
`2.2 基本不等式` output.

A reading, history, exercise, method, tool, concept, or other non-knowledge
child is represented by its navigation link without a duplicated opening
preview. A knowledge topic may carry one reviewed `parent_preview` only when
the source provides a concise question, thought, exploration prompt, or short
introductory idea of at most 180 characters. Prefer a later concise source
question over copying earlier definitions, derivations, formulas, images, or
long exposition. The preview is one complete source line copied verbatim; it
cannot be rewritten, summarized, shortened, expanded, spliced, or assembled
from multiple source locations. If no concise prompt exists, use only the
navigation link.

The opening `entry-context` block itself must contain at least two nonblank
source lines: the heading and at least one retained preview line. Content that
belongs to the opening situation cannot be moved wholesale into the first
child merely because substantial text remains later in the lesson.

A retained non-practice/non-worked-example block cannot exceed
`decomposition.max_retained_teaching_block_nonblank_lines` (default `40`).
This prevents a large independent topic, such as the failed
`3.1.2 函数的表示法` example cluster, from remaining unreviewed in the entry
page.

`情景引入` names a structural requirement, not a literal output component.
During rendering, retain `entry-context`, unlabeled `context`, transitions,
unlabeled questions, and unlabeled analysis in their original Markdown form.
The required introduction before a new node may therefore be a question, an
idea, or an ordinary paragraph. Create a callout only when the source block
itself begins with an explicit functional label such as `思考`, `观察`,
`探究`, or `分析`, and reuse that exact label rather than synthesizing
`情景引入`, `过渡`, or `思考`. The splitter inserts a blank line between each
logical block while keeping every original source line in the same order. When
a source label becomes the callout title, render it once rather than duplicating
it in the quoted body.

Validate before splitting:

```powershell
python scripts\lesson_flow_manifest.py validate `
  "<lesson_flow_manifest>" "<formatted_markdown>" `
  "<split_manifest>" "<profile>"
```
