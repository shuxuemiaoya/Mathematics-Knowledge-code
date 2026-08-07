---
name: question-type-graph
description: Coordinate conversion of supplementary exercise books into audited Obsidian question-type graphs using typed question, answer, or combined PDF/Markdown sources, reviewed format adapters, atomic question notes, exact answer matching, markup-only formatting, and an optional structural Canvas. Use for new conversions, resumes, format inventory, or final audits across publishers and layouts.
---

# Question Type Graph

Coordinate the standalone skills and enforce profile, review, preservation, and audit gates. Keep book-specific rules in staging adapters rather than coordinator code.

## Read

- Read `references/pipeline-contract.md` before starting or resuming.
- Read `references/format-adapter.md` when inventorying an unfamiliar book.
- Load each component skill only when entering its stage.

## Run

Initialize typed sources (naming graph folder after the PDF title and omitting any extra `vault` subfolder):

```powershell
python scripts/question_type_graph.py init `
  --source "questions=<questions.pdf>" `
  --source "answers=<answers.pdf>" `
  --title "<pdf_title>" `
  --staging-root "<root>/<pdf_title>/staging" `
  --vault-root "<root>" `
  --graph-root "<root>/<pdf_title>" `
  --canvas --output "<root>/<pdf_title>/staging/question-type-profile.json"
```

Use one `combined=<path>` source for a combined book, or only `questions=<path>` for a deliberately answerless book. Then run:

```powershell
python scripts/question_type_graph.py run "<profile>"
```

The first run stops after `format-inventory.json` until a reviewer-confirmed `format-adapter.json` exists. Resume with `resume`; unchanged hierarchy/content application artifacts are reused by hash, while drifted inputs are rebuilt. Inspect durable stage attempts and artifacts with `status`; rerun and persist the final checks with `audit --overwrite`.

## Gates

- Freeze every source path, digest, role, page count, and output root.
- Force MinerU OCR for PDFs and stop on incomplete page or asset coverage.
- Require a reviewed adapter and complete primary-TOC authority ledger, or an explicit reviewed no-TOC authority decision, before physical hierarchy or content splitting.
- Create one note per top-level question, named with monotonically increasing 8-digit sequence numbers across the vault (e.g. `Q00000001.md`, `Q00000002.md`). Automatically lookup vault `max_q_num` to prevent duplicates.
- Save matched solutions as standalone answer notes named `<Question_ID>A<Index>.md` (e.g., `Q00000001A1.md`), and embed them in the question note via `![[Q00000001A1]]`.
- Format all answer notes into collapsable Callout blocks (`> [!faq]- 必刷题解析`), including option selections, itemized bullet points, and pedagogical sections (`💡 规律方法`, `📌 名师点拨`, `🔔 敲黑板`, `💡 点悟`, `🔗 链接教材`, `⚠️ 易错警示`).
- Require exact answer identity or blocking review. Never accept fuzzy evidence alone. A passed answer manifest must have unique `answer_id` AND unique `question_id` (one owner per answer block, one match per question).
- Before the final audit, after any matcher/adapter change that flips questions matched → unmatched, clean stale answer artifacts: orphaned `Q*<id>A1.md` notes and `![[Q*<id>A1]]` embeds in question notes (the audit errors `unexpected-generated-note` / `broken-link` otherwise).
- Permit Markdown-only presentation changes and verify lexical preservation.
- Keep atomic questions off Canvas and knowledge linking deferred.
- Complete only when `final-audit-report.json` reports `status: passed`.
