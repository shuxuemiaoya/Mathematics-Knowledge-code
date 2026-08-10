---
name: reformat-exam-markdown
description: Reformat Markdown exam papers while preserving separate question and answer sections, inserting a forced page break before the answer key, compacting multiple-choice and fill-in answers by section, standardizing numbered questions as `1. ` list items, positioning question images before answer choices, and restructuring worked solutions into readable logical steps with display-style fractions. Use for Chinese or English exam-paper cleanup and preparation for later Pandoc or LaTeX-template processing when the source contains an answer key or worked solutions.
---

# Reformat Exam Markdown

Convert a source exam into a reviewable, LaTeX-oriented Markdown structure while keeping the question paper and reference answers separate.

## Workflow

1. Inspect the source before editing. Identify the paper title, subject, question-section headings, question-number range, answer heading, image links, and whether answers are embedded or stored separately.
2. Read [references/output-schema.md](references/output-schema.md) before changing the schema or manually correcting generated output.
3. Run a parse-only check first:

   ```powershell
   $env:PYTHONUTF8='1'
   python <skill-dir>\scripts\reformat_exam_markdown.py <paper.md> --check
   ```

4. Generate a sibling candidate. Omit `--output` to use the default `（题解整合版）.md` filename:

   ```powershell
   python <skill-dir>\scripts\reformat_exam_markdown.py <paper.md>
   ```

   If answers are in a second file, add `--answers <answers.md>`.
5. Inspect every reported missing or extra answer number. Correct ambiguous OCR or source layout manually; never invent a missing answer.
6. Review the candidate around section boundaries, complete A-D choice groups, table-shaped source data, question images, subquestions, and consecutive worked solutions. Inspect `image_path_rewrites`, `question_image_placement_violations`, and `unresolved_image_targets` in the JSON report.
7. Keep the source unchanged. Replace it only when the user explicitly approves replacement.

## Formatting Rules

- Preserve the semantic order and wording of questions, subquestions, mathematics, scoring annotations, and image targets.
- Keep all questions in the first half and all short answers and worked solutions under a later `# <subject>参考答案` heading. Never place an answer directly after its question.
- Insert `<div style="page-break-after: always;"></div>` immediately after the exam paper and before `<!-- answer-section -->` so the answer key starts on a new page.
- Render every question and answer entry as a numbered Markdown item beginning with its literal number and `. `, such as `1. ` or `15. `; do not use headings for question numbers.
- Keep each multiple-choice or fill-in answer section on one compact source line when practical, separating entries with an ideographic space: `1. C　2. B　3. A`. Keep worked solutions as separate numbered blocks.
- Convert recognizable A–D choices to indented Markdown list items without rewriting their content.
- Require each recognizable choice to occupy its own list item. Do not leave option A appended to the stem or combine two option labels in one item.
- Convert unambiguous row-and-column source data into a real Markdown table while preserving every header, row label, value, and reading order. If the table structure is ambiguous or incomplete, preserve the text and report it for manual review instead of flattening it into a misleading vertical list.
- Group every question image after the complete stem and subquestions but before the first answer choice. Keep related images together.
- Restore paragraph breaks before solution subparts and logical transitions such as `由`, `因为`, `所以`, `又`, `则`, `故`, `解得`, and `因此`. Keep each transition on a new indented paragraph inside its numbered answer item.
- Replace LaTeX `\frac{...}{...}` with `\dfrac{...}{...}` in the candidate to produce slightly longer fraction bars; preserve the operands exactly.
- Preserve a valid image link. If a relative target is broken only because it redundantly starts with the source folder name, rewrite it to the proven existing asset path relative to the candidate.
- Preserve unresolved content instead of guessing. Report missing and extra mappings in the script's JSON summary.
- Do not create backup files. The generated candidate is the recoverable artifact.
- Do not call an LLM or external API for the deterministic merge.

## Validation

Treat the run as structurally successful only when:

- the output parses all expected question numbers exactly once;
- questions and answers remain in separate top-level sections;
- the exact page-break `<div>` occurs between the exam paper and answer section;
- each short-answer section uses one compact line when practical;
- each question uses `1. ` numbering rather than a heading;
- each question image precedes its answer choices;
- every recognizable A–D choice group has one separate item per option, with no option embedded in the stem or combined with another option;
- every unambiguous source table remains a table with the same headers, row labels, and values rather than a vertical text sequence;
- every source image reference remains represented and every rewritten target resolves to an existing asset;
- no answer number is mapped to the wrong question;
- `missing_answers` and `extra_answers` are empty, unless the source itself is incomplete;
- both the paper and optional answer source retain their original SHA-256 hashes.

The script exits nonzero on structural parsing failure. Use `--strict` to also exit nonzero when answer mappings are incomplete.
