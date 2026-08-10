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
- Save matched solutions as standalone answer notes named `<Question_ID>A<Index>.md` (e.g., `Q00004154A1.md`), and embed them in the question note via `![[Q00004154A1]]`. Pre-split adapter-recognized inline OCR question and answer headers while retaining raw-line and raw-column coordinates so concatenated records are parsed without shifting reviewed region or context anchors. Preserve mapped theory-guide content in place; knowledge linking remains deferred.
- Format all answer notes into collapsable Callout blocks (`> [!faq]- <callout_title>`, e.g., `全练一本通解析`), including option selections (`**【答案】** A`), itemized bullet points, and pedagogical sections (`💡 规律方法`, `📌 名师点拨`, `🔔 敲黑板`, `💡 点悟`, `🔗 链接教材`, `⚠️ 易错警示`).
- Enforce zero-tolerance explanation validation: every atomic question note MUST embed a valid solution callout note (`![[Q*A1]]`). Any question lacking an explanation MUST trigger a blocking audit error (`question-lacking-explanation`) with its exact cause identified.
- Require exact answer identity or blocking review. Never accept fuzzy evidence alone. A passed answer manifest must have unique `answer_id` AND unique `question_id` (one owner per answer block, one match per question).
- Reconcile stale answer artifacts automatically from the application ownership
  report whenever matching changes.
- Permit Markdown-only presentation changes and verify lexical preservation.
- Keep atomic questions off Canvas and knowledge linking deferred.
- Complete only when `final-audit-report.json` reports `status: passed`.
