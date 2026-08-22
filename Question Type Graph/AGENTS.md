# Question Type Graph Agent Contract

This directory is a standalone, profile-driven supplementary-book agent. Do
not import runtime code from `Book to Obsidian Wiki Graph` and do not modify
that agent while operating here.

## Required Sequence

```text
freeze typed sources
  -> deterministic preflight and immutable run record
  -> forced MinerU OCR for every PDF source
  -> page/bbox provenance index, format inventory, and reviewed adapter worksheet
  -> hierarchy segmentation
  -> functional-block and atomic-question segmentation
  -> generated-title cleanup
  -> optional authoritative answer matching
  -> reviewed supplementation for unresolved enabled answers
  -> markup-only Markdown standardization
  -> optional structural Canvas
  -> final audit
```

## Invariants

- Treat every source PDF and registered raw Markdown file as immutable.
- Run preflight before OCR or graph mutation. Resolve credentials from an
  explicit path, process environment, or deterministic profile/project-root
  search; never make launch-directory choice part of format behavior.
- Append immutable run and stage-attempt IDs with input fingerprints and
  artifact hashes. Never overwrite the history of a terminal attempt.
- Bind every reusable compiler stage fingerprint to the concrete Python
  modules that implement that stage. A resume after compiler changes must
  invalidate stale stage artifacts and rebuild descendants without adapter
  cachebuster edits.
- When one OCR row contains several leader-delimited TOC entries, inventory
  every entry with its raw column and propose source-stream and column-major
  orders. Prefer a continuous printed ordinal ledger only as a review proposal;
  a reviewer still confirms authority and reading order.
- Review a printed TOC from its first leader-delimited entry through its last
  entry across every TOC page. The hierarchy planner must reject any
  leader-delimited row before the first body anchor that is absent from the
  primary ledger. A printed answer-key entry may be omitted from the content
  hierarchy only through `primary_authority.excluded_entries` with its exact
  source line, title, concrete reason, and reviewer confirmation.
- Cross-check conventional printed numbering against hierarchy semantics. If a
  book uses `第N讲` and `N.M`, each `N.M` node must be deeper than and directly
  parented by the matching `第N讲`; a repeated `思考题` must be a child of the
  nearest preceding lecture. Never flatten these titles into sibling folders.
- When the first hierarchy level exists only to organize second-level files,
  mark every first-level entry `structural_only: true`, scope questions only to
  second-level leaf contexts, and verify that no generated Q file is owned by a
  structural parent. Persist reviewed per-leaf question counts, including zero
  counts for non-question sections, so a structurally valid but incomplete
  split cannot pass final audit.
- Build a source-provenance index from MinerU content-list artifacts. Preserve
  original Markdown line ownership through hierarchy snapshots and attach an
  exact PDF page/bbox to atomic questions whenever evidence resolves; retain
  all candidates when it does not.
- Carry the same absolute profile path and frozen source hashes through every
  structured handoff.
- Keep publisher labels, titles, page ranges, numbering rules, answer layouts,
  and output folder templates in a reviewed `format-adapter.json`, never in
  reusable compiler code.
- Treat reviewed `output_policy.generate_index` and
  `output_policy.generate_canvas` as authoritative output switches. When either
  is false, do not publish that artifact and remove only hash-matching outputs
  previously owned by its pipeline stage; final audit must reject stale root
  index notes, `.canvas` files, or Canvas manifests.
- Scope numeric question detection to reviewed question-bearing functional
  roles, contexts, or source ranges before adding source-line exclusions for
  isolated false positives.
- Create one leaf note per semantic question. Keep genuinely shared-stem or
  dependent subparts together, but split publisher packet wrappers whose
  independently stated items alternate with their own authoritative solutions.
- Treat every adapter-recognized publisher worked example or variant as an
  atomic question leaf. The compiler must globally add `重要程度: 重要`, retain
  only the stem in that leaf, move the publisher's analysis into a separate
  authoritative `<QID>A1.md` answer note, and embed it from the question. Keep
  these leaves out of external answer matching. Recognition and exact solution
  boundary syntax remain in `content.question_kind_rules` and
  `content.worked_example_solution_patterns`, never in reusable compiler
  vocabulary.
- Treat teacher-edition exercises with publisher answers printed inside each
  question span as adapter-recognized `separate-authoritative` kinds rather
  than fake non-overlapping combined-source answer regions. Only the
  `worked-example` kind receives `重要程度: 重要`; other publisher-solved kinds
  retain their reviewed numbering policy. For interleaved subpart solutions,
  use adapter-owned solution start/resume patterns. Atomize independently
  stated and independently solved packet items into separate Q/A1 pairs; keep
  only genuine shared-stem or dependent subparts in one composite leaf.
- For the single-topic teacher-edition format represented by
  `专题01 导数的运算(教师版)`, set both reviewed output switches to false: its
  topic and functional notes are the navigation surface, so it must not create
  a synthetic root `index.md` or structural Canvas.
- When such a PDF already lives inside its dedicated source-topic directory,
  use that directory itself as `graph_root`; do not append another wrapper
  directory derived from the PDF filename. Record the reviewed direct-root
  layout in adapter inventory evidence and keep entry outputs root-relative.
- Flatten question-bearing HTML tables into semantic column streams before
  segmentation. Merge streams by the next printed question number, keep each
  image or strategy with its column record, and expose adapter-matched labels
  inside cells as their own nodes; never leave orphan `<td>` or `<tr>` tags in
  an atomic question.
- Final audit must require a continuous `1..N` question-number ledger inside
  every reviewed answer context. Gaps, duplicates, and reordered numbers are
  blocking errors rather than warnings.
- Treat every authoritative `unmatched-answer` review record as a blocking
  `answer-without-question` error. Reviewer confirmation cannot waive it,
  because it may be the only evidence that a continuous-looking question
  ledger lost its entire tail.
- Preserve a publisher/OCR numbering reset in the immutable source body, but
  use matching reviewed question/answer number-shift ranges when semantic
  identity must remain continuous.
- If visual PDF review proves that conversion omitted a complete question,
  recover it only through a page-provenanced, reviewer-confirmed virtual
  question entry anchored to the immutable hierarchy corpus; never reconstruct
  a missing stem from the answer alone.
- If visual PDF review proves that conversion omitted a fragment inside an
  otherwise preserved question, use an adapter-owned
  `recovered_question_fragments` insertion bound to the hierarchy snapshot's
  exact raw line/column, before/after position, drift anchor, PDF page/bbox, and
  reviewer confirmation. It may only insert PDF-visible text into the semantic
  virtual copy; it must never edit, replace, or delete frozen OCR text.
- If visual PDF review proves that OCR joined the end of one solved item and
  the next question header on one physical line, split only the semantic copy
  through adapter-owned `reviewed_semantic_line_splits` with exact
  hierarchy-local Unicode columns, drift anchor, PDF page/bbox, reason, and
  reviewer confirmation. Never edit the frozen raw line.
- Also use a reviewed semantic line split when OCR joins a worked-example stem
  and its publisher `分析/解答` on one line. Before delivery, scan every generated
  worked-example question source block; any remaining publisher solution marker
  in the Q body is a blocking boundary defect, even if an A1 note exists.
- Preserve source text, formulas, images, tables, numbering, and order. Add
  Markdown structure and navigation only.
- Keep a chapter's explanatory introduction in the chapter note unless the
  reviewed structure explicitly makes it an independent navigational node.
  Move publisher-labeled chapter metadata into YAML frontmatter only through
  adapter-declared `content.note_properties` rules with named `value` groups;
  do not leave duplicate metadata lines in the rendered body.
- After content segmentation, clean every generated title and corresponding
  filename by preserving only Unicode letters, digits, and `_` and replacing
  every other character (including whitespace, full-width punctuation such as
  `：`, ASCII punctuation, symbols, and emoji) with `_`. Never rewrite frozen
  OCR text or question bodies during title cleanup.
- Never accept fuzzy answer similarity by itself. Route ambiguous or missing
  matches to a blocking review queue.
- Assign each answer block to at most one question and each question to at most
  one answer. A re-claimed candidate routes to the blocking review queue,
  never to a second match (the final audit hard-errors on
  `answer-owned-more-than-once`).
- Answer patterns must accept real "N.M…" answers (e.g. `8.2或-2或…`,
  `5.2 【解析】`) while rejecting section-number phantoms (`1.3 空间向量…`).
  Verify the pattern set against every `^\d+[.．、]\d` line in the answer raw,
  and keep the same patterns in the adapter and any build-script event scanner.
- Answer application is declarative: automatically remove owned answer notes
  and embeds when a question flips matched → unmatched, and record removals in
  `answer-application-report.json`.
- Store reviewer-authored solutions that must survive pipeline regeneration in
  staging `reviewed-supplement-overrides.json`, keyed by `question_id` and
  `question_body_sha256`. Regenerated supplement plans must reuse only entries
  whose body digest still matches, and the coordinator should reapply those
  reviewed solutions without another manual copy/paste cycle.
- Keep atomic questions off the structural Canvas.
- Leave knowledge-point linking disabled until a later explicit stage.
- Keep staging outside published vault roots and create no backup directories.
- Use adapter-configured `answers.callout_title` for answer callouts rather than hardcoding publisher names.
- When OCR drops a choice answer header but preserves an explicit authoritative conclusion such as `故选:D`, recover `D` into a separate `**【答案】** D` field. Never infer an option from isolated capital letters or mathematical prose. Choice-question audit must fail on a missing answer field, and authoritative notes must agree with the source conclusion.
- Every generated solution note must use a collapsible outer
  `> [!faq]- <title>` and three collapsible nested callouts:
  `> > [!success]- **【答案】**`, `> > [!note]- **【分析】**`, and
  `> > [!note]- **【解析】**`. All nested content lines must retain the `> >`
  prefix. Recover a bounded publisher-stated result that appears before
  an explicit `解析:`/`【解析】` marker. When a non-choice problem has no safely
  separable short result, write `**【答案】** 详见解析`; never use that fallback
  for a choice problem, whose exact option remains mandatory.
- Ensure question and answer regex patterns use a single named group (e.g. `^【?(?P<number>\d+)[】.．、]?\s*`) to prevent Python regex duplicate group name errors.
- Bound ordinary question `end_line` before any internal markdown heading
  (`^\s*#{1,6}\s+\S`) in `plan_note()`. A reviewed worked-example kind may set
  `preserve_internal_headings: true` so publisher `分析/解析/评注` headings stay
  inside the atomic leaf.
- Automatically deduplicate adjacent OCR duplicate answer header lines for the same `(context, number)` in `answers.py`.
- Allocate question sequence numbers through the locked vault registry
  `.question-type-graph/question-id-registry.json`. Seed a new registry from
  the vault and any adapter-configured central question repository.
- Pre-split inline answer headers (e.g. `... 故选：B 【5】A`) in `parse_answer_blocks()` before scanning so OCR lines containing concatenated answer headers are isolated into separate answer blocks.
- Update `format_answer_callout()` option extraction regex (`^【?\d+】?[\.、\s]*([A-Z]+)`) to accept bracketed question numbers (`【N】A`) as well as plain numbers (`N. A`).
- Validate and align `answers.contexts` `start_line` boundaries against exact section heading positions in `answers.raw.md` during format inventory to prevent cross-section answer block misattribution and duplicate-number collisions.
- Preserve `## 知识导学` knowledge guide sections and all nested subheadings (`## 一. ...`, `## 1. ...`), formulas, diagram asset paths, and comparison tables within primary section notes without splitting them into separate question notes.
- Enforce zero-tolerance validation for questions lacking explanations during
  graph audit. External-answer exercises MUST embed a valid solution callout
  note; publisher worked examples MUST embed a separate, provenance-marked
  authoritative solution note and MUST NOT retain that solution inside the
  question-source block. Any failure is blocking and reports the exact cause.
- Treat this file and `skills/question-type-graph/references/pipeline-contract.md`
  as the canonical policy. Knowledge linking remains deferred; component skill
  documentation must not activate it implicitly.

## Canonical Skills

The canonical skills live under `skills/`. Install or link that directory using
the host platform's Codex skill location; do not maintain copied duplicates.
