---
name: mathos-formatting
description: Use when learning, previewing, approving, or reusing adaptive Markdown formatting programs for MathOS generated Markdown.
---

# MathOS Formatting Operator

Use this skill for adaptive Markdown formatting after PDF or Word conversion.

Unknown file types must use backup-only learning:

1. Extract headings and the table-of-contents block.
2. Ask the configured provider for regex heading rules.
3. Create a fresh candidate backup from the original Markdown file.
4. Apply heading rules only to the candidate backup.
5. Extract one complete h1 section from the candidate.
6. Ask the configured provider for a Python content cleaner plugin.
7. Run the plugin only on the candidate backup.
8. Generate a diff and warning report.
9. Ask the user to approve, revise, or discard.

Do not modify original Markdown files during unknown-type learning.

Save reusable programs only after explicit user approval.

Provider settings are read from `C:\Mathematics-Knowledge\.env`. Never print or save secret values.
