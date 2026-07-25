# Markdown Standardization Prompt Contract

This reference isolates Task 2 from the supplied `概念提取与Markdown排版美化.md` prompt.

## Global invariants

1. Content completeness has priority.
2. Prefer meaningful multi-image layout before single-image centering.
3. Never change H1-H3 text/order, table data, hyperlink destinations, image destinations, formula numbering, or source meaning.
4. Do not extract concepts in this stage.

## Paragraphs, blank lines, and lists

- Keep a blank line around headings, display formulas, image blocks, and tables.
- Compress three or more consecutive blank lines to one blank line.
- Avoid excessive blank lines inside one question.
- Keep stems, images, options, answers, and explanations adjacent.
- Use one numbering style per list level.
- Indent nested lists and do not split a continuous list into unrelated paragraphs.

Use one consistent choice style within a file:

```markdown
A. 选项一  
B. 选项二  
C. 选项三  
D. 选项四
```

or:

```markdown
(A) 选项一  (B) 选项二  (C) 选项三  (D) 选项四
```

## Formulas

- Prefer inline formulas by default.
- Use display formulas for important standalone conclusions.
- Preserve original circled or other formula numbers such as `①②③④`.
- Never convert formula numbers into footnotes.

## Callouts

Convert only functionally appropriate H4-H6 columns and worked examples. Do not convert ordinary questions or exercises.

| Function | Callout |
| --- | --- |
| observation, thinking, discussion, question | `> [!question]` |
| exploration, experiment, operation | `> [!question]` |
| introduction or context | `> [!info]` |
| worked example | `> [!example]-` |
| example analysis or hint | `> > [!tip]-` |
| example solution or proof | `> > [!success]-` |
| warning or restriction | `> [!warning]` |
| background or aside | `> [!tip]` |
| comparison or analogy | `> [!note]` |
| summary, rule, method, conclusion | `> [!summary]` |
| unextracted theorem, axiom, or property | `> [!summary]` |

Judge function before keywords. If function is unclear, keep ordinary Markdown.

Require a real blank line before every top-level callout.

Use an example structure:

```markdown
> [!example]- 例题 1
> 题干内容
>
> > [!tip]- 分析
> > 分析内容
>
> > [!success]- 解
> > 解答内容
```

Rules:

- Put the complete example stem inside the parent example callout.
- Put analysis/hints and solutions/proofs in separate nested callouts.
- Prefix every nested line, formula, image, HTML line, and blank line with `> >`.
- Never use `> >` without a parent callout.
- Outside examples, nest only when a clear question/exploration is followed by its answer, derivation, rule, or conclusion.

## Images

- Never change image filenames, folder names, or path strings.
- Use `<img src="原路径"/>` when changing only the embedding form.
- Put related subfigures, transformations, comparisons, consecutive figures, or images sharing one figure number side by side.
- Preserve subfigure labels such as `(1)`, `(2)`, `甲`, `乙`, `①`, and `②`.
- Keep captions and figure numbers immediately after their image.
- Keep images and captions inside their owning callout.

For a standalone image:

```markdown
<div align="center">
  <img src="原路径" width="55%" />
  <br />
  图号或题注
</div>
```

## Tables

- Use Markdown tables for simple data.
- Use HTML tables for merged cells, images, multiline formulas, layouts Markdown cannot render, or aligned multi-image rows.
- Preserve all table data.
- Keep a table indented with its owning list item, question, or callout.

## Reasoning, proofs, and solutions

- Remove unnecessary blank lines while keeping the process compact.
- Preserve every condition, intermediate conclusion, reason, and inference.
- Never replace a proof or solution with only its conclusion.
- Keep analysis, solution, proof, explanation, and conclusion distinguishable.
- Use nested callouts for those parts only when they belong to an example.

## Footnotes

Convert visible footnote markers:

```markdown
《九章算术》①
```

to:

```markdown
《九章算术》[^1]
```

and convert the matching bottom note:

```markdown
①《九章算术》
```

to:

```markdown
[^1]: 《九章算术》
```
