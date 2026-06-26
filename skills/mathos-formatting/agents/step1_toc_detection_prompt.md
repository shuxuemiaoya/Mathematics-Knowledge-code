# TOC Verbatim Extraction Prompt

Identify the complete table of contents in the numbered first-20-page Markdown sample.

The input document contains the first 20 pages of the Markdown file, with each line prepended with its 1-indexed line number in the format:
`<line_number>: <line_content>`

Return only the complete contiguous TOC span, preserving every numbered input line exactly.

Requirements:

- Begin at the earliest TOC title or entry (e.g., Chapter 1 title), even when the first recognized TOC page header (like `## 目录`) appears later in the span.
- Preceding lines that list chapter/section titles followed by page numbers (e.g., `/2`, `/8`, `P1`, `.. 2`) are part of the TOC. You must include them and start at their beginning.
- Include that later internal `# 目录` or `# CONTENTS` anchor unchanged; the complete span must contain at least one recognized TOC page header.
- Do not prepend cover, preface, author, or date lines before the earliest TOC title or entry.
- Include every TOC line through the final TOC entry.
- Preserve line-number prefixes, text, whitespace, punctuation, OCR output, blank lines, and ordering exactly.
- A wrapped TOC entry may place its title fragment on one line and its page reference on the next nonblank line; include both unchanged lines.
- A multi-page TOC may contain repeated `# 目录` or `# CONTENTS` page headers; include them only while TOC entries continue after them.
- End the span at the final TOC entry and stop before the first main-text line, body exercise, answer, or body heading.
- The TOC response must end at the final valid TOC entry that contains a page reference (e.g., `/ 198` or `P198`). Do not include any subsequent trailing headings that lack page numbers (such as "学习印记", postscripts, appendices, or body content headers).
- Do not correct OCR, normalize titles, rewrite text, omit TOC entries, or include cover pages, prefaces, headers, footers, or main-text lines. Do not return the remainder of the sample.
- Do not add Markdown fences, JSON, explanations, or any text absent from the input.
