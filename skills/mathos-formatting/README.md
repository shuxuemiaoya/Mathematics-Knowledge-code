# mathos-formatting

Status: active after implementation.

This repo-local skill manages adaptive Markdown formatting for MathOS.

The skill uses a two-step LLM-assisted workflow:

1. Extract headings and table-of-contents samples so the provider can propose regex heading rules.
2. Extract one h1 section so the provider can propose a Python content cleaner.

Unknown file types are modified only through fresh candidate backups. Approved reusable programs are saved under `plugins/approved/` only after user approval.
