---
name: mathos-formatting
description: Use when inspecting, learning, previewing, approving, or reusing adaptive Markdown formatting programs for MathOS generated Markdown.
---

# MathOS Formatting Operator

Status: operational.

Use this adaptive Markdown formatting operator after PDF or Word conversion when Markdown needs repeatable formatting cleanup.

Unknown file types must use candidate backup learning:

1. Run `inspect` to extract headings, table-of-contents signals, h1 sections, and protected blocks.
2. Run `learn-from-provider` to execute the two-stage DeepSeek learning workflow: TOC sample to heading rules, then complete H1 sample to image/text cleaner. This stops when a TOC is not found and protects structural heading lines, failing closed if heading protection is violated.
3. Alternatively, manually generate or provide regex heading rules and a Python content cleaner, then run `candidate-from-artifacts` to create the candidate backup.
4. Ask the user to review the backup result and choose approve, revise, or discard.
5. Run `approve` only after explicit user approval.
6. Reuse approved programs with `apply-approved`; this still writes a fresh candidate backup and does not modify the original Markdown file.

Do not modify original Markdown files during unknown-type learning. Delete and recreate the candidate backup for each revision cycle.

Approved reusable programs live under `plugins/approved/` and start as `manual-only`.

Provider settings are read from the workspace `.env`. Never print or save secret values.
