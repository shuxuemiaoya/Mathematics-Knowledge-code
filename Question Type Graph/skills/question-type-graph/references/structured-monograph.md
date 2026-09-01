# Structured Monographs and Series

Use this protocol for multi-level mathematical monographs, repeated
`第N讲 / N.M / 思考题` structures, batches of sibling volumes, and repairs of
flattened outputs.

## 1. Classify and freeze each volume

Enumerate every source PDF, intended graph root, staging root, and existing
output before mutation. Decide per volume whether it is a structured monograph,
single-topic teacher edition, or exercise bank. Do not inherit fixed lines,
page ranges, hierarchy depth, or answer boundaries from a sibling volume.

Reuse a preset only when it contains no paths, titles, line numbers, pages, or
book-specific captures. Treat every preset result as an inventory proposal.

## 2. Build hierarchy from visual authority

Render and inspect every printed TOC page. Freeze one ledger row per printed
entry:

```text
printed entry -> source line/column -> level -> parent -> body anchor -> output
```

Preserve mixed depths. A book may have two-level chapters in one part and
three-level chapters elsewhere. Parent a repeated `思考题` under its nearest
printed lecture or section. Do not flatten entries merely because OCR headings
have equal Markdown depth.

If non-leaf notes only organize children, mark them `structural_only` and set
`question_ownership_policy: leaf-only`. Parent notes embed only direct children.

## 3. Freeze output policy

Record `generate_index` and `generate_canvas` explicitly in every reviewed
adapter when the user or series layout has selected those products. When both
are false, reject stale `index.md`, `.canvas`, and Canvas manifests.

Map the source-relative book directory to exactly one graph root. If that root
already carries the book title, write chapter folders directly below it; never
create a second same-title wrapper.

## 4. Census and atomize questions

Review every leaf and freeze a complete `leaf x question_kind` expectation
matrix, including zeroes. Census all publisher examples, variants, thought
questions, reference problems, exercises, and independently solved packet
items—not only lines matching an Arabic-number regex.

For each publisher wrapper:

- Split independent statements that each own a publisher solution into one Q
  and one A1 per item.
- Keep one composite Q/A1 only when subparts share a genuine stem or depend on
  one another.
- Separate every publisher solution from the question source block.
- Keep ordinary theory and exposition in the owning leaf note.

## 5. Resolve answers without invention

Match authoritative answers by exact identity and context. If a choice follows
unambiguously from its publisher solution but OCR omitted the printed key, use
a reviewer-confirmed choice override with source line and drift anchor.

Use per-question `answer_handling: unavailable` only after source review proves
that the publisher supplies no answer. An unavailable question owns no A1,
answer match, or supplement. Do not use this state to silence a missing or
misparsed answer.

## 6. Rebuild through the coordinator

After adapter or compiler changes, run `resume --overwrite`. Do not call
component apply functions to jump past `review_required`, and do not add
cachebuster metadata. Stage fingerprints must include the implementation
modules and rebuild affected descendants.

## 7. Accept the batch

For every volume, independently verify:

- final audit is passed with zero errors and warnings;
- hierarchy depths match the printed TOC;
- structural parents own zero questions;
- every Q originates from a leaf and is embedded exactly once in navigation;
- reviewed per-leaf/per-kind counts equal compiled counts;
- representative first, middle, and last Q/A1 notes match PDF evidence;
- no duplicate book-title directory exists;
- disabled index/Canvas artifacts are absent.

Report per-volume counts and results. A correct aggregate total cannot excuse a
failed or flattened volume.
