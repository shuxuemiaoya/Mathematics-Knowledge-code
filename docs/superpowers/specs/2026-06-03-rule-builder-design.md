# LLM-Assisted Rule Builder for mathos-formatter

When a user encounters a `.md` file that doesn't match any existing formatter template, the Rule Builder automates the creation of a new `BaseFormatter` subclass via two LLM calls.

## Problem

Currently, adding support for a new textbook format requires manually writing a Python formatter class with regex rules. This is slow and repetitive — the pattern is always the same: analyze the TOC for heading hierarchy, then study the content for callout/spacing patterns. An LLM can do both analyses and generate the boilerplate.

## Design

### Two-Phase LLM Generation

**Phase 1 — Heading Rules from TOC:**

1. Extract the first N lines (default 600, ~20 pages) from the first `.md` file in `--dir`
2. Locate the literal printed TOC section (lines with `......` / `……` + page numbers, or `目录` marker)
3. If no explicit TOC found, fall back to extracting all `#` heading lines as structural hints
4. Send TOC content to DeepSeek with the Phase 1 prompt template
5. LLM returns a Python class inheriting `BaseFormatter` with heading mapping rules + TOC deletion
6. Validate via `ast.parse()`: must be valid Python, single class inheriting `BaseFormatter`, has `format_string` method
7. Display generated code to user for review — options: `Y` (accept), `n` (reject + exit), `r` (regenerate)

**Phase 2 — Beautification Rules from H1 Sample:**

1. Apply Phase 1 heading rules **in-memory** (no disk writes) to get heading-corrected content
2. Extract the first H1 section (all content from first `# ` to second `# `)
3. Send H1 content + Phase 1 class to DeepSeek with the Phase 2 prompt template
4. LLM returns the **updated** class with beautification rules added (callouts, spacing, figure handling)
5. Same validation + user review flow as Phase 1
6. Save the final class to `src/mathos/formatter/<name>.py`

### CLI Integration

The Rule Builder is triggered from the existing interactive mode selection in `cli.py`:

```
mk-format --dir "C:\path\to\textbook"

  → 未指定转换模式。检测到以下已存在的格式修改方案：
    1. textbook
    2. exercise
    3. renjiao-highschool-textbook
    ...
    0. 都不适用，创建新规则

User picks 0 →
  → 请输入新格式化器的名称 (英文, 如 beijing-algebra): ▌
  → [Phase 1] 正在提取目录...
  → [Phase 1] 请审核生成的标题规则...
  → 确认? [Y/n/r]: ▌
  → [Phase 2] 正在提取章节内容...
  → [Phase 2] 请审核生成的美化规则...
  → 确认? [Y/n/r]: ▌
  → ✅ 已保存: src/mathos/formatter/<name>.py
  → ✅ 已注册模式: <name>
  → 正在以 dry-run 模式运行...
```

### Auto-Discovery

A new `discovery.py` module replaces the hardcoded `FORMATTERS` dict. It scans `src/mathos/formatter/` for all `.py` files, imports them, finds classes inheriting `BaseFormatter`, and registers them with kebab-case mode names derived from the class name:

- `BeijingAlgebraFormatter` → `beijing-algebra`
- `RenjiaoHighschoolTextbookFormatter` → `renjiao-highschool-textbook`

The existing hardcoded entries remain as fallbacks to avoid breaking anything.

### Editable Prompt Templates

LLM prompts are stored as editable Markdown files in `src/mathos/formatter/prompts/`:

- `phase1_heading_rules.md` — system prompt for heading rule generation
- `phase2_beautification.md` — system prompt for beautification rule generation

Templates use `{placeholders}` filled at runtime:

| Placeholder | Content |
|---|---|
| `{base_formatter_source}` | Source code of `BaseFormatter` from `core.py` |
| `{example_formatter_source}` | Source code of `RenjiaoHighschoolTextbookFormatter` as a reference |
| `{toc_content}` | Extracted TOC content from the `.md` file |
| `{phase1_code}` | Phase 1 generated class (for Phase 2 prompt) |
| `{h1_section_content}` | Extracted first H1 section content |

### Generated Formatter Structure

All generated formatters follow this exact pattern:

```python
import re
from .core import BaseFormatter

class NewTextbookFormatter(BaseFormatter):
    def __init__(self):
        super().__init__()
        # Pre-compiled regexes only
        self.re_toc_block = re.compile(...)
        self.re_chapter = re.compile(...)
        
    def format_string(self, text: str) -> str:
        new = self._replace_common(text)
        # Phase 1: TOC deletion + heading restructuring
        # Phase 2: Beautification rules
        return self._cleanup_empty_lines(new)
```

## File Changes

### New Files

| File | Purpose |
|---|---|
| `src/mathos/formatter/rule_builder.py` | Two-phase LLM orchestrator: TOC extraction, H1 extraction, LLM calls, AST validation, file saving |
| `src/mathos/formatter/discovery.py` | Auto-scan `formatter/` for `BaseFormatter` subclasses, register as CLI modes |
| `src/mathos/formatter/prompts/phase1_heading_rules.md` | Editable Phase 1 system prompt template |
| `src/mathos/formatter/prompts/phase2_beautification.md` | Editable Phase 2 system prompt template |

### Modified Files

| File | Changes |
|---|---|
| `src/mathos/formatter/cli.py` | Replace hardcoded `FORMATTERS` with `discovery.discover_formatters()`. When user picks `0`, launch `RuleBuilder` instead of exiting. |
| `src/mathos/formatter/__init__.py` | Export `RuleBuilder` and `discover_formatters` |

### Unchanged Files

`core.py`, `textbook.py`, `exercise.py`, `renjiao_highschool_textbook.py`, `logger.py` — no changes.

## Error Handling

| Scenario | Behavior |
|---|---|
| No `.md` files in `--dir` | Exit with error message |
| No TOC found in first 600 lines | Fall back to extracting all `#` heading lines |
| LLM returns invalid Python | Catch `SyntaxError`, show error, offer `r` to regenerate |
| LLM class doesn't inherit `BaseFormatter` | Validate via AST, reject and offer regeneration |
| `DEEPSEEK_API_KEY` not set | Exit with message pointing to `.env` |
| User rejects 3+ times | Offer to exit and write manually |
| Generated formatter crashes on dry-run | Catch exception, show traceback, offer `r` or `q` |

## Verification Plan

### Automated Tests

- **`test_discovery.py`**: Place a mock formatter file in a temp directory, verify `discover_formatters()` finds it with correct mode name
- **`test_rule_builder_extract.py`**: Test `_extract_toc()` with sample `.md` files containing various TOC formats (page numbers, `......`, `……`, no TOC)
- **`test_rule_builder_validate.py`**: Test AST validation with valid code, invalid syntax, missing `BaseFormatter` inheritance, missing `format_string`
- **`test_rule_builder_integration.py`**: Mock LLM responses, verify end-to-end flow: TOC extraction → code generation → validation → file save → discovery

### Manual Verification

- Run Rule Builder against a real textbook `.md` file
- Review generated formatter code for correctness
- Run `mk-format --dir "..." --mode <new-mode> --dry-run` to verify output quality
