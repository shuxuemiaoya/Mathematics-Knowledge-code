---
name: mathos-formatting
description: Use when inspecting, learning, previewing, approving, or reusing adaptive Markdown formatting programs for MathOS generated Markdown.
---

# MathOS Formatting Operator

Status: operational.

Use this adaptive Markdown formatting operator after PDF or Word conversion when Markdown needs repeatable formatting cleanup.

Unknown file types must use candidate backup learning:

1. Run `inspect` to extract headings, table-of-contents signals, H1 sections, and protected blocks.
2. Run `learn-from-provider` to execute the four-stage DeepSeek learning workflow:
   - **Stage 1 (Heading Rules)**: Query the LLM to standardize TOC headings (Chapter to H1, Section to H2, etc.) and demote non-TOC headings to H4+ levels using negative lookaheads.
   - **Stage 2 (TOC Detection & Stripping)**: Extract the first 20 pages of the document, send them to the LLM to detect the boundaries of the Table of Contents (TOC), and selectively strip only the TOC block (preserving any preceding content/prefaces).
   - **Stage 3 (H1 Extraction)**: Extract the first complete H1 section from the stripped candidate.
   - **Stage 4 (Content Cleaner)**: Query the LLM to generate a Python content cleaner for image/text formatting.
3. Alternatively, manually generate or provide regex heading rules and a Python content cleaner, then run `candidate-from-artifacts` to create the candidate backup.
4. Ask the user to review the backup result and choose approve, revise, or discard.
5. Run `approve` only after explicit user approval.
6. Reuse approved programs with `apply-approved`; this still writes a fresh candidate backup.
7. The final step is to ask the user to confirm whether they are satisfied with the formatting changes. After the user confirms satisfaction:
   - Replace the original file with the modified (candidate) file.
   - Delete the temporary `mathos-formatting` directory.

Do not modify original Markdown files during unknown-type learning until the user explicitly confirms satisfaction. Delete and recreate the candidate backup for each revision cycle.


Approved reusable programs live under `plugins/approved/` and start as `manual-only`.

Provider settings are read from the workspace `.env`. Never print or save secret values.
