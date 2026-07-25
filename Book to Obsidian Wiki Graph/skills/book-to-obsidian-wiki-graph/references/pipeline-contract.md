# Standalone Modular Pipeline

| Stage | Owner | Input | Output | Gate |
| --- | --- | --- | --- | --- |
| Intake | `book-graph-intake` | source and target | inventory, profile | frozen source identity |
| PDF conversion | `book-pdf-to-markdown` | PDF and profile | raw Markdown and assets | forced OCR, complete pages/assets |
| TOC formatting | `book-toc-formatting` | raw Markdown and printed TOC | TOC manifest, formatted Markdown, report | every TOC entry matched; other headings below H3 |
| TOC splitting | `book-toc-splitting` | formatted Markdown, TOC and split manifests | categorized notes, parent links, coverage | every TOC key and H4-H6 heading reviewed; numbered subsections and section exercises split; all targets resolve |
| Concepts | `book-graph-concepts` | split notes and coverage | concept notes and manifest | formal definitions complete and linked |
| Standardization | `book-graph-markdown` | concept-linked notes | standardized notes | protected fields unchanged; no residual functional headings or raw worked-example markers |
| Pre-audit | `book-graph-audit` | complete note corpus | audit report | `status: passed` |
| Canvas | `book-graph-canvas` | passed notes and graph plan | `.canvas` | compiler passes |
| Final audit | `book-graph-audit` | final corpus | final report | `status: passed` |

TOC formatting and TOC splitting are one uninterrupted transition: a passed formatting report triggers splitting immediately.

JSON artifacts carry `schema_version`, absolute profile path, and frozen source digest. Formatting and splitting additionally carry the digest of their immediate Markdown input.

The coordinator owns sequence only. Component skills own behavior, scripts, prompts, and validation.
