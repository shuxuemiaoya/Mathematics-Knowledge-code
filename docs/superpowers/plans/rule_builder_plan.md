# Rule Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an LLM-assisted Rule Builder that auto-generates `BaseFormatter` subclasses when no existing formatter template matches a new `.md` file.

**Architecture:** Two-phase LLM workflow — Phase 1 extracts TOC from `.md` file and generates heading rules, Phase 2 extracts an H1 section and generates beautification rules. Output is a Python file that drops into `src/mathos/formatter/` alongside existing formatters. Auto-discovery replaces hardcoded `FORMATTERS` dict.

**Tech Stack:** Python 3, OpenAI SDK (DeepSeek), `ast` module for validation, existing `BaseFormatter` class hierarchy.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/mathos/formatter/discovery.py` | Create | Auto-scan `formatter/` for `BaseFormatter` subclasses, return `{mode_name: factory}` dict |
| `src/mathos/formatter/rule_builder.py` | Create | Two-phase LLM orchestrator: TOC extraction, H1 extraction, LLM calls, AST validation, code saving |
| `src/mathos/formatter/prompts/phase1_heading_rules.md` | Create | Editable Phase 1 system prompt template with `{placeholders}` |
| `src/mathos/formatter/prompts/phase2_beautification.md` | Create | Editable Phase 2 system prompt template with `{placeholders}` |
| `src/mathos/formatter/cli.py` | Modify | Replace hardcoded `FORMATTERS` with `discover_formatters()`, add Rule Builder launch when user picks `0` |
| `src/mathos/formatter/__init__.py` | Modify | Export `discover_formatters` and `RuleBuilder` |
| `tests/test_discovery.py` | Create | Unit tests for auto-discovery |
| `tests/test_rule_builder.py` | Create | Unit tests for TOC extraction, AST validation, and integration with mocked LLM |

---

### Task 1: Auto-Discovery Module (`discovery.py`)

**Files:**
- Create: `src/mathos/formatter/discovery.py`
- Create: `tests/test_discovery.py`

- [ ] **Step 1: Write the failing test for discover_formatters**

```python
# tests/test_discovery.py
import pytest
from mathos.formatter.discovery import discover_formatters

def test_discover_finds_textbook_formatter():
    """discover_formatters() should find TextbookFormatter and map it to 'textbook'."""
    formatters = discover_formatters()
    assert "textbook" in formatters
    # The factory should produce a TextbookFormatter instance
    from mathos.formatter.textbook import TextbookFormatter
    instance = formatters["textbook"]()
    assert isinstance(instance, TextbookFormatter)

def test_discover_finds_renjiao_formatter():
    """discover_formatters() should find RenjiaoHighschoolTextbookFormatter."""
    formatters = discover_formatters()
    assert "renjiao-highschool-textbook" in formatters

def test_discover_excludes_base_formatter():
    """BaseFormatter itself should not appear as a mode."""
    formatters = discover_formatters()
    assert "base" not in formatters
    assert "base-formatter" not in formatters

def test_class_name_to_mode_name():
    """Test the naming convention: CamelCaseFormatter -> kebab-case."""
    from mathos.formatter.discovery import _class_name_to_mode
    assert _class_name_to_mode("TextbookFormatter") == "textbook"
    assert _class_name_to_mode("RenjiaoHighschoolTextbookFormatter") == "renjiao-highschool-textbook"
    assert _class_name_to_mode("BeijingAlgebraFormatter") == "beijing-algebra"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_discovery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mathos.formatter.discovery'`

- [ ] **Step 3: Implement discovery.py**

```python
# src/mathos/formatter/discovery.py
"""Auto-discover BaseFormatter subclasses in the formatter package."""

import importlib
import inspect
import pkgutil
import re
from pathlib import Path
from typing import Callable

from .core import BaseFormatter


def _class_name_to_mode(class_name: str) -> str:
    """Convert CamelCaseFormatter to kebab-case mode name.
    
    Examples:
        TextbookFormatter -> textbook
        RenjiaoHighschoolTextbookFormatter -> renjiao-highschool-textbook
        BeijingAlgebraFormatter -> beijing-algebra
    """
    # Remove trailing 'Formatter'
    name = class_name
    if name.endswith("Formatter"):
        name = name[:-len("Formatter")]
    # Insert hyphens before uppercase letters, then lowercase
    name = re.sub(r'(?<=[a-z0-9])([A-Z])', r'-\1', name)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1-\2', name)
    return name.lower()


def discover_formatters() -> dict[str, Callable[[], BaseFormatter]]:
    """Scan the formatter package for all BaseFormatter subclasses.
    
    Returns a dict mapping mode names (kebab-case) to factory callables.
    """
    formatters = {}
    package_dir = Path(__file__).parent
    
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name.startswith('_'):
            continue
        try:
            module = importlib.import_module(f".{module_info.name}", package="mathos.formatter")
        except Exception:
            continue
            
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (issubclass(obj, BaseFormatter) 
                and obj is not BaseFormatter
                and not inspect.isabstract(obj)):
                mode = _class_name_to_mode(name)
                formatters[mode] = lambda cls=obj: cls()
    
    return formatters
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_discovery.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mathos/formatter/discovery.py tests/test_discovery.py
git commit -m "feat: add auto-discovery for formatter classes"
```

---

### Task 2: Rule Builder Core — TOC Extraction & AST Validation (`rule_builder.py`)

**Files:**
- Create: `src/mathos/formatter/rule_builder.py`
- Create: `tests/test_rule_builder.py`

This task builds the extraction and validation logic **without** LLM calls. LLM integration comes in Task 3.

- [ ] **Step 1: Write failing tests for TOC extraction**

```python
# tests/test_rule_builder.py
import pytest
import textwrap
from pathlib import Path
from mathos.formatter.rule_builder import RuleBuilder


@pytest.fixture
def tmp_md_with_toc(tmp_path):
    """Create a .md file with a literal TOC section."""
    content = textwrap.dedent("""\
        # 目录

        第一章 集合与常用逻辑用语……2
        1.1 集合的概念……3
        1.2 集合间的基本关系……10
        第二章 一元二次函数……25
        2.1 等式性质……26
        2.2 不等式性质……30

        # 第一章 集合与常用逻辑用语

        ## 1.1 集合的概念

        集合是数学中最基本的概念之一。
    """)
    md_file = tmp_path / "textbook.md"
    md_file.write_text(content, encoding="utf-8")
    return tmp_path


@pytest.fixture
def tmp_md_no_toc(tmp_path):
    """Create a .md file without a literal TOC — only headings."""
    content = textwrap.dedent("""\
        # 第一章 集合

        ## 1.1 集合的概念

        内容。

        ## 1.2 集合间的基本关系

        更多内容。

        # 第二章 函数

        ## 2.1 函数的概念
    """)
    md_file = tmp_path / "textbook.md"
    md_file.write_text(content, encoding="utf-8")
    return tmp_path


class TestExtractToc:
    def test_extracts_toc_with_page_numbers(self, tmp_md_with_toc):
        rb = RuleBuilder(target_dir=tmp_md_with_toc, name="test")
        md_file = tmp_md_with_toc / "textbook.md"
        toc = rb._extract_toc(md_file)
        assert "集合的概念" in toc
        assert "一元二次函数" in toc

    def test_fallback_extracts_headings_when_no_toc(self, tmp_md_no_toc):
        rb = RuleBuilder(target_dir=tmp_md_no_toc, name="test")
        md_file = tmp_md_no_toc / "textbook.md"
        toc = rb._extract_toc(md_file)
        assert "第一章 集合" in toc
        assert "1.1 集合的概念" in toc


class TestExtractH1Section:
    def test_extracts_first_h1_content(self, tmp_md_no_toc):
        rb = RuleBuilder(target_dir=tmp_md_no_toc, name="test")
        md_file = tmp_md_no_toc / "textbook.md"
        section = rb._extract_first_h1_section(md_file)
        assert "第一章 集合" in section
        assert "1.1 集合的概念" in section
        # Should NOT contain the second H1
        assert "第二章 函数" not in section


class TestValidateCode:
    def test_valid_formatter_passes(self):
        code = textwrap.dedent("""\
            import re
            from .core import BaseFormatter

            class TestFormatter(BaseFormatter):
                def __init__(self):
                    super().__init__()

                def format_string(self, text: str) -> str:
                    return self._cleanup_empty_lines(self._replace_common(text))
        """)
        rb = RuleBuilder(target_dir=Path("."), name="test")
        is_valid, error = rb._validate_code(code)
        assert is_valid, f"Expected valid but got: {error}"

    def test_syntax_error_fails(self):
        code = "def broken(:\n    pass"
        rb = RuleBuilder(target_dir=Path("."), name="test")
        is_valid, error = rb._validate_code(code)
        assert not is_valid
        assert "SyntaxError" in error or "syntax" in error.lower()

    def test_missing_base_class_fails(self):
        code = textwrap.dedent("""\
            class TestFormatter:
                def format_string(self, text):
                    return text
        """)
        rb = RuleBuilder(target_dir=Path("."), name="test")
        is_valid, error = rb._validate_code(code)
        assert not is_valid

    def test_missing_format_string_fails(self):
        code = textwrap.dedent("""\
            from .core import BaseFormatter

            class TestFormatter(BaseFormatter):
                def __init__(self):
                    super().__init__()
        """)
        rb = RuleBuilder(target_dir=Path("."), name="test")
        is_valid, error = rb._validate_code(code)
        assert not is_valid
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rule_builder.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement rule_builder.py (extraction + validation, no LLM)**

```python
# src/mathos/formatter/rule_builder.py
"""Two-phase LLM-assisted Rule Builder for generating new formatter classes."""

import ast
import re
from pathlib import Path
from typing import Optional

from .logger import get_logger

logger = get_logger()

PROMPTS_DIR = Path(__file__).parent / "prompts"


class RuleBuilder:
    """Orchestrates two-phase LLM calls to generate a BaseFormatter subclass."""

    def __init__(self, target_dir: Path, name: str, toc_lines: int = 600):
        self.target_dir = Path(target_dir)
        self.name = name
        self.toc_lines = toc_lines

    def _find_first_md(self) -> Optional[Path]:
        """Find the first .md file in target_dir."""
        if self.target_dir.is_file() and self.target_dir.suffix.lower() == '.md':
            return self.target_dir
        for p in sorted(self.target_dir.rglob("*.md")):
            if not any(part.startswith('.') for part in p.parts):
                return p
        return None

    def _extract_toc(self, md_path: Path) -> str:
        """Extract TOC content from a .md file.
        
        Strategy:
        1. Read first `toc_lines` lines
        2. Look for literal TOC section (lines with ...... + page numbers, or 目录 marker)
        3. If no explicit TOC, fall back to all # heading lines
        """
        text = md_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        first_n = lines[:self.toc_lines]

        # Strategy 1: Find literal TOC block
        toc_pattern = re.compile(r'^.+(?:\.{3,}|…{3,})\s*\d+\s*$')
        toc_lines_found = [l for l in first_n if toc_pattern.match(l)]
        
        if toc_lines_found:
            # Include TOC header and surrounding context
            toc_start = None
            toc_end = None
            for i, line in enumerate(first_n):
                if toc_pattern.match(line):
                    if toc_start is None:
                        # Look backwards for a header like "# 目录"
                        toc_start = max(0, i - 3)
                    toc_end = i + 1
            if toc_start is not None and toc_end is not None:
                return "\n".join(first_n[toc_start:toc_end])

        # Strategy 2: Fall back to heading lines
        heading_lines = [l for l in first_n if re.match(r'^#{1,4}\s+', l)]
        if heading_lines:
            return "\n".join(heading_lines)

        # Strategy 3: Return first N lines raw
        return "\n".join(first_n)

    def _extract_first_h1_section(self, md_path: Path, heading_corrected_text: Optional[str] = None) -> str:
        """Extract content under the first H1 section.
        
        Args:
            md_path: Path to the .md file
            heading_corrected_text: If provided, use this text (already heading-corrected)
                                   instead of reading from disk.
        """
        if heading_corrected_text:
            text = heading_corrected_text
        else:
            text = md_path.read_text(encoding="utf-8")

        lines = text.splitlines()
        h1_pattern = re.compile(r'^#\s+')
        
        first_h1_idx = None
        second_h1_idx = None
        
        for i, line in enumerate(lines):
            if h1_pattern.match(line):
                if first_h1_idx is None:
                    first_h1_idx = i
                elif second_h1_idx is None:
                    second_h1_idx = i
                    break

        if first_h1_idx is None:
            return "\n".join(lines[:200])

        end_idx = second_h1_idx if second_h1_idx else len(lines)
        return "\n".join(lines[first_h1_idx:end_idx])

    def _validate_code(self, code: str) -> tuple[bool, str]:
        """Validate generated Python code via AST analysis.
        
        Checks:
        1. Valid Python syntax
        2. Contains at least one class inheriting from BaseFormatter
        3. That class has a format_string method
        
        Returns (is_valid, error_message).
        """
        # Check syntax
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"

        # Find classes
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        if not classes:
            return False, "No class definition found in generated code."

        # Check for BaseFormatter inheritance
        formatter_class = None
        for cls in classes:
            for base in cls.bases:
                base_name = None
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name == "BaseFormatter":
                    formatter_class = cls
                    break
            if formatter_class:
                break

        if not formatter_class:
            return False, "No class inheriting from BaseFormatter found."

        # Check for format_string method
        methods = [
            node.name for node in ast.walk(formatter_class)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if "format_string" not in methods:
            return False, f"Class '{formatter_class.name}' is missing the 'format_string' method."

        return True, ""

    def _load_prompt(self, filename: str, **kwargs) -> str:
        """Load a prompt template and fill placeholders."""
        template_path = PROMPTS_DIR / filename
        template = template_path.read_text(encoding="utf-8")
        return template.format(**kwargs)

    def _save_formatter(self, code: str) -> Path:
        """Save generated formatter code to the formatter package directory."""
        filename = self.name.replace("-", "_") + ".py"
        target = Path(__file__).parent / filename
        target.write_text(code, encoding="utf-8")
        logger.info(f"Saved formatter to: {target}")
        return target
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rule_builder.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mathos/formatter/rule_builder.py tests/test_rule_builder.py
git commit -m "feat: add Rule Builder core — TOC extraction and AST validation"
```

---

### Task 3: Prompt Templates & LLM Integration

**Files:**
- Create: `src/mathos/formatter/prompts/phase1_heading_rules.md`
- Create: `src/mathos/formatter/prompts/phase2_beautification.md`
- Modify: `src/mathos/formatter/rule_builder.py` — add `phase1_heading_rules()` and `phase2_beautification_rules()` methods

- [ ] **Step 1: Create Phase 1 prompt template**

Create `src/mathos/formatter/prompts/phase1_heading_rules.md`:

```markdown
You are a Markdown formatting rule generator for Chinese mathematics textbooks.

You will receive the table of contents (TOC) from a textbook that was converted from PDF to Markdown via OCR (MinerU).

Your task: generate a Python class that inherits from `BaseFormatter` to fix the heading structure.

## Requirements

1. **Delete the TOC section** — the literal table of contents (lines with page numbers like `......2` or `……25`) must be removed from the output.
2. **Map heading patterns to correct Markdown levels:**
   - Chapter titles (e.g. 第一章, 第1章) → `# ` (H1)
   - Section titles (e.g. 1.1, §1.1) → `## ` (H2)
   - Subsection titles (e.g. 1.1.1, 习题, 练习, 复习参考题) → `### ` (H3)
   - Sub-subsection titles (e.g. 小节练习) → `#### ` (H4)
3. **Handle OCR artifacts**: extra spaces in headings, broken characters, wrong `#` levels from OCR
4. The class must ONLY contain `__init__` (with pre-compiled regexes) and `format_string` method
5. Always call `self._replace_common(text)` at the start and `self._cleanup_empty_lines()` at the end of `format_string`

## BaseFormatter Reference

```python
{base_formatter_source}
```

## Example of a Well-Written Formatter

```python
{example_formatter_source}
```

## TOC Content to Analyze

```
{toc_content}
```

## Output

Output ONLY the Python class code. No explanation, no markdown fences, just the raw Python code starting with `import re`.
```

- [ ] **Step 2: Create Phase 2 prompt template**

Create `src/mathos/formatter/prompts/phase2_beautification.md`:

```markdown
You are a Markdown beautification rule generator for Chinese mathematics textbooks.

You will receive one chapter of content from a textbook. The headings have already been fixed. Your task: add beautification regex rules to make the Markdown aesthetically pleasing in Obsidian.

## Look For These Patterns

- **Callout conversion**: 思考→`> [!think] 思考`, 探究→`> [!explore] 探究`, 观察→`> [!observe] 观察`, 归纳→`> [!tip] 归纳`, 例题→`> [!example]- 例N`
- **Spacing fixes**: remove excessive blank lines between continuation paragraphs (解:, 因为, 所以, etc.), fix indentation
- **Figure/image handling**: convert scattered image+caption pairs into centered format
- **Exercise formatting**: option indentation (A. B. C. D.), question numbering
- **Clean up OCR artifacts**: details blocks, broken formatting

## Rules

1. Add these rules to the existing class below — do NOT remove any existing heading rules
2. Add new pre-compiled regexes to `__init__`
3. Add new rule applications in `format_string` AFTER the existing heading rules but BEFORE `self._cleanup_empty_lines()`
4. The class must still ONLY contain `__init__` and `format_string`

## Current Class (Heading Rules Already Confirmed)

```python
{phase1_code}
```

## Chapter Content to Analyze

```
{h1_section_content}
```

## Output

Output ONLY the complete updated Python class code (including the existing heading rules). No explanation, no markdown fences, just the raw Python code starting with `import re`.
```

- [ ] **Step 3: Add LLM call methods to rule_builder.py**

Add these methods to the `RuleBuilder` class in `src/mathos/formatter/rule_builder.py`:

```python
# Add to imports at top of file
import os
from openai import OpenAI

# Add to RuleBuilder.__init__:
    def __init__(self, target_dir: Path, name: str, toc_lines: int = 600):
        self.target_dir = Path(target_dir)
        self.name = name
        self.toc_lines = toc_lines
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY must be set in environment variables. See .env setup.")
        self.llm_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

# Add these methods:
    def _call_llm(self, system_prompt: str) -> str:
        """Call DeepSeek LLM and return the response content."""
        response = self.llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
            ],
            temperature=0.3,
        )
        content = response.choices[0].message.content
        # Strip markdown fences if the LLM wraps the code
        content = content.strip()
        if content.startswith("```python"):
            content = content[len("```python"):].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        return content

    def _read_source_file(self, relative_path: str) -> str:
        """Read a source file from the formatter package for use in prompts."""
        path = Path(__file__).parent / relative_path
        return path.read_text(encoding="utf-8")

    def phase1_heading_rules(self) -> str:
        """Phase 1: Extract TOC → LLM → return generated Python code.
        
        Returns the generated Python code string.
        """
        md_file = self._find_first_md()
        if not md_file:
            raise FileNotFoundError(f"No .md files found in {self.target_dir}")

        toc_content = self._extract_toc(md_file)
        logger.info(f"Extracted TOC ({len(toc_content)} chars) from {md_file}")

        prompt = self._load_prompt(
            "phase1_heading_rules.md",
            base_formatter_source=self._read_source_file("core.py"),
            example_formatter_source=self._read_source_file("renjiao_highschool_textbook.py"),
            toc_content=toc_content,
        )

        code = self._call_llm(prompt)
        return code

    def phase2_beautification_rules(self, phase1_code: str) -> str:
        """Phase 2: Extract H1 section → LLM → return updated Python code.
        
        Args:
            phase1_code: The confirmed Phase 1 generated class code.
        
        Returns the updated Python code string with beautification rules added.
        """
        md_file = self._find_first_md()
        if not md_file:
            raise FileNotFoundError(f"No .md files found in {self.target_dir}")

        h1_content = self._extract_first_h1_section(md_file)
        logger.info(f"Extracted H1 section ({len(h1_content)} chars) from {md_file}")

        prompt = self._load_prompt(
            "phase2_beautification.md",
            phase1_code=phase1_code,
            h1_section_content=h1_content,
        )

        code = self._call_llm(prompt)
        return code
```

- [ ] **Step 4: Add integration test with mocked LLM**

Append to `tests/test_rule_builder.py`:

```python
from unittest.mock import patch, MagicMock

MOCK_PHASE1_CODE = textwrap.dedent("""\
    import re
    from .core import BaseFormatter

    class TestTextbookFormatter(BaseFormatter):
        def __init__(self):
            super().__init__()
            self.re_toc = re.compile(r'^.+(?:\\.{3,}|…{3,})\\s*\\d+\\s*$', re.MULTILINE)
            self.re_chapter = re.compile(r'(?m)^#\\s+(第[一二三四五六七八九十]+章[^\\r\\n]*)$')

        def format_string(self, text: str) -> str:
            new = self._replace_common(text)
            new = self.re_toc.sub('', new)
            new = self.re_chapter.sub(r'# \\1', new)
            return self._cleanup_empty_lines(new)
""")


class TestPhase1Integration:
    @patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"})
    @patch("mathos.formatter.rule_builder.OpenAI")
    def test_phase1_returns_valid_code(self, mock_openai_class, tmp_md_with_toc):
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = MOCK_PHASE1_CODE
        mock_client.chat.completions.create.return_value = mock_response

        rb = RuleBuilder(target_dir=tmp_md_with_toc, name="test-textbook")
        code = rb.phase1_heading_rules()

        is_valid, error = rb._validate_code(code)
        assert is_valid, f"Generated code is invalid: {error}"
        assert "TestTextbookFormatter" in code
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_rule_builder.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/mathos/formatter/prompts/ src/mathos/formatter/rule_builder.py tests/test_rule_builder.py
git commit -m "feat: add prompt templates and LLM integration for Rule Builder"
```

---

### Task 4: CLI Integration

**Files:**
- Modify: `src/mathos/formatter/cli.py`
- Modify: `src/mathos/formatter/__init__.py`

- [ ] **Step 1: Update cli.py to use auto-discovery and launch Rule Builder**

Replace the content of `src/mathos/formatter/cli.py`:

```python
import argparse
from pathlib import Path
from .logger import get_logger
from .discovery import discover_formatters

logger = get_logger()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Markdown formatter for the mathematics knowledge base")
    parser.add_argument("--dir", type=str, required=True, help="Directory containing markdown files")

    formatters = discover_formatters()
    mode_choices = list(formatters.keys())
    mode_help = "Formatting mode: " + " | ".join(mode_choices)

    parser.add_argument("--mode", type=str,
                        choices=mode_choices,
                        help=mode_help)
    parser.add_argument("--backup", action="store_true", help="Create .bak files before modifying")
    parser.add_argument("--dry-run", action="store_true", help="Report files that would change without writing them")
    parser.add_argument("--toc-lines", type=int, default=600, help="Number of lines to extract as TOC (default: 600)")

    args = parser.parse_args(argv)

    if not args.mode:
        print("未指定转换模式。检测到以下已存在的格式修改方案：")
        for i, m in enumerate(mode_choices, 1):
            print(f"{i}. {m}")
        print("0. 都不适用，创建新规则")

        while True:
            try:
                choice = input("请选择要调用的方案序号 (0-N): ")
                choice_idx = int(choice)
                if choice_idx == 0:
                    return _launch_rule_builder(args.dir, args.backup, args.dry_run, args.toc_lines)
                if 1 <= choice_idx <= len(mode_choices):
                    args.mode = mode_choices[choice_idx - 1]
                    break
                else:
                    print(f"无效序号，请输入 0 到 {len(mode_choices)} 之间的数字。")
            except ValueError:
                print("无效输入，请输入数字。")

    return 0 if run_formatter(args.dir, args.mode, args.backup, dry_run=args.dry_run) else 1


def _launch_rule_builder(dir_path: str, backup: bool, dry_run: bool, toc_lines: int):
    """Interactive Rule Builder: generate a new formatter via LLM."""
    from .rule_builder import RuleBuilder

    name = input("请输入新格式化器的名称 (英文, 如 beijing-algebra): ").strip()
    if not name:
        print("名称不能为空。")
        return 1

    try:
        rb = RuleBuilder(target_dir=Path(dir_path), name=name, toc_lines=toc_lines)
    except ValueError as e:
        print(f"错误: {e}")
        return 1

    # Phase 1: Heading rules
    max_retries = 3
    phase1_code = None
    for attempt in range(max_retries):
        print(f"\n[Phase 1] 正在从第一个 .md 文件提取目录 (前{toc_lines}行)...")
        print("正在发送到 LLM 分析目录结构...")
        try:
            code = rb.phase1_heading_rules()
        except Exception as e:
            print(f"LLM 调用失败: {e}")
            return 1

        is_valid, error = rb._validate_code(code)
        if not is_valid:
            print(f"⚠️  生成的代码无效: {error}")
            if attempt < max_retries - 1:
                print("正在重新生成...")
                continue
            else:
                print("已达最大重试次数，请手动编写格式化器。")
                return 1

        print("\n✅ LLM 已生成标题规则。请审核：")
        print("─" * 60)
        print(code)
        print("─" * 60)

        choice = input("\n确认使用这些规则? [Y/n/r(重新生成)]: ").strip().lower()
        if choice in ('', 'y', 'yes'):
            phase1_code = code
            break
        elif choice == 'r':
            continue
        else:
            print("已取消。")
            return 0

    if phase1_code is None:
        print("已达最大重试次数。")
        return 1

    # Phase 2: Beautification rules
    phase2_code = None
    for attempt in range(max_retries):
        print(f"\n[Phase 2] 正在提取第一个 H1 章节内容...")
        print("正在发送到 LLM 生成美化规则...")
        try:
            code = rb.phase2_beautification_rules(phase1_code)
        except Exception as e:
            print(f"LLM 调用失败: {e}")
            return 1

        is_valid, error = rb._validate_code(code)
        if not is_valid:
            print(f"⚠️  生成的代码无效: {error}")
            if attempt < max_retries - 1:
                print("正在重新生成...")
                continue
            else:
                print("跳过美化规则，仅使用标题规则。")
                phase2_code = phase1_code
                break

        print("\n✅ LLM 已添加美化规则。请审核：")
        print("─" * 60)
        print(code)
        print("─" * 60)

        choice = input("\n确认? [Y/n/r(重新生成)]: ").strip().lower()
        if choice in ('', 'y', 'yes'):
            phase2_code = code
            break
        elif choice == 'r':
            continue
        else:
            print("跳过美化规则，仅使用标题规则。")
            phase2_code = phase1_code
            break

    # Save and run
    final_code = phase2_code or phase1_code
    saved_path = rb._save_formatter(final_code)
    mode_name = name.replace("_", "-")
    print(f"\n✅ 已保存: {saved_path}")
    print(f"✅ 已注册模式: {mode_name}")
    print(f"\n正在以 dry-run 模式运行新格式化器...")

    return 0 if run_formatter(dir_path, mode_name, backup, dry_run=True) else 1


def run_formatter(dir_path: str, mode: str, backup: bool = False, dry_run: bool = False):
    root = Path(dir_path).expanduser().resolve()
    formatters = discover_formatters()
    logger.info(f"Starting formatter on {root} with mode={mode}, dry_run={dry_run}")

    if not root.exists():
        logger.error(f"Invalid path: {root}")
        return False

    if mode not in formatters:
        logger.error(f"Unknown mode: {mode}. Available: {', '.join(formatters.keys())}")
        return False

    formatter = formatters[mode]()

    processed_count = 0
    updated_count = 0

    if root.is_file():
        files = [root] if root.suffix.lower() == '.md' else []
    else:
        files = root.rglob("*.md")

    for p in files:
        if any(part.startswith('.') for part in p.parts):
            continue

        processed_count += 1
        success = formatter.process_file(p, backup=backup, dry_run=dry_run)
        if success:
            updated_count += 1

    action = "would update" if dry_run else "updated"
    logger.info(f"Formatting complete. Processed {processed_count} files, {action} {updated_count} files.")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Update __init__.py**

```python
# src/mathos/formatter/__init__.py
from .core import BaseFormatter
from .textbook import TextbookFormatter
from .renjiao_highschool_textbook import RenjiaoHighschoolTextbookFormatter
from .discovery import discover_formatters
from .rule_builder import RuleBuilder

__all__ = ["BaseFormatter", "TextbookFormatter", "discover_formatters", "RuleBuilder"]
```

Note: Remove the `ExerciseFormatter` import if `exercise.py` doesn't exist in the formatter directory (it's imported in `cli.py` but the file is missing from the directory listing).

- [ ] **Step 3: Run existing tests to verify nothing is broken**

Run: `python -m pytest -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/mathos/formatter/cli.py src/mathos/formatter/__init__.py
git commit -m "feat: integrate Rule Builder into CLI with auto-discovery"
```

---

### Task 5: End-to-End Verification & Documentation

**Files:**
- Modify: `src/mathos/formatter/../../AGENTS.md` — (no change needed, existing docs cover `mk-format`)
- Modify: `C:\Users\Oven\.gemini\config\skills\mathos-formatter\SKILL.md` — add Rule Builder usage
- Modify: `C:\Users\Oven\.gemini\config\skills\mathos-formatter\references\formatting-rules.md` — add Rule Builder paths

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Verify auto-discovery finds all existing formatters**

Run: `python -c "from mathos.formatter.discovery import discover_formatters; print(list(discover_formatters().keys()))"`
Expected: Output includes `textbook`, `renjiao-highschool-textbook`, and any other existing formatters

- [ ] **Step 3: Verify CLI help shows all discovered modes**

Run: `mk-format --help`
Expected: `--mode` shows all discovered formatters

- [ ] **Step 4: Update skill SKILL.md**

Add to `C:\Users\Oven\.gemini\config\skills\mathos-formatter\SKILL.md` under Workflow:

```markdown
7. If no existing mode matches, run `mk-format --dir "<target-dir>"` without `--mode` and choose `0` to launch the Rule Builder.
   The Rule Builder uses LLM to generate a new formatter class in two phases:
   - Phase 1: Extracts TOC → generates heading rules
   - Phase 2: Extracts chapter content → generates beautification rules
   Requires `DEEPSEEK_API_KEY` in environment.
```

- [ ] **Step 5: Update formatting-rules.md reference**

Add to `references/formatting-rules.md`:

```markdown
## Rule Builder

- Rule Builder: `src/mathos/formatter/rule_builder.py`
- Auto-discovery: `src/mathos/formatter/discovery.py`
- Prompt templates: `src/mathos/formatter/prompts/`

### Creating New Formatters via LLM

Run without `--mode` and pick option `0`:

```powershell
mk-format --dir "<target-dir>"
```

Generated formatters are saved to `src/mathos/formatter/<name>.py` and automatically discovered on next run.
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: update skill and reference docs for Rule Builder"
```
