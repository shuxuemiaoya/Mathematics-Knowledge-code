# Content Cleaner Prompt

You are generating a conservative Python Markdown formatting plugin for MathOS.

Primary rule: preserve mathematical and educational source content. Formatting means normalization, not deletion, rewriting, summarization, translation, simplification, or reordering.

Return one Python file only. It must expose:

```python
PLUGIN_ID = "descriptive_id"
PLUGIN_VERSION = "1.0.0"

# Both "warnings" and "summary" in the return dict MUST be flat lists of strings.
def analyze(markdown: str) -> dict:
    return {"warnings": ["warning string"], "summary": ["summary string"]}

def clean(markdown: str) -> str:
    return markdown
```

Allowed edits:

- Normalize redundant blank lines.
- Normalize surrounding whitespace without changing non-whitespace content.
- Normalize image alt text while preserving every image path and image line.
- Fix obvious Markdown spacing around paragraphs, lists, and headings without changing the text.

Forbidden edits:

- Do not delete image links or image Markdown lines.
- Do not delete `<details>` blocks or any content inside `<details>` blocks.
- Do not delete <details> blocks.
- Do not delete or modify formulas, inline math, display math, or math delimiters.
- Do not modify formula content.
- Do not delete tables or table-like lines.
- Do not delete examples, exercises, solutions, theorem-like blocks, notes, explanations, list items, or Chinese textbook content.
- Do not rewrite, translate, summarize, infer, simplify, or reorder content.
- Do not delete any non-empty source line unless the line contains only redundant whitespace.

If something looks suspicious, report it in `analyze()` as a warning. Do not fix risky content in `clean()`.

The plugin receives Markdown text and returns Markdown text. Do not read files, write files, access environment variables, call subprocesses, or use network APIs.

The input sample is one complete H1 section after heading normalization. The cleaner is for conservative image/text formatting only and must not modify heading lines.
