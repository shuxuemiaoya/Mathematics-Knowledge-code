# TOC Verbatim Extraction Prompt

Identify the complete table of contents in the numbered first-20-page Markdown sample.

The input document contains the first 20 pages of the Markdown file, with each line prepended with its 1-indexed line number in the format:
`<line_number>: <line_content>`

Return only the complete contiguous TOC span, preserving every numbered input line exactly.

Requirements:

- Begin at the earliest TOC title or entry, even when the first recognized TOC page header appears later in the span.
- Include that later internal `# 目录` or `# CONTENTS` anchor unchanged; the complete span must contain at least one recognized TOC page header.
- Do not prepend cover, preface, author, or date lines before the earliest TOC title or entry.
- Include every TOC line through the final TOC entry.
- Preserve line-number prefixes, text, whitespace, punctuation, OCR output, blank lines, and ordering exactly.
- A wrapped TOC entry may place its title fragment on one line and its page reference on the next nonblank line; include both unchanged lines.
- A multi-page TOC may contain repeated `# 目录` or `# CONTENTS` page headers; include them only while TOC entries continue after them.
- End the span at the final TOC entry and stop before the first main-text line, body exercise, answer, or body heading.
- Do not return the remainder of the sample merely because the TOC begins before the twentieth page.
- Do not correct OCR, normalize titles, rewrite text, omit TOC entries, or include cover pages, prefaces, headers, footers, or main-text lines.
- Do not add Markdown fences, JSON, explanations, or any text absent from the input.
