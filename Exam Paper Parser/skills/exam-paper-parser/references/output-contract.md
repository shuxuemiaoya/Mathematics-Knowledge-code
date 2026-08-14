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
