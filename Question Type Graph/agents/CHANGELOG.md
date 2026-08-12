# Question Type Graph Agent Change Log

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
