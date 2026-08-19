---
name: exam-paper-parser
description: Parse standardized combined exam-and-solution PDFs and Word documents (.doc/.docx) into audited Obsidian section notes, stable-QID atomic question notes, standalone authoritative solution callouts, and images without Canvas output. Use for Chinese high-school exam papers such as 高考真题解析版 when Codex needs a much faster, low-token alternative to Question Type Graph, including batch processing, cached MinerU OCR, deterministic question splitting, PDF/Word text answer recovery, or final output auditing.
---

# Exam Paper Parser

Use the bundled deterministic coordinator for PDF and Word (.doc/.docx) exam papers. Do not create a per-paper adapter for a paper that passes the standard profile.

## Run

Single paper (PDF or Word):

```bash
python scripts/exam_paper_parser.py run <paper.doc / paper.docx / paper.pdf> \
  --vault-root <obsidian-vault> \
  --output-root <year-classified-root>
```

Batch:

```bash
python scripts/exam_paper_parser.py batch <paper-1.doc> <paper-2.docx> <paper-3.pdf> ... \
  --vault-root <obsidian-vault> \
  --output-root <year-classified-root> --jobs 4
```

Use `run` with `--markdown` to consume an existing MinerU result without another OCR call. Use `audit <manifest.json>` to rerun only the final checks.

## Fast-path contract

- Keep the PDF and OCR Markdown immutable.
- Cache OCR by PDF SHA-256 and reuse it automatically.
- Recognize standard question-section headings and a continuous global numeric ledger.
- Split each top-level question once; keep subparts together.
- Split at explicit `【答案】/【解析】/【分析】/【详解】` markers only.
- Keep strategy summaries in `【分析】`; route every `【小问 n 详解】` block and
  derivation to `【解析】`.
- Reconcile OCR-dropped choice answers from the original PDF text layer; never infer an option from mathematical prose.
- Allocate stable QIDs under the shared vault registry lock.
- Emit one standalone authoritative answer note per question with nested collapsible answer, analysis, and explanation callouts.
- Preserve formulas, images, wording, order, and source-page provenance.
- Do not create `.canvas` files.
- Finish only when `final-audit-report.json` is `passed` with no errors or warnings.

## Review gate

Stop with `review_required` when section detection, the `1..N` ledger, expected section counts, source solutions, choice answers, image links, or source provenance cannot be proven. Escalate that paper to Question Type Graph only then; do not weaken the audit or ask an LLM to guess.

Read [references/output-contract.md](references/output-contract.md) only when changing the output schema or diagnosing an audit failure.
