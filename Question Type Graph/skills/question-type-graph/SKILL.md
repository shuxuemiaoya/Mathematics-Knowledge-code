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
  --staging-root "/Users/oven/Documents/ovenmathmap/.temp/<pdf_title>-staging" `
  --vault-root "/Users/oven/Documents/ovenmathmap" `
  --graph-root "/Users/oven/Documents/ovenmathmap/<relative_path_to_pdf_title>" `
  --canvas --output "/Users/oven/Documents/ovenmathmap/.temp/<pdf_title>-staging/question-type-profile.json"
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
- Create one note per top-level question, named with monotonically increasing 8-digit sequence numbers across the vault and central repository `/Users/oven/Documents/ovenmathmap/mathmap/习题/questions` (e.g. `Q00004154.md`). Automatically lookup `max_q_num` across roots to prevent duplicates.
- Save matched solutions as standalone answer notes named `<Question_ID>A<Index>.md` (e.g., `Q00004154A1.md`), and embed them in the question note via `![[Q00004154A1]]`. Pre-split inline OCR answer headers before scanning so concatenated headers (e.g. `... 故选：B 【5】A`) are parsed as distinct answer blocks. Validate and align `answers.contexts` `start_line` boundaries against exact section headings in `answers.raw.md`. In Stage 5 (Content Segmentation), extract `## 知识导学` formula and concept subheadings into standalone atomic concept notes (e.g. `3. 终边相同的角.md`). In Stage 7 (Markdown Standardization), append a Wiki bi-directional link (`[[<path>|<title>]]`) at the bottom of each concept note to connect it to its corresponding basic point note (e.g. `▶基础点 2_ 终边相同的角.md`) rather than an embedding (`![[...]]`), ensuring graph topology connectivity while preventing nested view redundancy.
- Format all answer notes into collapsable Callout blocks (`> [!faq]- <callout_title>`, e.g., `全练一本通解析`), including option selections (`**【答案】** A`), itemized bullet points, and pedagogical sections (`💡 规律方法`, `📌 名师点拨`, `🔔 敲黑板`, `💡 点悟`, `🔗 链接教材`, `⚠️ 易错警示`).
- Enforce zero-tolerance explanation validation: every atomic question note MUST embed a valid solution callout note (`![[Q*A1]]`). Any question lacking an explanation MUST trigger a blocking audit error (`question-lacking-explanation`) with its exact cause identified.
- Require exact answer identity or blocking review. Never accept fuzzy evidence alone. A passed answer manifest must have unique `answer_id` AND unique `question_id` (one owner per answer block, one match per question).
- Before the final audit, after any matcher/adapter change that flips questions matched → unmatched, clean stale answer artifacts: orphaned `Q*<id>A1.md` notes and `![[Q*<id>A1]]` embeds in question notes (the audit errors `unexpected-generated-note` / `broken-link` otherwise).
- Permit Markdown-only presentation changes and verify lexical preservation.
- Keep atomic questions off Canvas and knowledge linking deferred.
- Complete only when `final-audit-report.json` reports `status: passed`.
