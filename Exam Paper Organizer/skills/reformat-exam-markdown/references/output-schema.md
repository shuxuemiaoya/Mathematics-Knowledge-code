# Output schema

Keep the question paper and reference answers as two distinct top-level sections. Use numbered Markdown items rather than headings for question numbers.

```markdown
---
title: "Paper title"
subject: "Mathematics"
document_type: "exam-with-separate-answers"
---

# Paper title

## Instructions

1. Original instruction text.

## I. Multiple-choice questions

1. Question stem.

   ![](images/question-1.png)

   - A. First choice
   - B. Second choice
   - C. Third choice
   - D. Fourth choice

<div style="page-break-after: always;"></div>

<!-- answer-section -->

# Mathematics Answer Key

## I. Multiple-choice questions

1. C　2. B　3. A　4. D

## III. Fill-in-the-blank questions

12. $\sqrt{7}$　13. $\dfrac{2\sqrt{6}}{5}$　14. $\dfrac{\sqrt{3}}{7}$

## IV. Worked-response questions

15. (13 points)

   (1) Proof text.

   Because ...

   Therefore ...
```

For Chinese papers, use the source-language labels `注意事项` and `<科目>参考答案`. Keep original question-type headings rather than translating them.

## Invariants

- Preserve one question entry and one answer entry for each source question number.
- Start every entry with the literal form `<number>. `; do not emit `### <number>` headings.
- Keep the entire question paper before `<!-- answer-section -->`; keep all short answers and solutions after it.
- Place the exact line `<div style="page-break-after: always;"></div>` immediately before `<!-- answer-section -->`.
- Put the numbered answers for each multiple-choice or fill-in section on one source line when practical, separated by ideographic spaces. Do not compact worked solutions.
- Place the complete question stem and subquestions first, then one grouped image block, then A–D choices.
- Keep each worked-solution subpart and logical transition in its own indented paragraph.
- Use `\dfrac` instead of `\frac` to give fractions a more readable display-style bar without changing their numerator or denominator.
- Keep valid image destinations unchanged. Rewrite a broken relative destination only when the same asset is proven to exist at the corrected path.
- Never fabricate missing OCR text or an absent answer; expose it in the JSON report for manual review.

## Logical transitions

Start a new solution paragraph before cues such as `由`, `因为`, `所以`, `又`, `则`, `故`, `即`, `解得`, `因此`, `可得`, `易知`, `易得`, `两边平方得`, `代入并整理`, `当`, `设`, and `记`. Also start a new paragraph after a scoring marker such as `……4 分` when more reasoning follows.

Review ambiguous OCR manually, especially duplicated or missing question numbers and damaged mathematical expressions.
