# Markdown standardization contract

Canonical source:

```text
C:\Users\Oven\OneDrive\桌面\新建文件夹 (3)\概念提取与Markdown排版美化.md
```

This reference operationalizes Task 2 of the user-supplied contract. If this
file and the canonical source disagree, the canonical source wins.

For new textbook profiles, treat the passed lesson-flow manifest as the
authority for teaching-block ownership and order. Formatting may express those
blocks but must not merge, move, or reclassify them from keyword matches. A
functional heading/label, exposition or definition cue, worked-example label,
or practice heading that begins a reviewed block also terminates the preceding
block.

## Protected content

Preserve content and source order. Never change H1-H3 headings, table data,
link destinations, image paths, formula numbering, or intermediate reasoning.
Keep a real blank line around headings, formulas, images, tables, and callouts.
Compress runs of three or more blank lines. Keep each question's stem, images,
choices, answer, and explanation adjacent.

## Callout eligibility

Convert only functionally appropriate H4-H6 textbook columns and worked
examples. Ordinary questions, ordinary exercises, and continuous exposition
remain ordinary Markdown. Decide by function, not keyword alone; leave an
ambiguous block unchanged.

| Function | Callout |
| --- | --- |
| observation, thinking, discussion, question | `> [!question]` |
| exploration, experiment, discovering a rule | `> [!question]` |
| introduction, guidance, situational context | `> [!info]` |
| worked example | `> [!example]-` |
| analysis, approach, hint inside an example | `> > [!tip]-` |
| solution, proof, explanation inside an example | `> > [!success]-` |
| warning, error-prone condition, special note | `> [!warning]` |
| background, marginal note, supplementary material | `> [!tip]` |
| analogy, comparison, auxiliary explanation | `> [!note]` |
| summary, induction, method, rule, core conclusion | `> [!summary]` |
| unextracted theorem, axiom, property, core knowledge | `> [!summary]` |

Every top-level callout is a complete container. Every body line, formula,
image, HTML line, table line, caption, and intentional blank line begins with
`>`. A blank line inside a callout is represented by a line containing `>`.
Do not emit a marker followed by unquoted body text.

Emit the functional label once. If the source block begins with the same
`思考`, `观察`, `情景引入`, or equivalent label used in the callout marker,
remove that presentation-only duplicate from the body. Never place a later
functional heading, formal definition, worked-example label, or practice
heading inside the preceding callout.

## Worked examples

The whole example, including its stem, belongs inside one collapsed
`example` callout. When the stem begins on the example-label line, keep the
one-line stem on the marker line to match the approved textbook exemplar.
Analysis/approach/hint and solution/proof/explanation are
collapsed depth-two callouts:

```markdown
> [!example]- 例题 1 题干内容
>
> > [!tip]- 分析
> > 分析内容
>
> > [!success]- 解
> > 解答内容
```

`> >` may appear only inside a top-level callout. Every nested body line,
formula, image, HTML line, table line, and intentional blank line uses `> >`.

For non-example material, use a nested callout only when the source forms a
clear paired structure such as question/exploration/observation/attempt
followed by its answer, derivation, rule, or conclusion. A conclusion keyword
by itself does not justify nesting.

An approved style reference is evidence for marker compactness and nested
reasoning form, but never permission to copy a broken or discontinuous
callout. Every emitted body remains continuously quoted.

## Other presentation rules

- Prefer inline formulas; use display formulas for important conclusions.
- Preserve circled formula numbers exactly.
- Keep analysis, solution, proof, explanation, and conclusion distinct; remove
  unnecessary blank lines inside a reasoning chain without deleting steps.
- Prefer meaningful multi-image layouts before centering a single image.
- Preserve image filenames, folders, and paths. Keep captions immediately
  after their image and keep callout-owned images/captions inside the callout.
- Use Markdown tables for simple data and HTML tables for merged cells,
  embedded images, multiline formulas, or layouts Markdown cannot represent.
  A callout-owned table stays inside the callout.
- Convert real footnote markers and definitions to Markdown footnotes without
  confusing formula numbering with footnotes.
