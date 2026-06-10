---
name: mathos-formatting
description: Use when inspecting, learning, previewing, approving, or reusing adaptive Markdown formatting programs for MathOS generated Markdown.
---

# MathOS Formatting Operator

Status: operational.

Use this adaptive Markdown formatting operator after PDF or Word conversion when Markdown needs repeatable formatting cleanup.

Unknown file types must use candidate backup learning:

1. Run `inspect` to extract headings, table-of-contents signals, h1 sections, and protected blocks.
2. Generate or provide regex heading rules from the heading and TOC sample.
3. Generate or provide a Python content cleaner from one h1 section sample.
4. Run `candidate-from-artifacts` to create a fresh candidate backup, apply rules, run the text-only plugin, and write a review report.
5. Ask the user to review the backup result and choose approve, revise, or discard.
6. Run `approve` only after explicit user approval.
7. Reuse approved programs with `apply-approved`; this still writes a fresh candidate backup and does not modify the original Markdown file.

`learn-from-provider` performs the two-stage DeepSeek learning workflow: TOC sample to heading rules, then complete H1 sample to image/text cleaner. It stops when TOC is not found and writes only candidate backups and learning artifacts.

Do not modify original Markdown files during unknown-type learning. Delete and recreate the candidate backup for each revision cycle.

Approved reusable programs live under `plugins/approved/` and start as `manual-only`.

Provider settings are read from the workspace `.env`. Never print or save secret values.

