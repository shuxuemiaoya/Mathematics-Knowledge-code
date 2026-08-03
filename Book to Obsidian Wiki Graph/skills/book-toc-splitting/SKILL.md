---
name: book-toc-splitting
description: Split TOC-formatted book Markdown into categorized Obsidian notes using the TOC as the parent hierarchy and reviewed nested source ranges, while replacing every moved child block with a resolving Markdown link at the same position in its parent. Use immediately after book-toc-formatting; for textbooks enforce the three core categories plus only source-supported profile-recorded side-material roles.
---

# Book TOC Splitting

Own physical note boundaries, category placement, parent links, and coverage. Do not extract additional formal concepts or standardize callouts and typography.

## Plan

Read `references/split-manifest.md` and create `split-manifest.json`. For a
textbook, also read `references/lesson-flow-manifest.md`.

For a textbook, first generate the deterministic draft:

```powershell
python .\skills\book-toc-splitting\scripts\plan_split_manifest.py `
  "<staging>\<book>.toc-formatted.md" `
  "<staging>\toc-manifest.json" `
  "<staging>\book-profile.json" `
  "<staging>\split-manifest.json"
```

Review the `review_required` draft before splitting. The planner builds the TOC
tree, inventories every H4-H6 heading, splits mandatory numbered subsections and
section exercises, retains other headings by default, and creates a blocking
content-review entry for every long generated knowledge node, including
numbered H4-H6 subsections.

When the profile freezes a `same-book-content-and-style` reference, generate
the reference range evidence immediately after this draft:

```powershell
python .\skills\book-toc-splitting\scripts\propose_reference_semantic_review.py `
  "<formatted_markdown>" "<split_manifest>" "<reference_root>" `
  --output "<staging>\reference-semantic-proposals.json"
```

Read every proposal and ambiguity against the complete frozen source. After
confirming the exact ranges, write one decision for every ambiguous proposal
(`accept`, `revise`, or `reject`, each with a specific reason) to
`reference-ambiguity-decisions.json`. Bind that file to the proposal with
`proposal_report_sha256`, then adopt the review before lesson-flow planning:

```powershell
python .\skills\book-toc-splitting\scripts\adopt_reference_semantic_review.py `
  "<formatted_markdown>" "<split_manifest>" `
  "<staging>\reference-semantic-proposals.json" `
  "<staging>\split-manifest.reference-reviewed.json" `
  --review-decisions "<staging>\reference-ambiguity-decisions.json" `
  --reviewer-confirmed
```

Omit `--review-decisions` only when the proposal report contains zero
ambiguous items. Never silently drop an ambiguous suggestion.

Continue only with the adopted manifest. It must contain
`semantic_review.reference` bound to the configured reference path and digest,
the proposal-report digest, complete ambiguity counts, the decision-report
digest when ambiguities exist, and `reviewer_confirmed: true`. The splitter
rejects a same-book profile without this evidence.

After the split-manifest draft, generate `lesson-flow-manifest.json`:

```powershell
python .\skills\book-toc-splitting\scripts\lesson_flow_manifest.py plan `
  "<formatted_markdown>" "<split_manifest>" "<profile>" `
  "<lesson_flow_manifest>"
```

Review every numbered lesson and numbered in-lesson subsection as one ordered
teaching sequence. Resolve every `draft_findings` item and adjust child ranges
before marking the lesson flow passed. Preserve situation introductions and
transitions in the entry page, route independent topics to children, keep
ordinary practice locally or in an exercise child, and retain a worked example
in its own `worked-example` block; optionally mark one
`representative-example` as the representative anchor. The deterministic draft
must split retained ranges at every functional heading or label, exposition or
formal-definition cue, worked-example label, and practice heading. Validation
must reject a reviewed block that crosses any such boundary. Reject a link-only
lesson entry and an oversized retained teaching block.

After same-edition semantic ranges are adopted, run
`scripts/flatten_navigation_containers.py`. A numbered subsection that has no
independent body after one or more finer topic children move out is a structural
container, not another note. Retain and promote its heading on the lesson page,
promote its children to direct lesson children, and attach a complete
source-derived parent preview wherever the preceding retained context is
missing or incomplete.

Generate or validate lesson flow only after this adoption. Both lesson-flow
commands reject a same-book profile when the split manifest lacks a passed,
reviewer-confirmed reference review, matching reference identity, or the exact
proposal-report digest. If the reference was added after an older split, discard
that split and its downstream artifacts and restart from the split draft.

- Use every TOC entry exactly once as a parent or leaf note.
- Retain unnumbered non-TOC ranges in their nearest TOC note by default. Split
  one only when it forms a complete, independently reusable teaching arc.
- Resolve every `semantic_review.sections` item. Read the complete section,
  choose `split` or `retain`, give a specific reason and confidence, and set
  `reviewed_entire_section: true`. Never leave `decision: review_required`.
- A semantic arc may begin in ordinary prose without a heading. Add it as a
  child node plus a matching `semantic_review.ranges` entry with exact line
  bounds, title, confidence, reason, and
  `independent_teaching_arc: true`. The splitter will synthesize its H3 entry
  heading without rewriting the source body.
- For a same-edition reference proposal, require both content containment and
  `matched_reference_ratio >= 0.85`. A strong match to only the beginning of a
  longer reference note remains ambiguous and cannot justify a complete
  high-confidence range.
- Inventory every demoted H4-H6 content heading in
  `semantic_review.headings`; every decision needs confidence. Mark a split
  with a `node_key`, specific independence reason, and
  `independent_teaching_arc: true`; mark a retain with a specific reason.
- Split a numbered textbook subsection such as `6.1.1` into `knowledge` unless
  reviewed finer children leave it navigation-only. In that case retain it as
  a promoted H3 structural container on the lesson page. Always split section
  exercises such as `习题6.1` into `exercise`.
- A direct `knowledge` topic child may have one reviewed `parent_preview` only
  when the source supplies a concise question, thought, exploration prompt, or
  short introductory idea (at most 180 characters). Prefer a source question
  even when it occurs after preliminary exposition. Copy one complete source
  line verbatim: do not add, delete, rewrite, summarize, splice, or combine
  words or sentences. Never duplicate a
  definition, derivation, formula sequence, image cluster, worked solution, or
  long explanatory passage merely to introduce a link. When no concise prompt
  exists, render only the child link. `情景引入` is a structural concept, never
  a synthesized title, mandatory callout, or miniature summary of the child.
  Preserve ordinary
  paragraphs as ordinary Markdown. Create a callout only when the source itself
  provides a functional label such as `思考`, `观察`, or `探究`; classify formal
  definitions as exposition and example stems as worked examples.
- Keep ranges nested or disjoint; never overlap siblings.
- Preserve source order and complete source blocks.
- Do not merge adjacent functional blocks during review. In particular, close
  situation context before `观察/思考`, close a question before a worked
  example, start every example separately, and keep `练习` outside every
  question/example block.
- Leave introductions, transitions, and ordinary lesson practice in their parent unless intentionally moved.
- Give repeated generic chapter children contextual titles and filenames:
  use `<章名> 小结` for `小结`, and append the chapter name to a generic
  `复习参考题` title. Do not emit ambiguous `第1章 小结.md` placeholders.
- Keep book-wide standalone indexes and glossaries as child nodes with category
  `root`, so they are written beside the book entry note and retain their own
  TOC heading.
- Assign confidence to each semantic split/retain decision and route low-confidence, ambiguous, unresolved, or conflicting decisions through the coordinator review queue.

For textbooks, always use:

- `knowledge` → `知识点`;
- `concept` → `概念`;
- `exercise` → `习题`.

When evidenced by the source and enabled in the profile, also use:

- `reading` → `趣味阅读`;
- `history` → `数学历史`;
- `method` → `思维或方法`;
- `tool` → `工具`.

Do not create empty auxiliary directories.

For other books, let the LLM determine useful categories and record them in the profile before splitting.

## Split

```powershell
python .\skills\book-toc-splitting\scripts\split_book_by_toc.py `
  "<staging>\<book>.toc-formatted.md" `
  "<staging>\toc-manifest.json" `
  "<staging>\split-manifest.json" `
  --profile "<staging>\book-profile.json" `
  --lesson-flow-manifest "<staging>\lesson-flow-manifest.json"
```

The splitter must:

- reject a textbook manifest that omits the semantic-review ledger or retains a numbered subsection/section exercise;
- reject a missing, unresolved, stale, non-contiguous, or logically invalid
  lesson-flow manifest;
- reject a lesson-flow block that crosses a deterministic functional boundary
  or assigns the boundary to an incompatible role;
- reject a knowledge-topic `parent_preview` that is not a concise
  source-derived question, thought, exploration prompt, or short introductory
  idea, that exceeds 180 characters, or whose rendered text is not byte-for-byte
  source text from its recorded range;
- reject a parent preview that explicitly points to an immediately following
  image/table but ends before that media cluster;
- reject a navigation-only numbered subsection emitted as an intermediate note;
- reject an unresolved long-section content review or an unreviewed headerless
  semantic range;
- reject an unreviewed low-confidence decision or an unnumbered non-TOC split
  without a specific independence reason and `independent_teaching_arc: true`;
- reject a `same-book-content-and-style` profile whose split manifest lacks
  passed, reviewer-confirmed, identity-bound reference semantic evidence;
- create one note per split node;
- replace each direct child range with a standard Markdown link in its parent at the original source position;
- render every direct-child navigation link as a bullet item, and promote the
  entry heading of every independent H4-H6 semantic note to H3;
- render reading, history, exercise, method, tool, concept, and other
  non-knowledge child links without copying their opening body into the parent;
- compute relative or vault-root targets from the profile;
- retain the parent heading, introductions, transitions, and unsplit material;
- copy referenced assets into the category-local location and materialize each output image destination according to `links.asset_mode`;
- flatten MinerU book/part namespaces to category-local `images/<basename>`
  destinations, rejecting a same-name collision when the bytes differ;
- for `vault-root` assets, write encoded `/课本/...` destinations after copying;
- write `coverage-manifest.json` in staging;
- refuse an existing output root rather than infer replacement.

The parent-link pattern must match the supplied 人教版 example: a lesson note remains an ordered reading path, while linked child bodies live in categorized files.

## Handoff

Require every TOC key and split range to be assigned, every generated target to
exist, every parent link to resolve, and all copied asset paths to resolve.
Require `book-graph-audit --stage split` to pass, then invoke
`book-graph-concepts`.
