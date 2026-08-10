---
name: book-to-obsidian-wiki-graph
description: Coordinate the standalone conversion of a PDF or long Markdown book into a validated Obsidian Wiki-style knowledge graph through book-specific forced-OCR conversion, TOC-authoritative heading formatting, immediate TOC-based splitting with parent links, concept extraction, Markdown standardization, audits, and an optional logic canvas. Use for complete conversions, resumes, or audits; never route these stages through MathOS Agent.
---

# Book To Obsidian Wiki Graph

Coordinate component skills and enforce artifact gates. Do not absorb stage-specific implementation.

## Read

- Read `references/pipeline-contract.md` for stage ownership and handoffs.
- Read `references/runtime-contract.md` before starting or resuming a run.
- Read `references/example-architecture.md` when comparing with the 人教版高中必修第一册 example.
- Load each component skill only when entering its stage.

## Runtime

After intake passes, initialize `scripts/pipeline_runtime.py` with the frozen
profile. Wrap every component invocation with `begin` and `complete`; use
`fail` on an unsuccessful stage. Run `resume` before continuing an interrupted
run. The runtime validates artifact schemas, profile/source identity, recorded
hashes, unresolved review items, stage order, and output drift.

Runtime state is recovery data for one conversion run only. Never search another
book or an older run for reusable conversion output, and never add a cross-book
cache.

For repeated tests of the exact same frozen source, honor the optional
`book-graph-test-options.json` described in `references/runtime-contract.md`.
When `preserve_stage_artifacts` is enabled, let the runtime checkpoint every
completed stage and use `restore-checkpoint` to resume from one of those
identity-bound snapshots. When disabled or absent, keep the existing
final-result-only behavior. Never treat test checkpoints as cross-book reuse.

## Route

1. Invoke `book-graph-intake` to freeze source identity and create `book-profile.json`.
   If the user names an approved corpus, freeze its path, digest, and scope in
   the profile before any conversion work.
   If a same-book reference is supplied only after splitting, do not append it
   to a completed run and continue downstream. Rebind intake identity, invalidate
   the old split and every dependent artifact, then resume from the deterministic
   split draft so reference semantic review still precedes lesson flow.
   For directory or series builds with Canvas enabled, discover the nearest
   completed same-publisher, same-series sibling Canvas before creating each
   profile and freeze it as `canvas.style_reference`. Prefer an explicitly
   named reference. If none exists, let the first completed volume establish
   the series baseline for later volumes.
2. For PDF input, invoke `book-pdf-to-markdown`; for Markdown input, register that immutable source directly.
3. Invoke `book-toc-formatting` to build the TOC manifest, align all TOC headings to H1-H3, and demote every other heading below H3.
4. Immediately invoke `book-toc-splitting` after a passed formatting report.
   When `reference.scope` is `same-book-content-and-style`, require the
   identity-bound reference semantic proposal and reviewer-confirmed adoption
   before lesson-flow planning. Do not proceed with a manually reviewed
   split manifest that lacks `semantic_review.reference.status: passed`.
   Require a passed `lesson-flow-manifest.json` before physical textbook
   splitting.
5. Invoke `book-graph-audit --stage split`; stop on coverage, link, asset, or identity failures.
6. Invoke `book-graph-concepts`, then require `book-graph-audit --stage concepts`.
7. Invoke `book-graph-markdown`, then require `book-graph-audit --stage formatting`.
8. Invoke `book-graph-audit --stage pre-canvas` and require a passed report.
9. Invoke `book-graph-canvas` only when enabled. For a same-book reference
   with a canvas—or when the user supplies one during comparison—bind that
   reference into the profile, plan from the reviewed layout first, review
   every skipped node/edge, then augment it with resolving current-only notes
   instead of replacing it with a chapter-only grid. Reject a per-book builder
   containing literal chapter ranges, fixed concept names, or hand-authored
   relation lists. When `canvas.style_reference` exists, run the style
   comparator, revise and rebuild until `canvas-style-report.status: passed`,
   then provide that report to runtime completion. Canonical Markdown links
   and valid topology override defects inherited from a legacy reference.
10. Invoke `book-graph-metadata` to derive, inject, and validate Frontmatter metadata properties for all notes in the vault, producing `metadata-report.json`.
11. Invoke `book-graph-audit --stage final` for the final gate.
    A configured reference also requires a passed, profile-bound
    `reference-parity-report`; the runtime must not complete without it.

Never invoke `mathos-pdf-to-md`, `mathos-formatting`, or `mathos-segmentation`.

## Cross-Stage Invariants

- Set default `vault_root` to `/Users/oven/Documents/ovenmathmap`.
- Preserve the relative input directory structure when deriving `book_root` under `vault_root` (e.g. `<vault_root>/<input_relative_path>/<book_folder>`).
- Preserve source meaning, complete blocks, and order.
- Carry one profile path and frozen source digest through every handoff.
- Carry immediate Markdown input/output hashes through formatting and splitting.
- Always use `知识点`, `概念`, and `习题` for textbooks. Add only
  source-supported profile roles among `趣味阅读`, `数学历史`, `思维或方法`, and
  `工具`; never create an empty auxiliary directory.
- Record LLM-selected categories in the profile before splitting other books.
- Retain a link in the parent at every moved child block's original position.
- Give repeated generic chapter and section children contextual titles and filenames:
  `小结` → `<章名> 小结`, `复习参考题` → `<章名> 复习参考题`, and `习题` → `习题<编号> <对应小节标题>` (e.g., `习题10.1 随机事件与概率`).
- Do not accept TOC-only textbook splitting. Require the complete H4-H6
  semantic-review ledger with confidence, numbered subsection notes, and
  section-exercise notes. Retain unnumbered non-TOC blocks unless a reviewed
  decision confirms a complete independent teaching arc.
- A same-book reference is active split evidence, not a final-report-only
  comparator. Run `propose_reference_semantic_review.py`, resolve every
  candidate or ambiguity against the frozen source, and run
  `adopt_reference_semantic_review.py --reviewer-confirmed` before generating
  lesson flow. When ambiguities exist, pass an exhaustive, proposal-digest-bound
  `--review-decisions` file with an `accept`, `revise`, or `reject` decision and
  specific reason for each item. The adopted split manifest must carry the
  frozen reference path/digest, proposal-report digest, and decision-report
  digest.
- Treat a newly supplied or changed same-book reference as split-input drift.
  Never let content parity, Markdown audit, or canvas reconstruction bless a
  split manifest created before that reference was frozen.
- Do not equate the H4-H6 ledger with content review. For every long knowledge
  node emitted by the split planner, including numbered H4-H6 subsections,
  inspect the complete body,
  resolve `semantic_review.sections`, and add reviewed
  `semantic_review.ranges` for independent teaching arcs that begin in
  ordinary paragraphs rather than headings. The splitting stage must remain
  blocked while any section says `review_required`.
- For every numbered textbook lesson and numbered in-lesson subsection,
  require a complete source-ordered lesson-flow review and resolve its
  automatic draft findings. Keep `情景引入`, motivation, and transitions in
  the lesson entry; move independent topics to children; retain ordinary
  practice or route it to exercises; give every retained worked example an
  independent logical block and optionally identify one representative
  anchor. Treat functional labels/headings, exposition or definition cues,
  worked-example labels, and practice headings as hard boundaries. Block any
  reviewed block that crosses the next boundary, as well as link-only lesson
  entries and oversized retained teaching blocks.
- Treat `情景引入` in the preceding rule as a structural requirement, not a
  generated title or callout. Every new node link must be introduced by a
  complete source-derived question, idea, or ordinary paragraph; preserve
  unlabeled prose as prose. For every topic child, use its own leading source
  range as the reviewed `parent_preview` and keep that range in the child. Do
  not let an unrelated or generic lesson-opening paragraph satisfy the link.
- Keep H1-H3 immutable after TOC formatting.
- Keep hyperlink and image destinations immutable during post-split standardization.
- Require Markdown standardization to turn residual functional headings,
  contextual problem introductions, and worked examples into complete quoted
  callout containers. Example analysis and solutions must remain nested inside
  the owning example callout before pre-audit. Close question and situation
  callouts before a following exposition or formal-definition cue. Convert an
  unlabeled H4-H6 sentence/question display artifact to an ordinary paragraph
  rather than inventing a functional callout title.
- Require the formatting audit to reconstruct callout ownership and reject
  swallowed functional headings, duplicated source labels, formal definitions
  inside situation callouts, examples inside non-example callouts, and
  practice inside any callout.
- Require Markdown standardization and every progressive audit to consume the
  same passed lesson-flow manifest; do not let post-split formatting infer a
  different teaching hierarchy from keywords.
- Send low-confidence, ambiguous, unresolved, or conflicting decisions to a review queue; block the owning stage until every item is resolved.
- Parallelize only independent note-level work from one frozen workplan. Give each note and output path exactly one owner, then validate every result before merging.
- Stop on failed or mismatched artifacts.

## Completion

Report source/profile identity, conversion result, TOC matches and demotions,
split/category/parent-link counts, coverage, concepts, formatting validation,
links/assets, optional Canvas counts and style metrics, audit results, and
source integrity.

Also report per-stage duration, attempts, failures, and review counts from
`pipeline-state.json`. Completion requires the final applicable audit to report
`status: passed`.

When `canvas.style_reference` is configured, completion additionally requires
an identity-bound `canvas-style-report.json` with `status: passed`. A
`style_review_required` report means the Canvas must be replanned; it is not a
warning that may be accepted at handoff.

When the user supplies an intended/reference corpus, completion also requires a
normalized reference-parity review. Compare architecture rather than raw book
size:

- H1/H2/H3 entry-heading grammar and malformed first lines;
- bullet navigation placement and configured link syntax;
- chapter-qualified summary/review titles;
- category-local flat asset depth;
- concept-note title/source/definition structure;
- residual OCR ornament/running-header headings;
- knowledge and exercise counts per chapter, not total counts.

When the reference is the same book and edition, also perform content parity:

- compare same/renamed/aggregated note bodies after removing link destinations,
  complete heading lines, image destinations, and callout quoting;
- compare the source-ordered functional-block topology of every common note,
  including callout type, functional label, quote depth, and parent callout;
  a same-path topology mismatch is blocking even when normalized body text is
  equivalent;
- rank same-path note differences by bidirectional normalized-body containment,
  including concept-note bodies, and block `content_divergent` pairs instead
  of reporting only their count;
- distinguish an empty reference body with additional current content from a
  current-empty/reference-nonempty loss; only the latter is blocking;
- list reference teaching notes whose content is still aggregated into a
  larger current lesson;
- compare formal-concept title coverage and explain every missing term;
- distinguish preserved-but-differently-split content from genuinely absent
  text;
- block parity when a long current lesson combines multiple independently
  reusable teaching arcs represented separately by the intended corpus.

Generate the content evidence before writing the final parity report:

```powershell
python .\skills\book-to-obsidian-wiki-graph\scripts\compare_reference_content.py `
  "<current_book_root>" "<reference_book_root>" `
  --profile "<staging>\book-profile.json" `
  --output "<staging>\reference-content-parity-report.json"
```

Treat `status: content_review_required` as a blocking decomposition finding,
not as a successful comparison.
When every reported blocker has been checked against the frozen source,
concept-candidate rejection record, and intended corpus, write an identity-bound
review-decisions JSON with exact `reference_notes`, `common_notes`, and
`missing_concepts` keys. Each accepted item must use
`decision: accept-current` and a specific reason. Rerun with
`--review-decisions`; unlisted blockers remain blocking. Do not use a broad
waiver or change the reference scope merely to obtain `status: passed`.

For a different-book `style-only` reference, content totals and titles are not
compared. The report still blocks legacy/discontinuous callouts, worked-example
stems that were not compacted to the approved form, and explicit reasoning
labels flattened at the wrong quote depth. The ordinary formatting audit
continues to enforce all canonical Markdown and source-completeness rules.

Record the comparison in staging and explicitly separate implementation
differences from source-supported differences such as chapter count, printed
side material, enabled concepts, and canvas policy. Never declare parity from
link resolution and file counts alone.
