# TOC Verbatim Extraction Prompt

Identify the complete table of contents in the numbered first-20-page Markdown sample.

The input document contains the first 20 pages of the Markdown file, with each line prepended with its 1-indexed line number in the format:
`<line_number>: <line_content>`

Return only the complete contiguous TOC span, preserving every numbered input line exactly.

Requirements:

- Begin with the TOC heading such as `# 目录` or `# Contents`.
- Include every TOC line through the final TOC entry.
- Preserve line-number prefixes, text, whitespace, punctuation, OCR output, blank lines, and ordering exactly.
- Do not correct OCR, normalize titles, rewrite text, omit TOC entries, or include cover pages, prefaces, headers, footers, or main-text lines.
- Do not add Markdown fences, JSON, explanations, or any text absent from the input.
