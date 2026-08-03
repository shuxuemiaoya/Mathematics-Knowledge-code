---
name: question-type-markdown
description: Apply Markdown-only organization to a generated Question Type Graph corpus while preserving every word, symbol, formula, number, link, image, table, and source sequence. Use after optional answer matching and before Canvas or final audit.
---

# Question Type Markdown

Read `references/preservation-contract.md`.

```powershell
python scripts/standardize_markdown.py `
  "<profile>" "<staging>/markdown-standardization-report.json"
```

Normalize line endings, trailing spaces, blank runs, and heading spacing only. Compare lexical signatures before publication and fail on any content change. Never perform OCR correction in this stage; use a separate source-bound review artifact.
