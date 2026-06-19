# Stage 2 Preservation-Safe Markdown Content Processor

你的任务是输出一个完整 Python 文件，在 Stage 1 已经确定标题结构后，对 Markdown 正文做保守的格式规范化。

最终只输出完整 Python 文件源码。不要输出 Markdown 代码块、JSON、解释、伪代码、占位符或未完成代码。

## Immutable Content

- Heading lines are immutable. Preserve every complete H1-H6 line exactly, including text, spacing, and `#` count.
- Preserve every Markdown image reference exactly. Never delete an image, change its path, convert it to HTML, move it, or combine it into a table.
- Preserve every <details>...</details> block exactly, including all nested content.
- Preserve YAML frontmatter, fenced code, inline code, display math, inline math, Markdown tables, HTML blocks, Obsidian links/embeds, callouts, and template variables exactly.
- Do not delete, summarize, translate, reorder, merge, split, or rewrite educational content.
- Do not change formulas, answers, question order, option order, or mathematical meaning.
- Do not create or delete files other than writing the sandbox Markdown candidate in place.

## Allowed Normalization

- Conservative whitespace normalization outside immutable content.
- Remove redundant Markdown emphasis markers only when the enclosed text and line structure remain unchanged.
- Correct an obvious formatting typo only when no content is added or removed.
- If a proposed change might affect protected content or meaning, leave it unchanged.
- An identity transformation is valid when the sample does not justify a safe deterministic change.

## Required Python Contract

- The first line must be `import os`.
- Include `from pathlib import Path` and `import re`.
- Use only `os`, `pathlib`, and `re`; never import `sys`, `shutil`, `subprocess`, networking modules, or third-party packages.
- Define `get_target_root()`, `protect_blocks()`, `restore_blocks()`, `replace_in_file()`, and `main()`.
- The source must contain `def get_target_root`, `def protect_blocks`, `def restore_blocks`, `def replace_in_file`, and `def main` definitions.
- `get_target_root()` must use built-in `input()` to read the sandbox root from stdin.
- `main()` recursively processes only `.md` files under the sandbox root and skips `.git`, `node_modules`, `.obsidian`, `.trash`, and `__pycache__`.
- `protect_blocks()` must protect all immutable regions before normalization; `restore_blocks()` must restore them byte-for-byte.
- `replace_in_file()` reads and writes UTF-8 and writes only when content changed.
- Never create backups, reports, logs, or side files.
- Never access paths outside the supplied sandbox.
- End with `if __name__ == "__main__": main()`.

再次强调：禁止删除或改写标题行、图片引用、`<details>`、公式、表格和其他受保护内容，它们必须完全不变。最终只输出完整 Python 文件，不要输出 JSON。
