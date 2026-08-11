---
name: question-type-graph
description: Coordinate conversion of supplementary exercise books into audited Obsidian question-type graphs using typed question, answer, or combined PDF/Markdown sources, reviewed format adapters, atomic question notes, exact answer matching, markup-only formatting, and an optional structural Canvas. Use for new conversions, resumes, format inventory, or final audits across publishers and layouts.
---

# Question Type Graph

Coordinate the standalone skills and enforce profile, review, preservation, and audit gates. Keep book-specific rules in staging adapters rather than coordinator code.

## Read

- Read `references/pipeline-contract.md` before starting or resuming.
- Read `references/format-adapter.md` when inventorying an unfamiliar book.
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

The first run stops after `format-inventory.json` and creates a schema-shaped
`format-adapter.draft.json` until a reviewer-confirmed `format-adapter.json`
exists. Resume with `resume`; unchanged stages are reused by input fingerprint,
while a drifted stage invalidates and rebuilds its descendants. Inspect durable
stage attempts, durations, fingerprints, and artifacts with `status`; rerun and
persist the final checks with `audit --overwrite`.

## Gates

- Freeze every source path, digest, role, page count, and output root.
- Force MinerU OCR for PDFs and stop on incomplete page or asset coverage.
- Require a reviewed adapter and complete primary-TOC authority ledger, or an explicit reviewed no-TOC authority decision, before physical hierarchy or content splitting.
- Keep all source-label semantics and inline question/answer marker syntax in
  the frozen adapter or path-free series preset. Treat any new-book change to
  reusable recognition code as a generalization failure requiring review.
- Create one note per top-level question, named with a persistent 8-digit QID
  allocated through the locked vault registry. Seed a new registry from the
  vault and an optional adapter-configured central repository.
- Flatten question-bearing HTML tables by semantic column streams before
  splitting, recover adapter-defined roles embedded in table cells, and block
  completion unless every answer context has a continuous `1..N` question
  ledger with no gaps, duplicates, or reordering.
- Immediately after content segmentation, clean every generated title and its
  corresponding filename through the shared filename policy. Replace unsafe
  filesystem characters and always replace both `:` and `：` with `_`, while
  preserving other reviewed title characters. Never apply this cleanup to
  immutable OCR source text or question bodies. Route every hierarchy
  `root_output` and `entries[].output` component through the same normalizer;
  final audit must fail if `:` or `：` survives in any generated file or
  directory path.
- Save matched solutions as standalone answer notes named `<Question_ID>A<Index>.md` (e.g., `Q00004154A1.md`), and embed them in the question note via `![[Q00004154A1]]`. Pre-split adapter-recognized inline OCR question and answer headers while retaining raw-line and raw-column coordinates so concatenated records are parsed without shifting reviewed region or context anchors. Preserve mapped theory-guide content in place; knowledge linking remains deferred.
- Format all answer notes into collapsable Callout blocks (`> [!faq]- <callout_title>`, e.g., `全练一本通解析`) with both `**【答案】**` and `**【解析】**`. Recover explicit publisher short-answer prefixes; use `详见解析` only for non-choice problems without a safely separable short result. Choice problems require exact option selections such as `**【答案】** A`. Preserve itemized bullet points and pedagogical sections (`💡 规律方法`, `📌 名师点拨`, `🔔 敲黑板`, `💡 点悟`, `🔗 链接教材`, `⚠️ 易错警示`).
- Enforce zero-tolerance explanation validation: every atomic question note MUST embed a valid solution callout note (`![[Q*A1]]`). Any question lacking an explanation MUST trigger a blocking audit error (`question-lacking-explanation`) with its exact cause identified.
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
- Recover a PDF-visible authoritative answer omitted or corrupted in raw
  Markdown only through a reviewer-confirmed `recovered_answers` entry carrying
  context, number, exact body, PDF page, and a raw-source drift anchor. Keep it
  distinct from AI supplementation and require both rendered `【答案】` and
  `【解析】` fields after application.
- Reconcile stale answer artifacts automatically from the application ownership
  report whenever matching changes.
- Permit Markdown-only presentation changes and verify lexical preservation.
- Keep atomic questions off Canvas and knowledge linking deferred.
- Complete only when `final-audit-report.json` reports `status: passed`.
