# TOC Detection Prompt

You are identifying the exact line numbers where the Table of Contents (TOC) starts and ends (where the main text begins) in a Markdown document.

The input document contains the first 20 pages of the Markdown file, with each line prepended with its 1-indexed line number in the format:
`<line_number>: <line_content>`

Your goal is to output a JSON object containing:
- `toc_start_line`: The line number where the table of contents starts (e.g. '# 目录' or the first TOC item). If no TOC is found in the document, return null.
- `main_text_start_line`: The line number where the main text begins (usually begins with the first actual chapter heading, e.g. '# 第一章').

Return JSON only with this shape:

```json
{
  "toc_start_line": 15,
  "main_text_start_line": 238,
  "reason": "The TOC starts at line 15 with '# 目录' and the main text begins at line 238 with '# 第七章 相交线与平行线'."
}
```

Important:
- Return ONLY a valid JSON object. Do not include markdown code block markers (like "```json") or any explanation outside the JSON.
- The line numbers MUST match the prefix line numbers exactly.
- Ensure that main_text_start_line is always an integer, and toc_start_line is either an integer or null.

