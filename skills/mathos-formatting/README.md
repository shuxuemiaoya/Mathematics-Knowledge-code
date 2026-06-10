# mathos-formatting

Status: operational.

This repo-local skill manages adaptive Markdown formatting for MathOS.

The workflow uses the LLM as a senior engineer that creates reusable formatting artifacts from samples:

1. `inspect` reads a Markdown file and reports headings, table-of-contents signals, h1 sections, and protected blocks.
2. `learn-from-provider` performs the two-stage DeepSeek learning workflow: TOC sample to heading rules, then complete H1 sample to image/text cleaner. It stops when TOC is not found and writes only candidate backups and learning artifacts.
3. `candidate-from-artifacts` applies generated heading rules and a generated Python cleaner only to a fresh candidate backup.
4. The user reviews the candidate backup and report.
5. `approve` saves the heading rules, cleaner, samples, approval note, and metadata under `plugins/approved/<plugin-id>/`.
6. `apply-approved` reuses a saved program without another provider call.

Original Markdown files are not modified during learning or approved reuse. Approved programs start with `manual-only` scope until real-world review justifies broader automation.

