# TOC Detection Prompt

You are identifying the exact line number where the table of contents ends and the main text begins in a Markdown document.

The input document contains the first 20 pages of the Markdown file, with each line prepended with its 1-indexed line number in the format:
`<line_number>: <line_content>`

Your goal is to output a JSON object containing the line number where the main text begins. The main text usually begins with the first actual chapter heading (e.g. `# 第一章` or similar). Everything before this line (including the Table of Contents, cover, or preface) should be considered as preceding content and will be deleted.

Return JSON only with this shape:

```json
{
  "main_text_start_line": 238,
  "reason": "The main text begins at line 238 with heading '# 第七章 相交线与平行线'."
}
```

Important:
- Return ONLY a valid JSON object. Do not include markdown code block markers (like ```json) or any explanation outside the JSON.
- The `main_text_start_line` MUST be the line number from the prepended line prefix.
- Ensure the line number is an integer.
