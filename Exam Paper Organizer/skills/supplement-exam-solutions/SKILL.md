---
name: supplement-exam-solutions
description: Add authoritative or generated answers, concise method analysis, and appropriately detailed explanations directly below every question in a Markdown exam paper. Use when Codex must turn a question-only paper or a paper with a terse answer key into a compact inline worked-solution edition, copying complete supplied long-form solutions directly, using gpt-5.6-sol only for missing material, and writing a sibling file whose name ends in `（解析版）.md` while leaving the source unchanged.
---

# Supplement Exam Solutions

Create a complete inline worked-solution edition as a new sibling Markdown file without modifying the source or changing the wording, order, numbering, choices, figures, or mathematics of its questions.

## Workflow

1. Inspect the entire Markdown paper before editing. Identify section boundaries, shared stems, question IDs, subquestions, choices, figures, tables, scoring annotations, and any embedded answer section.
2. Locate answer sources in this order:
   - an answer attachment explicitly supplied or named by the user;
   - an answer section embedded in the exam paper;
   - one unambiguous answer or solution file in the same folder whose name clearly matches the paper.
3. If several possible answer files exist, do not guess. Ask the user which file is authoritative.
4. Build a question inventory and map answers by section plus question ID. When numbering restarts, also compare the stem text; never map by position alone.
5. Treat the selected answer source as authoritative. Preserve its final answers and usable solution text. Do not silently correct or replace them.
   - If a long-form question already has a detailed solution, copy that solution directly into `**Detailed explanation:**` and add only the necessary concise `**Analysis:**`.
   - Do not paraphrase, expand, renumber, re-derive, or add an alternative approach to a complete supplied long-form solution unless the user explicitly requests it.
6. Use `gpt-5.6-sol` for every missing component:
   - If no answer source exists, generate the answer, analysis, detailed explanation, and alternative approaches for every question.
   - If the source gives only a letter, value, or short conclusion, preserve that result and generate the missing analysis and explanation around it.
   - If only some questions are covered, use the source for covered questions and generate complete solutions for the gaps.
   - Do not send a complete supplied long-form solution to the model for rewriting; generate only its missing analysis.
7. Derive the required sibling output path, copy the complete source into that new file, and insert one solution block immediately after each complete question block and before the next question. Keep shared-stem questions together and place the solution after all of that question's subparts.
8. Write all changes only to the sibling output. Do not modify the source, any answer attachment, or an existing answer-key section copied into the output.
9. Validate coverage, provenance, placement, output naming, and source preservation before reporting completion.

## Output File Contract

- Never edit the source Markdown file directly.
- Insert `（解析版）` immediately before the source's `.md` extension and place the result in the same directory. For example, write `试卷（解析版）.md` from `试卷.md`.
- Preserve the entire existing stem when adding the suffix. For example, write `试卷（题解整合版）（解析版）.md` from `试卷（题解整合版）.md`.
- Append the suffix exactly once. If the source stem already ends with `（解析版）`, require an explicit different output filename instead of creating `（解析版）（解析版）`.
- If the derived output file already exists, do not overwrite it without the user's explicit approval. Stop and report the existing-file gate or use another filename explicitly supplied by the user.
- Preserve relative image and asset links unchanged because the output remains in the source directory.
- Do not create a backup file; the untouched source is the recovery artifact.

## Invoke the Required Model

- If the active agent is already `gpt-5.6-sol`, generate the missing material locally.
- Otherwise, delegate the missing material to one or more bounded subagents with the model override `gpt-5.6-sol`.
- Give each subagent the absolute paper path, the exact question range, relevant shared stems and image paths, and any authoritative final answers it must preserve.
- Ask for reader-facing derivations, not private scratch work or hidden chain-of-thought.
- Batch contiguous questions when the paper is long, but keep each question assigned to exactly one generator.
- Do not substitute another model if `gpt-5.6-sol` is unavailable. Stop and report the model-availability gate.

## Insertion Format

Use these markers so reruns can replace a block instead of duplicating it. Keep multiple-choice and fill-in-the-blank blocks compact:

```markdown
<!-- exam-solution:start id="1" -->
**Answer:** B　**Analysis:** Identify the governing idea, why the selected method applies, and any common trap.

**Detailed explanation:** Give a compact, checkable derivation. Keep short calculations inline; start a new paragraph only at a logical transition or when the current block becomes long.
<!-- exam-solution:end id="1" -->
```

- For a complete supplied long-form solution, use:

  ```markdown
  <!-- exam-solution:start id="15" -->
  **Answer:** State the official conclusion.

  **Analysis:** Briefly identify the method and its key idea.

  **Detailed explanation:**

  Copy the supplied detailed solution directly, preserving its original paragraphs, equations, subquestion labels, and scoring annotations.
  <!-- exam-solution:end id="15" -->
  ```

- Use the paper's language for all inserted text.
- Use the exact visible question ID in each marker. Prefix it with a section identifier when numbering restarts, such as `II-1`.
- For a question written as a Markdown list item, indent every inserted line to remain inside that list item. For heading-based questions, keep the block unindented.
- For multipart questions, keep one outer block and label the answer and derivation for each subpart clearly.
- Add `**Alternative approach:**` only for generated or incomplete-source solutions when a genuinely different method is useful. Do not add it to a complete supplied long-form solution unless requested.
- Preserve valid Markdown and LaTeX. Use display math for multi-step derivations and keep image links unchanged.

## Layout Density

- Prefer coherent prose, compact equation groups, and descriptive transitions over numbered lists inside `**Detailed explanation:**`.
- Do not automatically turn every calculation or inference into `1.`, `2.`, `3.` steps.
- Use numbered steps only when the order is genuinely essential, such as an algorithm, construction, or multi-stage proof that would otherwise be ambiguous.
- Preserve the source's existing `（1）`, `（2）` subquestion labels; do not replace them with a new numbered list.
- For multiple-choice and fill-in-the-blank questions, keep `**Answer:**` and a short `**Analysis:**` on the same line when readable.
- Keep short derivations in one paragraph. Insert a paragraph break only after a logical transition, before a substantial displayed derivation, or when a block of text becomes long.
- Do not place every sentence, equation, or conclusion on its own line merely for uniformity.

## Explanation Requirements

### Multiple-choice questions

- State the option and its content when useful.
- Derive or justify the correct option rather than merely restating it.
- Explain why the other options fail when that comparison is informative and can be done concisely.
- Mention traps such as sign errors, excluded values, unit mismatches, or misread conditions.
- Keep the answer and explanation visually compact; do not force a line break after every label, sentence, or option check.

### Fill-in-the-blank questions

- State the exact value, expression, interval, unit, or conclusion required by the blank.
- Show the calculation or logical path that produces it.
- Check domain restrictions, endpoint inclusion, significant conditions, and units where relevant.
- Keep short calculations inline and use paragraph breaks only for real changes in reasoning or long displayed work.

### Long-form and proof questions

- If a complete detailed solution is supplied, copy it directly and add only the necessary method analysis.
- Preserve the supplied wording, method, result, paragraph structure, equations, subquestion labels, and scoring annotations.
- Do not regenerate, paraphrase, expand, or convert the supplied solution into a new numbered-step structure.
- If no complete solution is supplied, generate a readable derivation with explicit reasons for non-obvious transitions while still avoiding unnecessary numbered lists.
- Match subparts one-to-one and end each with a clear conclusion.
- For generated solutions only, add a genuinely distinct approach when practical, such as algebraic versus geometric, synthetic versus coordinate, direct versus contradiction, or exact versus graphical verification.

## Source Fidelity and Conflict Handling

- Treat the source as read-only and verify its hash before and after creating the derived file.
- Do not rewrite, summarize, reorder, or renumber questions.
- Do not move choices, images, tables, or scoring annotations.
- Copy authoritative final answers exactly, allowing only Markdown normalization that does not change meaning.
- If an official answer conflicts with the question or another supplied source, keep the designated authoritative answer, add a short clearly labeled caution in the solution block, and report the conflict.
- If a figure is required but unreadable or missing, leave that question unresolved and report it instead of inventing visual facts.
- If an existing marked solution block is present, replace it. If an unmarked inline solution is already present, reconcile it instead of adding a duplicate.

## Validation

Confirm all of the following:

- Every inventoried question has exactly one solution block directly below it.
- The source file hash is unchanged, and the output is a separate sibling whose stem ends with exactly one `（解析版）`.
- Every solution block contains an answer, analysis, and detailed explanation.
- Every authoritative final answer still matches its source.
- Every complete supplied long-form solution is copied directly rather than rewritten, with only necessary analysis added.
- Every generated answer is attributable to `gpt-5.6-sol` rather than an unapproved fallback.
- Removing only the marked solution blocks from the derived file reproduces the complete source file.
- No marker, placeholder, question, image link, formula, or answer-source mapping is left incomplete.
- Detailed explanations do not use routine numbered lists excessively, and short-answer blocks do not contain forced line breaks without a logical or readability reason.

Report the unchanged source path, the new output path, and counts for total questions, fully sourced solutions, sourced answers with generated explanations, fully generated solutions, unresolved questions, and answer conflicts.
