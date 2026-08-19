# Output contract

The graph root contains:

```text
<paper>.md
images/
<section>/<section>.md
<section>/题目/Q00000001.md
<section>/题目/answers/Q00000001A1.md
```

Each question note has source identity, printed number, page/bbox when available,
body digest, `重要程度: "重要"`, a source block, and exactly one answer embed.

Each answer note records whether its exact answer came from an explicit answer
marker, an explicit publisher conclusion, or PDF-text recovery, and has exactly
this callout hierarchy:

```markdown
> [!faq]- <paper>解析
>
> > [!success]- **【答案】** <exact result or 详见解析>
>
> > [!note]- **【分析】**
> > ...
>
> > [!note]- **【解析】**
> > ...
```

Choice questions require an exact A-F result. `详见解析` is allowed only for
non-choice questions with a substantive publisher solution.

The analysis callout contains only the publisher's strategy overview. Preserve
all `【小问 n 详解】` markers and their derivations in the explanation callout;
never duplicate `【分析】` inside the analysis body.

The final audit requires continuous global numbering, section-count agreement,
one question and answer note per number, stable embeds, intact source digests,
resolved local images, unchanged source hashes, no unexpected `.canvas` files,
and no unsafe generated path characters.

## Deterministic Parser Contract

- **Standalone & Tail Answer Section Recovery**: `extract_standalone_answers` extracts short fill-in answers (`1. \pi`), choice HTML tables (`<td>13</td><td>C</td>`), choice conclusions (`故选：D`), fill conclusions (`故答案为：-5`), and sequential solution blocks (`【分析】... 【解答】...`) when answer keys are placed at the top or bottom of the document.
- **Preamble Guideline Filter**: Ignores preamble rating guidelines containing `评分标准`, `评阅`, `本解答列出`, `阅到底` to prevent misattributing rules to Q1/Q2.
- **Sub-question & Section Isolation**: Differentiates sub-questions `(1)`, `(2)`, `(3)` in free-response solutions from top-level questions `(1)`, `(2)`, `(3)` in choice/fill sections by checking question stem keywords (`已知`, `若`, `设`, `在`, `某`, `___`) and choice options `(A)`, `(B)`.
- **Numerical & Province Section Normalization**: Normalizes numerical range headers (`第12题至第15题`) and special province section titles (`【必做题】`, `【选做题】`, `【附加题】`) into canonical sections (`选择题`, `填空题`, `解答题`).
- **Marker Splitting & Regex Safety**: Requires brackets `【` / `[` or colons `:` / `：` for section markers, preventing plain words (e.g. `目标函数得\n答案`) from breaking line parsing. Preserves LaTeX math symbols starting with `\` (`\triangle`, `\left`, `\vec`, `\alpha`, `\int`, `\lim`, `\frac`, `\log`, `\cos`, `\sin`, `\sqrt`) at the beginning of question lines.
