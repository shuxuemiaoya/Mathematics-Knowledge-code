# Question Type Graph Agent Change Log

## 2026-09-18 — Bishuati multi-band sequence matching and choice answer precision

- **Multi-band Sequence Decoupling**: Documented and established rules for exercise series containing parallel training bands (e.g., `刷基础`, `刷提升`, `刷易错`) with restarting question numbers.
- **Choice-Answer Overrides (`choice_answer_overrides`)**: Enforced explicit registration of `context`, `number`, `start_line`, `answer`, and `anchor_text` to prevent longer explanation blocks from overwriting choice answers, resolving `solution-choice-answer-missing` and eliminating synthetic AI fallback placeholders.
- **Leading Option Extraction Priority**: Fixed option extraction precedence to prioritize definitive leading headers over regex matches from explanation prose (preventing "错选 B" remarks from overriding "20. C"), eliminating `solution-choice-answer-mismatch`.
- **Two-Column Reading Order & Section Boundary Alignment**: Addressed MinerU cross-column interleaving by aligning section answer start lines strictly to the problem stream (e.g., correcting chapter test boundary from 7097 to 7071).
- **Pure Organizational Parent Exclusion**: Codified mandatory exclusion of title-only parent headers (`excluded_entries`) to prevent invalid embed ownership and phantom answer preemption.
- **Punctuation & Heading Resilience**: Integrated Chinese/English quote lookaheads (`\u201c\u201d\u2018\u2019\"“”`) and optional Markdown headings into practice question patterns alongside `implicit_answers` and `recovered_question_fragments`.

## 2026-08-14 — interleaved teacher-edition solutions

- Added reviewed adapter output switches for synthetic root index and Canvas
  generation. Single-topic teacher-edition adapters can now explicitly disable
  both, safely prune only owned prior artifacts, and audit their absence.
- Documented direct-root publishing for topic PDFs already stored in a
  dedicated topic directory, avoiding an extra PDF-title wrapper folder.
- Added an explicit `inline-solved-exercise` strategy for teacher editions that
  print an authoritative answer immediately after every exercise.
- Added adapter-driven `tail` and `interleaved` authoritative-solution layouts,
  preserving all subpart stems in one top-level question while moving all
  publisher solutions to its standalone A1 note.
- Separated worked-example importance semantics from generic publisher-solved
  exercises and retained continuous-number auditing through `sequence_policy`.
- Added composite-answer handling guidance and regression coverage for
  interleaved subparts and same-number inline answer rows.
- Added page-provenanced `recovered_question_fragments` for exact, reviewed
  insertion of OCR-omitted text inside an existing question without mutating
  the frozen OCR corpus.
- Bound inventory, hierarchy, content, answer, Markdown, Canvas, and audit
  fingerprints to their compiler module hashes so resume cannot silently reuse
  artifacts produced by older implementation semantics.

## 2026-08-12 — worked-example completeness and answer UX

- Added adapter-scoped recognition for publisher examples and variants.
- Made every worked example atomic and globally enforced `重要程度: 重要`.
- Added reviewed question/solution boundaries and standalone authoritative
  `<QID>A1.md` generation so stems and solutions cannot remain mixed.
- Added three nested collapsible answer sections: `【答案】`, `【分析】`, and
  `【解析】`, all inside the collapsible publisher answer callout.
- Added final-audit ownership, provenance, embed, structure, and substantive
  solution gates for content-generated worked-example answers.
- Added regression tests for kind-scoped atomization, question/answer
  separation, nested Callout rendering, and result-only solution rejection.
