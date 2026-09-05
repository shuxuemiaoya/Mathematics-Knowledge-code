---
name: question-type-graph
description: Coordinate conversion or repair of supplementary exercise books, teacher editions, structured mathematical monographs, and multi-volume series into audited Obsidian question-type graphs using reviewed hierarchy adapters, atomic question notes, exact answer matching, markup-only formatting, and optional structural Canvas. Use for new conversions, batch series work, resumes, flattened-hierarchy repairs, format inventory, or final audits across publishers and layouts.
---

# Question Type Graph

Coordinate the standalone skills and enforce profile, review, preservation, and audit gates. Keep book-specific rules in staging adapters rather than coordinator code.

## Read

- Read `references/pipeline-contract.md` before starting or resuming.
- Read `references/format-adapter.md` when inventorying an unfamiliar book.
- Read `references/structured-monograph.md` for multi-level monographs, repeated
  lecture/section/thought structures, series batches, or repairs of flattened
  outputs.
- Validate reviewed adapters against the runtime contract and
  `references/format-adapter.schema.json` before segmentation.
- Load each component skill only when entering its stage.

## Run

Initialize typed sources (naming graph folder after the PDF title and omitting any extra `vault` subfolder):

```powershell
python scripts/question_type_graph.py init `
  --source "questions=<questions.pdf>" `
  --source "answers=<answers.pdf>" `
  --title "<pdf_title>" `
  --staging-root "/Users/oven/Documents/ovenmathmap/.temp/<pdf_title>-staging" `
  --vault-root "/Users/oven/Documents/ovenmathmap" `
  --graph-root "/Users/oven/Documents/ovenmathmap/<relative_path_to_pdf_title>" `
  --format-preset "<optional_path_free_series_preset.json>" `
  --canvas --output "/Users/oven/Documents/ovenmathmap/.temp/<pdf_title>-staging/question-type-profile.json"
```

Use one `combined=<path>` source for a combined book, or only `questions=<path>` for a deliberately answerless book. Then run:

```powershell
python scripts/question_type_graph.py run "<profile>"
```

The coordinator performs deterministic preflight automatically. Run
`preflight <profile>` separately when diagnosing intake. It writes
`preflight-report.json` without secrets, resolves `.env` independently of the
launch directory, and blocks source drift, missing conversion credentials,
unowned output collisions, and insufficient working space.

The first run stops after `format-inventory.json` and creates a schema-shaped
`format-adapter.draft.json` plus `format-review-worksheet.md` until a
reviewer-confirmed `format-adapter.json`
exists. Resume with `resume`; unchanged stages are reused by input fingerprint,
while a drifted stage invalidates and rebuilds its descendants. Every invocation
and stage attempt receives an append-only ID. Inspect durable run/attempt IDs,
durations, fingerprints, and artifacts with `status`; rerun and
persist the final checks with `audit --overwrite`.

## Gates

- **Stage 0 Discovery Gate**: For unfamiliar document layouts, new publishers, or unstructured exercise banks, ALWAYS execute a sample-based syntax discovery and submit a 5-dimension schema inventory (TOC, stem/subquestion boundaries, answer layout, short answer detection, metadata extraction) with rendered preview cards (`generate_stage0_preview`) to the user for confirmation BEFORE any batch processing.
- **Pre-segmentation Continuity Gate**: Content planning (`plan_content`) MUST scan $1..N$ sequence continuity before file generation. If any gap occurs in a `continuous` sequence context, emit a blocking `question-sequence-discontinuity` review item with missing number and candidate line ranges.
- **Confidence-Tiered Answer Gate**: Extract choice and short answers with explicit confidence tiers (HIGH > MEDIUM > LOW > FALLBACK). Log low-confidence extractions for review.
- Freeze every source path, digest, role, page count, and output root.
- Force MinerU OCR for PDFs and stop on incomplete page or asset coverage.
- Build `source-provenance-index.json` from MinerU content-list blocks and carry
  raw-line ownership through hierarchy snapshots so resolvable questions record
  exact PDF page/bbox evidence.
- Require a reviewed adapter and complete primary-TOC authority ledger, or an explicit reviewed no-TOC authority decision, before physical hierarchy or content splitting.
- When chapters or sections contain internal modules, subtopics, or pedagogical divisions (`一、`, `二、`, `考点1`, `考点2`, `专题1`, `题型1`), ALWAYS build a 3-level (or 4-level) fine-grained hierarchy (章 -> 节 -> 考点/模块 -> 例题), scoping question ownership exclusively to the finest leaf nodes. Never flatten internal subtopics into flat section notes.
- Every entry in `entries` and `primary_authority` MUST be strictly sorted in monotonic increasing reading order by `source_line` (Line 1 -> Line 2 -> ...). Never append chapter nodes before section/subtopic nodes.
- For MinerU OCR, enforce chunking threshold of `MAX_PAGES = 80` to eliminate cloud OCR timeouts and parsing failures on large volumes.
- For multi-volume series (e.g. 上册, 下册), isolate output folders under distinct subpaths (e.g. `graph_root/上册`, `graph_root/下册`) and maintain separate staging profiles so audit checks remain 100% independent and collision-free.
- Parse every leader-delimited index record even when several visual-column
  entries share one OCR line. Show both source-stream and column-major orders in
  the worksheet; never publish the recommended order without review. Count
  coverage per leader-delimited entry, so one registered record cannot conceal
  a sibling record joined onto the same OCR line.
- For a multi-volume series, inventory and visually confirm every volume
  independently. Freeze per-volume hierarchy depth, body anchors, answer
  region, output root, and disabled-output policy; reuse only path-free semantic
  patterns. A successful sibling volume is not evidence for another volume.
- Keep all source-label semantics and inline question/answer marker syntax in
  the frozen adapter or path-free series preset. Treat any new-book change to
  reusable recognition code as a generalization failure requiring review.
- Honor adapter `output_policy` after format review. `generate_index: false`
  suppresses the synthetic root note, and `generate_canvas: false` suppresses
  Canvas even when the profile requested it; disabled outputs must leave no
  owned stale artifact or manifest.
- Create one note per top-level question, named with a persistent 8-digit QID
  allocated through the locked vault registry. Seed a new registry from the
  vault and an optional adapter-configured central repository.
- Flatten question-bearing HTML tables by semantic column streams before
  splitting, recover adapter-defined roles embedded in table cells, and block
  completion unless every answer context has a continuous `1..N` question
  ledger with no gaps, duplicates, or reordering.
- Prefer adapter `content.question_scopes` over expanding a global question
  regex with book-specific negative lookaheads. Scope by reviewed functional
  roles, hierarchy contexts, and/or local raw-line ranges.
- Classify publisher example/variant headers through reviewed
  `content.question_kind_rules`. Decide the source's actual question boundary
  before compiling: a publisher wrapper such as `[例1]` is not automatically
  one question. If it immediately contains independently stated and
  independently solved `(1)(2)…` items, enable reviewed
  `atomize_interleaved_subquestions` and create one original Q node plus one A1
  per item. Keep a single composite node only when the items share a genuine
  stem or depend on one another. Every resulting `worked-example` leaf receives
  `重要程度: 重要`, moves its publisher solution to a standalone
  provenance-marked `<QID>A1.md` note, embeds that answer from the stem-only
  question note, and is excluded from external answer matching.
- Classify teacher-edition exercises whose publisher solutions are printed
  immediately after each question as a non-worked-example
  `separate-authoritative` kind. Use adapter-driven `tail` or `interleaved`
  solution layouts. For a genuine shared-stem composite, retain every subpart
  stem in one Q and collect every solution segment in one A1. For an
  independently solved example packet, atomize at the reviewed item boundaries
  instead. Such interleaved files are `questions` sources, not fake combined
  sources with overlapping regions. Set `sequence_policy: continuous` when
  their numeric ledger must still be audited.
- For single-topic teacher-edition PDFs in this format, record
  `generate_index: false` and `generate_canvas: false` in the reviewed adapter;
  topic and functional notes remain available without synthetic overview files.
- If the source is already inside a dedicated topic directory, make that
  directory the graph root instead of appending a PDF-stem wrapper. Record this
  reviewed direct-root decision in adapter inventory evidence.
- Immediately after content segmentation, clean every generated title and its
  corresponding filename through the shared filename policy. Replace unsafe
  filesystem characters and always replace both `:` and `：` with `_`, while
  preserving other reviewed title characters. Never apply this cleanup to
  immutable OCR source text.
- Normalize all hierarchy output directory paths via `normalize_section_title` (`output: "考点XX_名称/考点XX_名称.md"`) to ensure uniform folder structures across all topics while keeping `title` matched with frozen Markdown for `source-heading` anchor validity.
- Format every answer note as a collapsible outer `> [!faq]- <title>` with
  three collapsible nested blocks: `[!success]- **【答案】**`,
  `[!note]- **【分析】**`, and `[!note]- **【解析】**`. Prefix every nested body
  line with `> >`. Support `【详解】`, `【思路导航】`, `【解答】`, `【解法】`, `【证法】`, `【证明】` headers alongside `【解析】`. Extract non-choice short answers cleanly into the `[!success]` Callout header while removing duplicate answer lines and `【详解】` headers from the resolution body. If the publisher does not separately label analysis, write `本题未单列分析。` without duplicating the derivation. Recover explicit publisher short-answer prefixes; use `详见解析` only for non-choice problems without a safely separable short result. Choice problems require exact option selections such as `**【答案】** A`. Preserve itemized bullet points and pedagogical sections (`💡 规律方法`, `📌 名师点拨`, `🔔 敲黑板`, `💡 点悟`, `🔗 链接教材`, `⚠️ 易错警示`).
- Enforce zero-tolerance explanation validation: external-answer exercises MUST
  embed a valid solution callout note (`![[Q*A1]]`); worked examples MUST carry
  required important/separated metadata and embed a valid standalone publisher
  solution note. The question-source block must contain only the stem. Any
  failure is blocking with its exact cause.
- Require exact answer identity or blocking review. Never accept fuzzy evidence alone. A passed answer manifest must have unique `answer_id` AND unique `question_id` (one owner per answer block, one match per question).
- Block every authoritative `unmatched-answer` as `answer-without-question`,
  even when the remaining review queue was reviewer-confirmed; this is the
  cross-source gate for detecting a wholly missing terminal question span.
- When a verified publisher/OCR numbering reset requires a constant semantic
  offset, require matching reviewed, source-anchored question and answer shift
  ranges; preserve the printed number in immutable source bodies.
- Recover a PDF-visible question omitted from raw Markdown only through a
  reviewer-confirmed, page-provenanced virtual question entry anchored to the
  immutable corpus; never infer the stem from an answer block.
- Recover a PDF-visible fragment omitted inside an existing question only
  through `content.recovered_question_fragments`, using an exact hierarchy-note
  raw line/column, before/after insertion position, drift anchor, PDF page/bbox,
  and reviewer confirmation. The frozen OCR source remains unchanged and final
  audit must retain the fragment provenance marker.
- Recover a PDF-visible authoritative answer omitted or corrupted in raw
  Markdown only through a reviewer-confirmed `recovered_answers` entry carrying
  context, number, exact body, PDF page, and a raw-source drift anchor. Keep it
  distinct from AI supplementation and require both rendered `【答案】` and
  `【解析】` fields after application.
- Reconcile stale answer artifacts automatically from the application ownership
  report whenever matching changes.
- Permit Markdown-only presentation changes and verify lexical preservation.
- Keep atomic questions off Canvas and knowledge linking deferred.
- Before accepting content segmentation, compare the reviewed source ledger to
  the manifest: count ordinary questions and every independently solved packet
  item. Freeze those reviewed per-context/per-kind totals in
  `content.question_count_expectations`, require one Q and one authoritative A1
  per expected item, and reject an
  atomic Q whose body still contains two independently solved item starts.
  Inspect at least the first, middle, and last generated hierarchy/Q/A1 notes;
  do not treat a successful coordinator exit as semantic proof.
- For a hierarchy whose non-leaf nodes are organizational, set
  `hierarchy.question_ownership_policy: leaf-only`. Require every non-leaf to be
  `structural_only`, explicit question scopes to cover exactly all leaves, and
  a reviewed count for every leaf/question-kind pair including zero. Final
  audit must prove every Q belongs to a leaf and appears exactly once across all
  generated navigation notes.
- If overlapping OCR blocks duplicate one printed line, preserve frozen raw and
  use only a reviewer-confirmed `reviewed_semantic_line_exclusions` entry bound
  to the exact hierarchy-local line, drift anchor, PDF page/bbox, and reason.
  Never use semantic exclusion to remove genuine source content.
- If OCR joins the end of one solved item and the next question header on one
  physical line, preserve frozen raw and use reviewer-confirmed
  `reviewed_semantic_line_splits` with exact hierarchy-local Unicode columns,
  drift anchor, and PDF page/bbox before atomizing the packet.
- Complete only when `final-audit-report.json` reports `status: passed` and the
  independent ledger, duplicate-heading, Q/A1 parity, embed, disabled-output,
  and representative source-versus-output checks all pass.
- Never bypass a review gate by directly applying downstream components. Fix
  the owning review artifact and resume through the coordinator; compiler
  implementation hashes must invalidate stale descendants automatically.
