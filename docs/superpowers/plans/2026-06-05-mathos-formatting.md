# MathOS Adaptive Markdown Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `mathos-formatting` repo-local skill as a safe adaptive Markdown formatting operator that learns from samples, modifies only candidate backups during learning, and saves reusable Python cleaner programs only after user approval.

**Architecture:** The implementation uses a thin CLI entrypoint plus focused pure-Python modules for extraction, heading-rule execution, backup/report handling, provider calls, and plugin safety. LLM calls are isolated behind a provider adapter so tests can use fake responses and approved plugins can be reused without calling DeepSeek.

**Tech Stack:** Python standard library, `pytest`, PowerShell commands, Markdown files, JSON metadata, DeepSeek-compatible HTTP provider through settings loaded from `C:\Mathematics-Knowledge\.env`.

---

## Scope Check

This plan implements one coherent subsystem: `skills/mathos-formatting`. It includes scaffolding, extraction, heading rules, backup-only candidate runs, plugin safety, provider integration, approval, reuse, tests, and docs because these pieces must work together before the skill is safe to run on unknown Markdown files.

The plan does not implement batch promotion heuristics beyond storing `manual-only` approval metadata. Batch-eligible promotion needs reviewed real-world runs and should be added after the first operator is stable.

## File Structure

Create or modify these files:

- Create: `skills/mathos-formatting/assets/.gitkeep`
- Create: `skills/mathos-formatting/agents/heading_rules_prompt.md`
- Create: `skills/mathos-formatting/agents/content_cleaner_prompt.md`
- Create: `skills/mathos-formatting/plugins/approved/.gitkeep`
- Create: `skills/mathos-formatting/plugins/candidates/.gitkeep`
- Create: `skills/mathos-formatting/reports/.gitkeep`
- Create: `skills/mathos-formatting/references/formatting-program-format.md`
- Create: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Create: `skills/mathos-formatting/scripts/mathos_provider.py`
- Create: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Create: `skills/mathos-formatting/LICENSE.txt`
- Create: `skills/mathos-formatting/NOTICE.txt`
- Create: `skills/mathos-formatting/SKILL.md`
- Modify: `skills/mathos-formatting/README.md`
- Create: `tests/test_mathos_formatting.py`

Responsibilities:

- `mathos_formatting_core.py`: dataclasses, Markdown extraction, heading-rule validation/application, candidate backup lifecycle, diff/report generation, plugin validation/execution, approval save, approved-plugin reuse.
- `mathos_provider.py`: `.env` loading, provider request/response handling, structured LLM artifact parsing.
- `mathos_formatting.py`: CLI commands that orchestrate core and provider behavior.
- `tests/test_mathos_formatting.py`: focused safety and repeatability tests using temporary files and fake provider artifacts.
- `agents/*.md`: stable prompts for heading rules and content cleaner generation.
- `references/formatting-program-format.md`: human-readable schema for approved programs.
- `SKILL.md`: operator instructions for future Codex runs.

## Task 1: Scaffold The Formatting Skill

**Files:**
- Create: `skills/mathos-formatting/assets/.gitkeep`
- Create: `skills/mathos-formatting/agents/heading_rules_prompt.md`
- Create: `skills/mathos-formatting/agents/content_cleaner_prompt.md`
- Create: `skills/mathos-formatting/plugins/approved/.gitkeep`
- Create: `skills/mathos-formatting/plugins/candidates/.gitkeep`
- Create: `skills/mathos-formatting/reports/.gitkeep`
- Create: `skills/mathos-formatting/references/formatting-program-format.md`
- Create: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Create: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Create: `skills/mathos-formatting/scripts/mathos_provider.py`
- Create: `skills/mathos-formatting/LICENSE.txt`
- Create: `skills/mathos-formatting/NOTICE.txt`
- Create: `skills/mathos-formatting/SKILL.md`
- Modify: `skills/mathos-formatting/README.md`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write the failing scaffold test**

Add this to `tests/test_mathos_formatting.py`:

```python
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "mathos-formatting"


def test_formatting_skill_scaffold_exists():
    expected = [
        "assets/.gitkeep",
        "agents/heading_rules_prompt.md",
        "agents/content_cleaner_prompt.md",
        "plugins/approved/.gitkeep",
        "plugins/candidates/.gitkeep",
        "reports/.gitkeep",
        "references/formatting-program-format.md",
        "scripts/mathos_formatting.py",
        "scripts/mathos_formatting_core.py",
        "scripts/mathos_provider.py",
        "LICENSE.txt",
        "NOTICE.txt",
        "SKILL.md",
        "README.md",
    ]

    missing = [item for item in expected if not (SKILL_ROOT / item).exists()]

    assert missing == []
```

- [ ] **Step 2: Run the scaffold test to verify it fails**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_formatting_skill_scaffold_exists -v
```

Expected: FAIL with missing scaffold files.

- [ ] **Step 3: Create the skill files and directories**

Create the directories listed in the file structure.

Create `skills/mathos-formatting/scripts/mathos_formatting.py`:

```python
"""CLI entrypoint for the MathOS adaptive Markdown formatting operator."""

from __future__ import annotations


def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `skills/mathos-formatting/scripts/mathos_formatting_core.py`:

```python
"""Core utilities for MathOS adaptive Markdown formatting."""

from __future__ import annotations
```

Create `skills/mathos-formatting/scripts/mathos_provider.py`:

```python
"""Provider adapter for MathOS adaptive Markdown formatting."""

from __future__ import annotations
```

Create `skills/mathos-formatting/SKILL.md`:

```markdown
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
```

Create `skills/mathos-formatting/README.md`:

```markdown
# mathos-formatting

Status: active after implementation.

This repo-local skill manages adaptive Markdown formatting for MathOS.

The skill uses a two-step LLM-assisted workflow:

1. Extract headings and table-of-contents samples so the provider can propose regex heading rules.
2. Extract one h1 section so the provider can propose a Python content cleaner.

Unknown file types are modified only through fresh candidate backups. Approved reusable programs are saved under `plugins/approved/` only after user approval.
```

Create `skills/mathos-formatting/LICENSE.txt`:

```text
Copyright (c) 2026 MathOS contributors.

This local skill is provided for use inside the Mathematics-Knowledge workspace.
```

Create `skills/mathos-formatting/NOTICE.txt`:

```text
MathOS adaptive Markdown formatting skill.

This skill may call a configured LLM provider to generate candidate formatting rules and cleaner plugins. Provider secrets must not be logged, printed, or saved.
```

Create `skills/mathos-formatting/agents/heading_rules_prompt.md`:

```markdown
# Heading Rules Prompt

You are generating deterministic Markdown heading normalization rules from extracted structure.

Return JSON only with this shape:

```json
{
  "rules": [
    {
      "id": "chapter_heading",
      "pattern": "^(第[一二三四五六七八九十]+章 .+?)(?: *[.．…·]+ *\\d+)?$",
      "replacement": "# \\\\1",
      "flags": ["MULTILINE"]
    }
  ],
  "notes": ["short human-readable summary"]
}
```

Rules must preserve math blocks, code fences, image links, and tables unless the payload explicitly requests changes to them.
```

Create `skills/mathos-formatting/agents/content_cleaner_prompt.md`:

```markdown
# Content Cleaner Prompt

You are generating a Python Markdown cleaner plugin.

Return one Python file only. It must expose:

```python
PLUGIN_ID = "descriptive_id"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"warnings": [], "summary": []}

def clean(markdown: str) -> str:
    return markdown
```

The plugin receives Markdown text and returns Markdown text. Do not read files, write files, access environment variables, call subprocesses, or use network APIs.
```

Create `skills/mathos-formatting/references/formatting-program-format.md`:

```markdown
# Approved Formatting Program Format

Approved programs live under `plugins/approved/<plugin-id>/`.

Required files:

- `heading_rules.json`
- `content_cleaner.py`
- `metadata.json`
- `approval.md`
- `sample_before.md`
- `sample_after.md`

Newly approved programs start with `"allowed_scope": "manual-only"` in `metadata.json`.
```

- [ ] **Step 4: Run the scaffold test to verify it passes**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_formatting_skill_scaffold_exists -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting tests/test_mathos_formatting.py
git commit -m "feat: scaffold mathos formatting skill"
```

## Task 2: Implement Markdown Structure Extraction

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing extraction tests**

Append:

```python
import importlib.util
import sys


CORE_PATH = SKILL_ROOT / "scripts" / "mathos_formatting_core.py"
core_spec = importlib.util.spec_from_file_location("mathos_formatting_core", CORE_PATH)
core = importlib.util.module_from_spec(core_spec)
assert core_spec.loader is not None
sys.modules["mathos_formatting_core"] = core
core_spec.loader.exec_module(core)


SAMPLE_MARKDOWN = """# 数学

# 目录

# 第一章 集合与常用逻辑用语 …… 1
1.1 集合的概念…… 2
阅读与思考 集合中元素的个数 …… 15

# 第一章 集合与常用逻辑用语

## 1.1 集合的概念

集合是数学语言。

```python
# not a markdown heading
```

$$
# not a markdown heading either
$$

![](images/a.png)
"""


def test_extract_structure_finds_headings_toc_h1_and_protected_blocks():
    result = core.extract_structure(SAMPLE_MARKDOWN, source_label="sample.md")

    assert result.source_label == "sample.md"
    assert [heading.text for heading in result.headings[:4]] == [
        "数学",
        "目录",
        "第一章 集合与常用逻辑用语 …… 1",
        "第一章 集合与常用逻辑用语",
    ]
    assert result.toc_block is not None
    assert "1.1 集合的概念" in result.toc_block.text
    assert result.heading_level_distribution == {1: 4, 2: 1}
    assert result.h1_sections[0].heading == "数学"
    assert any(block.kind == "code_fence" for block in result.protected_blocks)
    assert any(block.kind == "math_block" for block in result.protected_blocks)
    assert any(block.kind == "image" for block in result.protected_blocks)
```

- [ ] **Step 2: Run extraction tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_extract_structure_finds_headings_toc_h1_and_protected_blocks -v
```

Expected: FAIL with `AttributeError: module 'mathos_formatting_core' has no attribute 'extract_structure'`.

- [ ] **Step 3: Implement extraction dataclasses and function**

Add to `mathos_formatting_core.py`:

```python
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line_number: int


@dataclass(frozen=True)
class TextBlock:
    kind: str
    text: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class H1Section:
    heading: str
    text: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class MarkdownStructure:
    source_label: str
    headings: list[Heading]
    toc_block: TextBlock | None
    heading_like_lines: list[str]
    heading_level_distribution: dict[int, int]
    h1_sections: list[H1Section]
    protected_blocks: list[TextBlock]


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TOC_HEADING_RE = re.compile(r"^#{1,6}\s*(目录|目\s*录|contents?)\s*$", re.IGNORECASE)
HEADING_LIKE_RE = re.compile(
    r"^(第[一二三四五六七八九十百千万0-9]+[章节篇部].+|"
    r"\d+(?:\.\d+)+\s+.+|"
    r"(阅读与思考|探究与发现|信息技术应用|文献阅读|小结|复习参考题).*)$"
)


def _line_offsets(markdown: str) -> list[str]:
    return markdown.splitlines()


def _extract_protected_blocks(lines: list[str]) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    in_code = False
    code_start = 0
    in_math = False
    math_start = 0

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append(TextBlock("code_fence", "\n".join(lines[code_start - 1:index]), code_start, index))
                in_code = False
            else:
                in_code = True
                code_start = index
            continue
        if stripped == "$$":
            if in_math:
                blocks.append(TextBlock("math_block", "\n".join(lines[math_start - 1:index]), math_start, index))
                in_math = False
            else:
                in_math = True
                math_start = index
            continue
        if re.search(r"!\[[^\]]*\]\([^)]+\)", line):
            blocks.append(TextBlock("image", line, index, index))

    return blocks


def _line_in_blocks(line_number: int, blocks: list[TextBlock], kinds: set[str]) -> bool:
    return any(block.kind in kinds and block.start_line <= line_number <= block.end_line for block in blocks)


def _extract_toc_block(lines: list[str], headings: list[Heading]) -> TextBlock | None:
    toc_heading = next((heading for heading in headings if TOC_HEADING_RE.match("#" * heading.level + " " + heading.text)), None)
    if toc_heading is None:
        return None

    following_h1 = next(
        (heading for heading in headings if heading.level == 1 and heading.line_number > toc_heading.line_number),
        None,
    )
    end_line = (following_h1.line_number - 1) if following_h1 else len(lines)
    text = "\n".join(lines[toc_heading.line_number - 1:end_line])
    return TextBlock("toc", text, toc_heading.line_number, end_line)


def _extract_h1_sections(lines: list[str], headings: list[Heading]) -> list[H1Section]:
    h1_headings = [heading for heading in headings if heading.level == 1]
    sections: list[H1Section] = []
    for index, heading in enumerate(h1_headings):
        end_line = h1_headings[index + 1].line_number - 1 if index + 1 < len(h1_headings) else len(lines)
        sections.append(
            H1Section(
                heading=heading.text,
                text="\n".join(lines[heading.line_number - 1:end_line]),
                start_line=heading.line_number,
                end_line=end_line,
            )
        )
    return sections


def extract_structure(markdown: str, source_label: str) -> MarkdownStructure:
    lines = _line_offsets(markdown)
    protected_blocks = _extract_protected_blocks(lines)
    headings: list[Heading] = []
    heading_like_lines: list[str] = []
    distribution: dict[int, int] = {}

    for line_number, line in enumerate(lines, start=1):
        if _line_in_blocks(line_number, protected_blocks, {"code_fence", "math_block"}):
            continue
        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            headings.append(Heading(level, heading_match.group(2), line_number))
            distribution[level] = distribution.get(level, 0) + 1
            continue
        stripped = line.strip()
        if stripped and HEADING_LIKE_RE.match(stripped):
            heading_like_lines.append(stripped)

    return MarkdownStructure(
        source_label=source_label,
        headings=headings,
        toc_block=_extract_toc_block(lines, headings),
        heading_like_lines=heading_like_lines,
        heading_level_distribution=distribution,
        h1_sections=_extract_h1_sections(lines, headings),
        protected_blocks=protected_blocks,
    )
```

- [ ] **Step 4: Run extraction tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_extract_structure_finds_headings_toc_h1_and_protected_blocks -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: extract markdown formatting structure"
```

## Task 3: Implement Heading Rule Validation And Application

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing heading-rule tests**

Append:

```python
import pytest


def test_heading_rules_validate_and_apply_outside_protected_blocks():
    rules = {
        "rules": [
            {
                "id": "chapter",
                "pattern": r"^(第一章 .+?)(?: …… \d+)?$",
                "replacement": r"# \1",
                "flags": ["MULTILINE"],
            },
            {
                "id": "section",
                "pattern": r"^(1\.1 .+?)(?:…… \d+)?$",
                "replacement": r"## \1",
                "flags": ["MULTILINE"],
            },
        ],
        "notes": ["align chapter and section headings"],
    }
    markdown = "第一章 集合 …… 1\n\n1.1 集合的概念…… 2\n\n```\n1.1 keep code\n```\n"

    validated = core.validate_heading_rules(rules)
    cleaned = core.apply_heading_rules(markdown, validated)

    assert cleaned.startswith("# 第一章 集合\n\n## 1.1 集合的概念")
    assert "```\n1.1 keep code\n```" in cleaned


def test_heading_rules_reject_invalid_regex():
    rules = {"rules": [{"id": "bad", "pattern": "(", "replacement": "# x", "flags": []}]}

    with pytest.raises(core.FormattingError, match="invalid regex"):
        core.validate_heading_rules(rules)
```

- [ ] **Step 2: Run heading-rule tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_heading_rules_validate_and_apply_outside_protected_blocks tests/test_mathos_formatting.py::test_heading_rules_reject_invalid_regex -v
```

Expected: FAIL with missing `validate_heading_rules`.

- [ ] **Step 3: Implement heading rules**

Add:

```python
@dataclass(frozen=True)
class HeadingRule:
    rule_id: str
    pattern: str
    replacement: str
    flags: int


class FormattingError(RuntimeError):
    """Raised when formatting configuration or execution is unsafe."""


FLAG_MAP = {
    "MULTILINE": re.MULTILINE,
    "IGNORECASE": re.IGNORECASE,
}


def _compile_flags(raw_flags: list[str]) -> int:
    flags = 0
    for flag in raw_flags:
        if flag not in FLAG_MAP:
            raise FormattingError(f"unsupported regex flag: {flag}")
        flags |= FLAG_MAP[flag]
    return flags


def validate_heading_rules(payload: dict) -> list[HeadingRule]:
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise FormattingError("heading rules must contain a non-empty rules list")

    validated: list[HeadingRule] = []
    for raw_rule in raw_rules:
        rule_id = raw_rule.get("id")
        pattern = raw_rule.get("pattern")
        replacement = raw_rule.get("replacement")
        raw_flags = raw_rule.get("flags", [])
        if not isinstance(rule_id, str) or not rule_id:
            raise FormattingError("heading rule id must be a non-empty string")
        if not isinstance(pattern, str) or not pattern:
            raise FormattingError(f"heading rule {rule_id} pattern must be a non-empty string")
        if not isinstance(replacement, str):
            raise FormattingError(f"heading rule {rule_id} replacement must be a string")
        if not isinstance(raw_flags, list) or not all(isinstance(flag, str) for flag in raw_flags):
            raise FormattingError(f"heading rule {rule_id} flags must be a string list")
        flags = _compile_flags(raw_flags)
        try:
            re.compile(pattern, flags)
        except re.error as exc:
            raise FormattingError(f"invalid regex in heading rule {rule_id}: {exc}") from exc
        validated.append(HeadingRule(rule_id, pattern, replacement, flags))
    return validated


def _protect_multiline_blocks(markdown: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = f"__MATHOS_PROTECTED_{len(replacements)}__"
        replacements[token] = match.group(0)
        return token

    protected = re.sub(r"```.*?```", replace, markdown, flags=re.DOTALL)
    protected = re.sub(r"\$\$.*?\$\$", replace, protected, flags=re.DOTALL)
    return protected, replacements


def _restore_multiline_blocks(markdown: str, replacements: dict[str, str]) -> str:
    restored = markdown
    for token, value in replacements.items():
        restored = restored.replace(token, value)
    return restored


def apply_heading_rules(markdown: str, rules: list[HeadingRule]) -> str:
    protected, replacements = _protect_multiline_blocks(markdown)
    result = protected
    for rule in rules:
        result = re.sub(rule.pattern, rule.replacement, result, flags=rule.flags)
    return _restore_multiline_blocks(result, replacements)
```

- [ ] **Step 4: Run heading-rule tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_heading_rules_validate_and_apply_outside_protected_blocks tests/test_mathos_formatting.py::test_heading_rules_reject_invalid_regex -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: validate and apply formatting heading rules"
```

## Task 4: Implement Candidate Backup Lifecycle And Reports

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing candidate and report tests**

Append:

```python
def test_candidate_backup_is_recreated_from_original_each_iteration(tmp_path):
    original = tmp_path / "book.md"
    original.write_text("第一章 集合 …… 1\n\nbody\n", encoding="utf-8")

    first_candidate = core.create_fresh_candidate(original)
    first_candidate.write_text("mutated candidate\n", encoding="utf-8")

    second_candidate = core.create_fresh_candidate(original)

    assert first_candidate == second_candidate
    assert second_candidate.read_text(encoding="utf-8") == "第一章 集合 …… 1\n\nbody\n"
    assert original.read_text(encoding="utf-8") == "第一章 集合 …… 1\n\nbody\n"


def test_write_review_report_contains_diff_and_warnings(tmp_path):
    original = tmp_path / "book.md"
    candidate = tmp_path / ".mathos-formatting" / "book.candidate.md"
    report = tmp_path / ".mathos-formatting" / "book.report.md"
    original.write_text("第一章 集合 …… 1\n", encoding="utf-8")
    candidate.parent.mkdir()
    candidate.write_text("# 第一章 集合\n", encoding="utf-8")

    path = core.write_review_report(
        original_path=original,
        candidate_path=candidate,
        report_path=report,
        heading_summary=["chapter -> h1"],
        plugin_summary=["removed page number"],
        warnings=["sample warning"],
    )

    text = path.read_text(encoding="utf-8")
    assert "Source file:" in text
    assert "Candidate file:" in text
    assert "chapter -> h1" in text
    assert "sample warning" in text
    assert "-第一章 集合 …… 1" in text
    assert "+# 第一章 集合" in text
```

- [ ] **Step 2: Run candidate/report tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_candidate_backup_is_recreated_from_original_each_iteration tests/test_mathos_formatting.py::test_write_review_report_contains_diff_and_warnings -v
```

Expected: FAIL with missing `create_fresh_candidate`.

- [ ] **Step 3: Implement candidate backup and review report functions**

Add:

```python
import difflib
import shutil


def candidate_path_for(original_path: Path) -> Path:
    return original_path.parent / ".mathos-formatting" / f"{original_path.stem}.candidate{original_path.suffix}"


def create_fresh_candidate(original_path: Path) -> Path:
    original_path = original_path.resolve()
    if not original_path.exists():
        raise FormattingError(f"source Markdown file does not exist: {original_path}")
    if original_path.suffix.lower() != ".md":
        raise FormattingError(f"source file must be Markdown: {original_path}")

    candidate_path = candidate_path_for(original_path)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    if candidate_path.exists():
        candidate_path.unlink()
    shutil.copy2(original_path, candidate_path)
    return candidate_path


def unified_markdown_diff(original_text: str, candidate_text: str, original_name: str, candidate_name: str) -> str:
    return "".join(
        difflib.unified_diff(
            original_text.splitlines(keepends=True),
            candidate_text.splitlines(keepends=True),
            fromfile=original_name,
            tofile=candidate_name,
            lineterm="",
        )
    )


def write_review_report(
    original_path: Path,
    candidate_path: Path,
    report_path: Path,
    heading_summary: list[str],
    plugin_summary: list[str],
    warnings: list[str],
) -> Path:
    original_text = original_path.read_text(encoding="utf-8")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    diff_text = unified_markdown_diff(
        original_text,
        candidate_text,
        str(original_path),
        str(candidate_path),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = [
        "# MathOS Formatting Candidate Report",
        "",
        f"Source file: `{original_path}`",
        f"Candidate file: `{candidate_path}`",
        "",
        "## Heading Rules Summary",
        "",
        *[f"- {item}" for item in heading_summary],
        "",
        "## Content Plugin Summary",
        "",
        *[f"- {item}" for item in plugin_summary],
        "",
        "## Warnings",
        "",
        *[f"- {item}" for item in warnings],
        "",
        "## Diff",
        "",
        "```diff",
        diff_text,
        "```",
        "",
        "## Next Actions",
        "",
        "- approve",
        "- revise",
        "- discard",
        "",
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")
    return report_path
```

- [ ] **Step 4: Run candidate/report tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_candidate_backup_is_recreated_from_original_each_iteration tests/test_mathos_formatting.py::test_write_review_report_contains_diff_and_warnings -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: create formatting candidates and review reports"
```

## Task 5: Implement Plugin Safety Validation And Text-Only Runner

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [x] **Step 1: Write failing plugin safety tests**

Append:

```python
SAFE_PLUGIN = '''
PLUGIN_ID = "safe_plugin"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"warnings": [], "summary": ["normalize whitespace"]}

def clean(markdown: str) -> str:
    return markdown.replace("  ", " ")
'''


UNSAFE_PLUGIN = '''
import os

PLUGIN_ID = "unsafe_plugin"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"warnings": [], "summary": []}

def clean(markdown: str) -> str:
    return os.environ.get("SECRET", markdown)
'''


def test_plugin_runner_accepts_text_only_safe_plugin(tmp_path):
    plugin_path = tmp_path / "content_cleaner.py"
    plugin_path.write_text(SAFE_PLUGIN, encoding="utf-8")

    plugin = core.load_safe_plugin(plugin_path)
    result = core.run_plugin(plugin, "a  b")

    assert result.cleaned_markdown == "a b"
    assert result.summary == ["normalize whitespace"]
    assert result.warnings == []


def test_plugin_runner_rejects_environment_access(tmp_path):
    plugin_path = tmp_path / "content_cleaner.py"
    plugin_path.write_text(UNSAFE_PLUGIN, encoding="utf-8")

    with pytest.raises(core.FormattingError, match="unsafe import"):
        core.load_safe_plugin(plugin_path)
```

- [x] **Step 2: Run plugin tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_plugin_runner_accepts_text_only_safe_plugin tests/test_mathos_formatting.py::test_plugin_runner_rejects_environment_access -v
```

Expected: FAIL with missing `load_safe_plugin`.

- [x] **Step 3: Implement static safety checks and runner**

Add:

```python
import ast
import importlib.util
import sys
from types import ModuleType


SAFE_IMPORTS = {"re", "math", "typing"}
UNSAFE_CALL_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
}
UNSAFE_ATTRIBUTE_ROOTS = {
    "os",
    "sys",
    "subprocess",
    "pathlib",
    "socket",
    "requests",
    "urllib",
    "http",
    "shutil",
}


@dataclass(frozen=True)
class PluginResult:
    cleaned_markdown: str
    summary: list[str]
    warnings: list[str]


def _validate_plugin_ast(source: str) -> None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in SAFE_IMPORTS:
                    raise FormattingError(f"unsafe import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in SAFE_IMPORTS:
                raise FormattingError(f"unsafe import: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in UNSAFE_CALL_NAMES:
                raise FormattingError(f"unsafe call: {node.func.id}")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in UNSAFE_ATTRIBUTE_ROOTS:
                raise FormattingError(f"unsafe attribute access: {node.value.id}.{node.attr}")


def load_safe_plugin(plugin_path: Path) -> ModuleType:
    source = plugin_path.read_text(encoding="utf-8")
    _validate_plugin_ast(source)
    module_name = f"mathos_candidate_{abs(hash(plugin_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise FormattingError(f"cannot load plugin: {plugin_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    for attr in ["PLUGIN_ID", "PLUGIN_VERSION", "analyze", "clean"]:
        if not hasattr(module, attr):
            raise FormattingError(f"plugin missing required attribute: {attr}")
    probe = module.clean("probe")
    if not isinstance(probe, str):
        raise FormattingError("plugin clean() must return a string")
    analysis = module.analyze("probe")
    if not isinstance(analysis, dict):
        raise FormattingError("plugin analyze() must return a dict")
    return module


def run_plugin(plugin: ModuleType, markdown: str) -> PluginResult:
    analysis = plugin.analyze(markdown)
    cleaned = plugin.clean(markdown)
    if not isinstance(cleaned, str):
        raise FormattingError("plugin clean() must return a string")
    summary = analysis.get("summary", [])
    warnings = analysis.get("warnings", [])
    if not isinstance(summary, list) or not all(isinstance(item, str) for item in summary):
        raise FormattingError("plugin analysis summary must be a string list")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise FormattingError("plugin analysis warnings must be a string list")
    return PluginResult(cleaned_markdown=cleaned, summary=summary, warnings=warnings)
```

- [x] **Step 4: Run plugin tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_plugin_runner_accepts_text_only_safe_plugin tests/test_mathos_formatting.py::test_plugin_runner_rejects_environment_access -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: validate and run text-only formatting plugins"
```

Acceptance note: completed in `f66d013` and hardened in `5deacf8` to reject `__builtins__` subscript access and remove invalid plugin modules from `sys.modules`. Verified with `python -m pytest tests/test_mathos_formatting.py -v` and `python -m pytest -q` on 2026-06-06.

## Task 6: Implement Provider Adapter And Structured Artifact Parsing

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_provider.py`
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [x] **Step 1: Write failing provider tests**

Append:

```python
PROVIDER_PATH = SKILL_ROOT / "scripts" / "mathos_provider.py"
provider_spec = importlib.util.spec_from_file_location("mathos_provider", PROVIDER_PATH)
provider = importlib.util.module_from_spec(provider_spec)
assert provider_spec.loader is not None
sys.modules["mathos_provider"] = provider
provider_spec.loader.exec_module(provider)


def test_load_provider_settings_reads_deepseek_without_exposing_secret(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DEEPSEEK_API_KEY=secret-value\nDEEPSEEK_BASE_URL=https://api.deepseek.com\nDEEPSEEK_MODEL=deepseek-chat\n",
        encoding="utf-8",
    )

    settings = provider.load_provider_settings(env_path)

    assert settings.api_key == "secret-value"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-chat"
    assert "secret-value" not in repr(settings)


def test_parse_heading_rules_artifact_accepts_json_only():
    artifact = provider.parse_heading_rules_artifact('{"rules": [{"id": "x", "pattern": "^x$", "replacement": "# x", "flags": []}]}')

    assert artifact["rules"][0]["id"] == "x"


def test_parse_python_artifact_strips_markdown_fence():
    text = "```python\nPLUGIN_ID = 'x'\nPLUGIN_VERSION = '1.0.0'\n\ndef analyze(markdown: str) -> dict:\n    return {'summary': [], 'warnings': []}\n\ndef clean(markdown: str) -> str:\n    return markdown\n```"

    parsed = provider.parse_python_artifact(text)

    assert parsed.startswith("PLUGIN_ID")
    assert "```" not in parsed
```

- [x] **Step 2: Run provider tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_load_provider_settings_reads_deepseek_without_exposing_secret tests/test_mathos_formatting.py::test_parse_heading_rules_artifact_accepts_json_only tests/test_mathos_formatting.py::test_parse_python_artifact_strips_markdown_fence -v
```

Expected: FAIL with missing provider functions.

- [x] **Step 3: Implement provider settings and parsers**

Add to `mathos_provider.py`:

```python
from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib import request


class ProviderError(RuntimeError):
    """Raised when provider configuration or response parsing fails."""


@dataclass(frozen=True)
class ProviderSettings:
    api_key: str
    base_url: str
    model: str

    def __repr__(self) -> str:
        return f"ProviderSettings(api_key='<redacted>', base_url={self.base_url!r}, model={self.model!r})"


def _read_env(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        raise ProviderError(f"env file does not exist: {env_path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_provider_settings(env_path: Path) -> ProviderSettings:
    values = _read_env(env_path)
    api_key = values.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ProviderError("DEEPSEEK_API_KEY is missing")
    return ProviderSettings(
        api_key=api_key,
        base_url=values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        model=values.get("DEEPSEEK_MODEL", "deepseek-chat"),
    )


def parse_heading_rules_artifact(text: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"heading rules response is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or "rules" not in payload:
        raise ProviderError("heading rules response must be a JSON object with a rules key")
    return payload


def parse_python_artifact(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:python)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    if "def clean(" not in stripped or "def analyze(" not in stripped:
        raise ProviderError("python artifact must define analyze() and clean()")
    return stripped
```

- [x] **Step 4: Add provider call helper**

Append to `mathos_provider.py`:

```python
def call_deepseek_chat(settings: ProviderSettings, system_prompt: str, user_payload: str, timeout_seconds: int = 120) -> str:
    endpoint = f"{settings.base_url}/chat/completions"
    payload = json.dumps(
        {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            "temperature": 0.1,
        }
    ).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("provider response missing choices[0].message.content") from exc
```

- [x] **Step 5: Run provider tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_load_provider_settings_reads_deepseek_without_exposing_secret tests/test_mathos_formatting.py::test_parse_heading_rules_artifact_accepts_json_only tests/test_mathos_formatting.py::test_parse_python_artifact_strips_markdown_fence -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_provider.py tests/test_mathos_formatting.py
git commit -m "feat: add formatting provider adapter"
```

Acceptance note: completed in `7b65169`. Verified required provider tests, `python -m pytest tests/test_mathos_formatting.py -q`, and `python -m py_compile skills/mathos-formatting/scripts/mathos_provider.py` on 2026-06-06.

## Task 7: Implement Approval Save And Approved Plugin Reuse

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [x] **Step 1: Write failing approval and reuse tests**

Append:

```python
import json


def test_save_approved_program_writes_required_files(tmp_path):
    approved_root = tmp_path / "approved"
    original = tmp_path / "before.md"
    candidate = tmp_path / "after.md"
    plugin = tmp_path / "content_cleaner.py"
    original.write_text("第一章 集合 …… 1\n", encoding="utf-8")
    candidate.write_text("# 第一章 集合\n", encoding="utf-8")
    plugin.write_text(SAFE_PLUGIN, encoding="utf-8")
    heading_rules = {"rules": [{"id": "chapter", "pattern": "^x$", "replacement": "# x", "flags": []}]}

    program_dir = core.save_approved_program(
        approved_root=approved_root,
        plugin_id="safe_plugin",
        heading_rules=heading_rules,
        plugin_path=plugin,
        original_path=original,
        candidate_path=candidate,
        approving_source_path=original,
        operations_summary=["chapter heading normalized"],
    )

    assert (program_dir / "heading_rules.json").exists()
    assert (program_dir / "content_cleaner.py").exists()
    assert (program_dir / "approval.md").exists()
    assert (program_dir / "sample_before.md").read_text(encoding="utf-8") == "第一章 集合 …… 1\n"
    metadata = json.loads((program_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["plugin_id"] == "safe_plugin"
    assert metadata["allowed_scope"] == "manual-only"


def test_apply_approved_program_reuses_without_provider(tmp_path):
    approved_root = tmp_path / "approved"
    target = tmp_path / "target.md"
    target.write_text("第一章 集合 …… 1\n\na  b\n", encoding="utf-8")
    original = tmp_path / "before.md"
    candidate = tmp_path / "after.md"
    plugin = tmp_path / "content_cleaner.py"
    original.write_text("x\n", encoding="utf-8")
    candidate.write_text("x\n", encoding="utf-8")
    plugin.write_text(SAFE_PLUGIN, encoding="utf-8")
    heading_rules = {"rules": [{"id": "chapter", "pattern": r"^(第一章 .+?)(?: …… \d+)?$", "replacement": r"# \1", "flags": ["MULTILINE"]}]}
    core.save_approved_program(approved_root, "safe_plugin", heading_rules, plugin, original, candidate, original, ["summary"])

    result = core.apply_approved_program(approved_root / "safe_plugin", target)

    assert result.candidate_path.read_text(encoding="utf-8") == "# 第一章 集合\n\na b\n"
    assert target.read_text(encoding="utf-8") == "第一章 集合 …… 1\n\na  b\n"
```

- [x] **Step 2: Run approval tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_save_approved_program_writes_required_files tests/test_mathos_formatting.py::test_apply_approved_program_reuses_without_provider -v
```

Expected: FAIL with missing `save_approved_program`.

- [x] **Step 3: Implement approval save and approved reuse**

Add:

```python
import hashlib
import json
from datetime import datetime, timezone


@dataclass(frozen=True)
class ApprovedApplyResult:
    candidate_path: Path
    report_path: Path
    summary: list[str]
    warnings: list[str]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_approved_program(
    approved_root: Path,
    plugin_id: str,
    heading_rules: dict,
    plugin_path: Path,
    original_path: Path,
    candidate_path: Path,
    approving_source_path: Path,
    operations_summary: list[str],
) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", plugin_id):
        raise FormattingError("plugin id may contain only letters, numbers, underscores, and hyphens")
    program_dir = approved_root / plugin_id
    if program_dir.exists():
        raise FormattingError(f"approved plugin already exists: {plugin_id}")
    program_dir.mkdir(parents=True)

    original_text = original_path.read_text(encoding="utf-8")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    (program_dir / "heading_rules.json").write_text(
        json.dumps(heading_rules, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    shutil.copy2(plugin_path, program_dir / "content_cleaner.py")
    (program_dir / "sample_before.md").write_text(original_text, encoding="utf-8")
    (program_dir / "sample_after.md").write_text(candidate_text, encoding="utf-8")
    metadata = {
        "plugin_id": plugin_id,
        "version": "1.0.0",
        "approval_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_file_family_evidence": str(approving_source_path),
        "heading_signature": extract_structure(candidate_text, str(candidate_path)).heading_level_distribution,
        "toc_signature": bool(extract_structure(original_text, str(original_path)).toc_block),
        "h1_sample_hash": _sha256_text(extract_structure(candidate_text, str(candidate_path)).h1_sections[0].text)
        if extract_structure(candidate_text, str(candidate_path)).h1_sections
        else _sha256_text(candidate_text[:2000]),
        "operations_summary": operations_summary,
        "original_approving_file_path": str(approving_source_path),
        "allowed_scope": "manual-only",
    }
    (program_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (program_dir / "approval.md").write_text(
        "\n".join(
            [
                "# Approval",
                "",
                f"Approved program: `{plugin_id}`",
                f"Approving source: `{approving_source_path}`",
                "",
                "Allowed scope: `manual-only`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return program_dir


def apply_approved_program(program_dir: Path, target_path: Path) -> ApprovedApplyResult:
    heading_rules_payload = json.loads((program_dir / "heading_rules.json").read_text(encoding="utf-8"))
    rules = validate_heading_rules(heading_rules_payload)
    plugin = load_safe_plugin(program_dir / "content_cleaner.py")

    candidate_path = create_fresh_candidate(target_path)
    markdown = candidate_path.read_text(encoding="utf-8")
    markdown = apply_heading_rules(markdown, rules)
    plugin_result = run_plugin(plugin, markdown)
    candidate_path.write_text(plugin_result.cleaned_markdown, encoding="utf-8")

    report_path = candidate_path.parent / f"{target_path.stem}.approved-report.md"
    write_review_report(
        original_path=target_path,
        candidate_path=candidate_path,
        report_path=report_path,
        heading_summary=[rule.rule_id for rule in rules],
        plugin_summary=plugin_result.summary,
        warnings=plugin_result.warnings,
    )
    return ApprovedApplyResult(
        candidate_path=candidate_path,
        report_path=report_path,
        summary=plugin_result.summary,
        warnings=plugin_result.warnings,
    )
```

- [x] **Step 4: Run approval tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_save_approved_program_writes_required_files tests/test_mathos_formatting.py::test_apply_approved_program_reuses_without_provider -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: approve and reuse formatting programs"
```

Acceptance note: completed in `8bf9272`. Verified focused approval/reuse tests, `python -m py_compile skills/mathos-formatting/scripts/mathos_formatting_core.py`, and `python -m pytest -q` on 2026-06-06.

## Task 8: Implement CLI Orchestration

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Modify: `skills/mathos-formatting/scripts/mathos_provider.py`
- Test: `tests/test_mathos_formatting.py`

- [x] **Step 1: Write failing CLI smoke tests**

Append:

```python
import subprocess


CLI_PATH = SKILL_ROOT / "scripts" / "mathos_formatting.py"


def test_cli_inspect_outputs_structure_json(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "inspect", str(markdown)],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["source_label"].endswith("book.md")
    assert payload["heading_count"] >= 1
    assert payload["toc_found"] is True


def test_cli_apply_approved_writes_candidate_not_original(tmp_path):
    approved_root = tmp_path / "approved"
    target = tmp_path / "target.md"
    target.write_text("第一章 集合 …… 1\n\na  b\n", encoding="utf-8")
    original = tmp_path / "before.md"
    candidate = tmp_path / "after.md"
    plugin = tmp_path / "content_cleaner.py"
    original.write_text("x\n", encoding="utf-8")
    candidate.write_text("x\n", encoding="utf-8")
    plugin.write_text(SAFE_PLUGIN, encoding="utf-8")
    heading_rules = {"rules": [{"id": "chapter", "pattern": r"^(第一章 .+?)(?: …… \d+)?$", "replacement": r"# \1", "flags": ["MULTILINE"]}]}
    core.save_approved_program(approved_root, "safe_plugin", heading_rules, plugin, original, candidate, original, ["summary"])

    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "apply-approved", str(approved_root / "safe_plugin"), str(target)],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert Path(payload["candidate_path"]).exists()
    assert target.read_text(encoding="utf-8") == "第一章 集合 …… 1\n\na  b\n"
```

- [x] **Step 2: Run CLI tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_cli_inspect_outputs_structure_json tests/test_mathos_formatting.py::test_cli_apply_approved_writes_candidate_not_original -v
```

Expected: FAIL because the CLI does not implement commands.

- [x] **Step 3: Implement CLI commands**

Replace `mathos_formatting.py` with:

```python
"""CLI entrypoint for the MathOS adaptive Markdown formatting operator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import mathos_formatting_core as core


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def command_inspect(args: argparse.Namespace) -> int:
    source = Path(args.markdown)
    markdown = source.read_text(encoding="utf-8")
    structure = core.extract_structure(markdown, str(source))
    _print_json(
        {
            "source_label": structure.source_label,
            "heading_count": len(structure.headings),
            "toc_found": structure.toc_block is not None,
            "heading_level_distribution": structure.heading_level_distribution,
            "heading_like_line_count": len(structure.heading_like_lines),
            "h1_section_count": len(structure.h1_sections),
            "protected_block_count": len(structure.protected_blocks),
        }
    )
    return 0


def command_apply_approved(args: argparse.Namespace) -> int:
    result = core.apply_approved_program(Path(args.program_dir), Path(args.markdown))
    _print_json(
        {
            "status": "candidate-written",
            "candidate_path": str(result.candidate_path),
            "report_path": str(result.report_path),
            "summary": result.summary,
            "warnings": result.warnings,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MathOS adaptive Markdown formatting operator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect Markdown structure without modifying files")
    inspect_parser.add_argument("markdown")
    inspect_parser.set_defaults(func=command_inspect)

    apply_parser = subparsers.add_parser("apply-approved", help="Apply an approved program to a fresh candidate backup")
    apply_parser.add_argument("program_dir")
    apply_parser.add_argument("markdown")
    apply_parser.set_defaults(func=command_apply_approved)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run CLI tests to verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_cli_inspect_outputs_structure_json tests/test_mathos_formatting.py::test_cli_apply_approved_writes_candidate_not_original -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting.py tests/test_mathos_formatting.py
git commit -m "feat: add formatting operator cli"
```

Acceptance note: completed in `ad120c2`. Verified focused CLI smoke tests, `python -m py_compile skills/mathos-formatting/scripts/mathos_formatting.py`, `git diff --check`, and `python -m pytest -q` on 2026-06-06.

## Task 9: Add Learning Command With Fakeable Provider Hooks

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Modify: `skills/mathos-formatting/scripts/mathos_provider.py`
- Test: `tests/test_mathos_formatting.py`

- [x] **Step 1: Write failing learning command test using fixture artifacts**

Append:

```python
def test_cli_candidate_from_artifacts_creates_backup_report_and_candidate_plugin(tmp_path):
    markdown = tmp_path / "book.md"
    heading_rules_path = tmp_path / "heading_rules.json"
    plugin_path = tmp_path / "generated_plugin.py"
    markdown.write_text("第一章 集合 …… 1\n\na  b\n", encoding="utf-8")
    heading_rules_path.write_text(
        json.dumps({"rules": [{"id": "chapter", "pattern": r"^(第一章 .+?)(?: …… \d+)?$", "replacement": r"# \1", "flags": ["MULTILINE"]}]}),
        encoding="utf-8",
    )
    plugin_path.write_text(SAFE_PLUGIN, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "candidate-from-artifacts",
            str(markdown),
            "--heading-rules",
            str(heading_rules_path),
            "--plugin",
            str(plugin_path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    candidate = Path(payload["candidate_path"])
    report = Path(payload["report_path"])
    assert candidate.read_text(encoding="utf-8") == "# 第一章 集合\n\na b\n"
    assert report.exists()
    assert markdown.read_text(encoding="utf-8") == "第一章 集合 …… 1\n\na  b\n"
```

- [x] **Step 2: Run learning command test to verify it fails**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_cli_candidate_from_artifacts_creates_backup_report_and_candidate_plugin -v
```

Expected: FAIL because the command does not exist.

- [x] **Step 3: Add a helper for candidate runs from already-generated artifacts**

Add to `mathos_formatting_core.py`:

```python
@dataclass(frozen=True)
class CandidateRunResult:
    candidate_path: Path
    report_path: Path
    summary: list[str]
    warnings: list[str]


def run_candidate_from_artifacts(markdown_path: Path, heading_rules_path: Path, plugin_path: Path) -> CandidateRunResult:
    heading_payload = json.loads(heading_rules_path.read_text(encoding="utf-8"))
    rules = validate_heading_rules(heading_payload)
    plugin = load_safe_plugin(plugin_path)
    candidate_path = create_fresh_candidate(markdown_path)

    markdown = candidate_path.read_text(encoding="utf-8")
    markdown = apply_heading_rules(markdown, rules)
    plugin_result = run_plugin(plugin, markdown)
    candidate_path.write_text(plugin_result.cleaned_markdown, encoding="utf-8")

    report_path = candidate_path.parent / f"{markdown_path.stem}.candidate-report.md"
    write_review_report(
        original_path=markdown_path,
        candidate_path=candidate_path,
        report_path=report_path,
        heading_summary=[rule.rule_id for rule in rules],
        plugin_summary=plugin_result.summary,
        warnings=plugin_result.warnings,
    )
    return CandidateRunResult(candidate_path, report_path, plugin_result.summary, plugin_result.warnings)
```

- [x] **Step 4: Add `candidate-from-artifacts` CLI command**

Modify `mathos_formatting.py`:

```python
def command_candidate_from_artifacts(args: argparse.Namespace) -> int:
    result = core.run_candidate_from_artifacts(
        markdown_path=Path(args.markdown),
        heading_rules_path=Path(args.heading_rules),
        plugin_path=Path(args.plugin),
    )
    _print_json(
        {
            "status": "candidate-written",
            "candidate_path": str(result.candidate_path),
            "report_path": str(result.report_path),
            "summary": result.summary,
            "warnings": result.warnings,
        }
    )
    return 0
```

Add this parser block inside `build_parser()`:

```python
    artifact_parser = subparsers.add_parser(
        "candidate-from-artifacts",
        help="Run a candidate backup from generated heading rules and plugin artifacts",
    )
    artifact_parser.add_argument("markdown")
    artifact_parser.add_argument("--heading-rules", required=True)
    artifact_parser.add_argument("--plugin", required=True)
    artifact_parser.set_defaults(func=command_candidate_from_artifacts)
```

- [x] **Step 5: Run learning command test to verify it passes**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_cli_candidate_from_artifacts_creates_backup_report_and_candidate_plugin -v
```

Expected: PASS.

- [x] **Step 6: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting.py skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: run formatting candidates from generated artifacts"
```

Acceptance note: completed in `85f4f4f`. Verified focused candidate-from-artifacts test, `python -m py_compile skills/mathos-formatting/scripts/mathos_formatting.py skills/mathos-formatting/scripts/mathos_formatting_core.py`, `git diff --check`, and `python -m pytest -q` on 2026-06-06.

## Task 10: Add Approval CLI Command

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Test: `tests/test_mathos_formatting.py`

- [x] **Step 1: Write failing approval CLI test**

Append:

```python
def test_cli_approve_saves_program_after_candidate_review(tmp_path):
    approved_root = tmp_path / "approved"
    original = tmp_path / "book.md"
    candidate = tmp_path / ".mathos-formatting" / "book.candidate.md"
    heading_rules = tmp_path / "heading_rules.json"
    plugin = tmp_path / "content_cleaner.py"
    original.write_text("第一章 集合 …… 1\n", encoding="utf-8")
    candidate.parent.mkdir()
    candidate.write_text("# 第一章 集合\n", encoding="utf-8")
    heading_rules.write_text(
        json.dumps({"rules": [{"id": "chapter", "pattern": "^x$", "replacement": "# x", "flags": []}]}),
        encoding="utf-8",
    )
    plugin.write_text(SAFE_PLUGIN, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "approve",
            "--approved-root",
            str(approved_root),
            "--plugin-id",
            "safe_plugin",
            "--heading-rules",
            str(heading_rules),
            "--plugin",
            str(plugin),
            "--original",
            str(original),
            "--candidate",
            str(candidate),
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "approved"
    assert (approved_root / "safe_plugin" / "metadata.json").exists()
```

- [x] **Step 2: Run approval CLI test to verify it fails**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_cli_approve_saves_program_after_candidate_review -v
```

Expected: FAIL because the command does not exist.

- [x] **Step 3: Add approval CLI command**

Add to `mathos_formatting.py`:

```python
def command_approve(args: argparse.Namespace) -> int:
    heading_rules_path = Path(args.heading_rules)
    heading_rules = json.loads(heading_rules_path.read_text(encoding="utf-8"))
    program_dir = core.save_approved_program(
        approved_root=Path(args.approved_root),
        plugin_id=args.plugin_id,
        heading_rules=heading_rules,
        plugin_path=Path(args.plugin),
        original_path=Path(args.original),
        candidate_path=Path(args.candidate),
        approving_source_path=Path(args.original),
        operations_summary=args.summary,
    )
    _print_json({"status": "approved", "program_dir": str(program_dir)})
    return 0
```

Add this parser block inside `build_parser()`:

```python
    approve_parser = subparsers.add_parser("approve", help="Save an approved candidate result as a reusable program")
    approve_parser.add_argument("--approved-root", required=True)
    approve_parser.add_argument("--plugin-id", required=True)
    approve_parser.add_argument("--heading-rules", required=True)
    approve_parser.add_argument("--plugin", required=True)
    approve_parser.add_argument("--original", required=True)
    approve_parser.add_argument("--candidate", required=True)
    approve_parser.add_argument("--summary", action="append", default=["user approved candidate result"])
    approve_parser.set_defaults(func=command_approve)
```

- [x] **Step 4: Run approval CLI test to verify it passes**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_cli_approve_saves_program_after_candidate_review -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting.py tests/test_mathos_formatting.py
git commit -m "feat: approve formatting programs from cli"
```

Acceptance note: completed in `4383991`. Verified focused approval CLI test, `python -m py_compile skills/mathos-formatting/scripts/mathos_formatting.py`, `git diff --check`, and `python -m pytest -q` on 2026-06-06.

## Task 11: Final Documentation And Full Verification

**Files:**
- Modify: `skills/mathos-formatting/SKILL.md`
- Modify: `skills/mathos-formatting/README.md`
- Modify: `skills/mathos-formatting/references/formatting-program-format.md`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Add a docs coverage test**

Append:

```python
def test_skill_docs_name_backup_approval_and_secret_boundaries():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme_text = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
    reference_text = (SKILL_ROOT / "references" / "formatting-program-format.md").read_text(encoding="utf-8")
    combined = "\n".join([skill_text, readme_text, reference_text])

    assert "candidate backup" in combined
    assert "user approval" in combined
    assert "DEEPSEEK_API_KEY" not in combined
    assert "plugins/approved" in combined
    assert "manual-only" in combined
```

- [ ] **Step 2: Run docs test to verify it passes or exposes missing wording**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_skill_docs_name_backup_approval_and_secret_boundaries -v
```

Expected: PASS. If it fails, add the exact missing phrase to the relevant doc and rerun.

- [ ] **Step 3: Run the full formatter test file**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py -v
```

Expected: all tests in `tests/test_mathos_formatting.py` PASS.

- [ ] **Step 4: Run the broader test suite if the unrelated deletion has been resolved**

First inspect status:

```powershell
git status --short
```

If `tests/test_mathos_pdf_to_md.py` is still deleted from unrelated work, do not restore or stage it inside this task. Run only:

```powershell
python -m pytest tests/test_mathos_formatting.py -v
```

If the unrelated deletion is resolved, run:

```powershell
python -m pytest -v
```

Expected: formatter tests pass either way. Full suite pass is expected only when unrelated workspace changes do not remove existing tests.

- [ ] **Step 5: Commit docs and any verification fixes**

```powershell
git add skills/mathos-formatting/SKILL.md skills/mathos-formatting/README.md skills/mathos-formatting/references/formatting-program-format.md tests/test_mathos_formatting.py
git commit -m "docs: document mathos formatting workflow"
```

## Self-Review Checklist

Spec coverage:

- Skill layout is covered by Task 1.
- Heading and TOC extraction is covered by Task 2.
- Regex heading normalization is covered by Task 3.
- Fresh candidate backups and reports are covered by Task 4.
- Python plugin interface and safety are covered by Task 5.
- Provider settings and artifact parsing are covered by Task 6.
- Approved program save and reuse are covered by Task 7.
- CLI operation is covered by Tasks 8, 9, and 10.
- Documentation and verification are covered by Task 11.

Placeholder scan:

- The plan contains no unresolved placeholder markers.
- Each test step gives exact test code and an exact command.
- Each implementation step gives concrete code or exact file content.

Type consistency:

- `FormattingError`, `HeadingRule`, `PluginResult`, `CandidateRunResult`, and `ApprovedApplyResult` are defined before use.
- CLI commands call functions defined in `mathos_formatting_core.py`.
- Provider parser functions return data consumed by core validation and plugin loading.
