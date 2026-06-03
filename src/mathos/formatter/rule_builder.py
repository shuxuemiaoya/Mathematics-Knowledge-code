"""Two-phase LLM-assisted Rule Builder for generating new formatter classes."""

import ast
import os
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI

from .logger import get_logger

logger = get_logger()

PROMPTS_DIR = Path(__file__).parent / "prompts"


class RuleBuilder:
    """Orchestrates two-phase LLM calls to generate a BaseFormatter subclass.

    This version contains only extraction and validation logic.
    LLM integration is added in Task 3.
    """

    def __init__(self, target_dir: Path, name: str, toc_lines: int = 600):
        self.target_dir = Path(target_dir)
        self.name = name
        self.toc_lines = toc_lines
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY must be set in environment variables. See .env setup.")
        self.llm_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

    def _find_first_md(self) -> Optional[Path]:
        """Find the first .md file in target_dir."""
        if self.target_dir.is_file() and self.target_dir.suffix.lower() == ".md":
            return self.target_dir
        for p in sorted(self.target_dir.rglob("*.md")):
            if not any(part.startswith(".") for part in p.parts):
                return p
        return None

    def _extract_toc(self, md_path: Path) -> str:
        """Extract TOC content from a .md file.

        Strategy:
        1. Read first `toc_lines` lines
        2. Look for literal TOC section (lines with ...... + page numbers,
           or 目录 marker)
        3. If no explicit TOC, fall back to all # heading lines
        """
        text = md_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        first_n = lines[: self.toc_lines]

        # Strategy 1: Find literal TOC block
        toc_pattern = re.compile(r"^.+(?:\.{3,}|…{2,})\s*\d+\s*$")
        toc_lines_found = [line for line in first_n if toc_pattern.match(line)]

        if toc_lines_found:
            toc_start = None
            toc_end = None
            for i, line in enumerate(first_n):
                if toc_pattern.match(line):
                    if toc_start is None:
                        toc_start = max(0, i - 3)
                    toc_end = i + 1
            if toc_start is not None and toc_end is not None:
                return "\n".join(first_n[toc_start:toc_end])

        # Strategy 2: Fall back to heading lines
        heading_lines = [line for line in first_n if re.match(r"^#{1,4}\s+", line)]
        if heading_lines:
            return "\n".join(heading_lines)

        # Strategy 3: Return first N lines raw
        return "\n".join(first_n)

    def _extract_first_h1_section(
        self,
        md_path: Path,
        heading_corrected_text: Optional[str] = None,
    ) -> str:
        """Extract content under the first H1 section."""
        if heading_corrected_text:
            text = heading_corrected_text
        else:
            text = md_path.read_text(encoding="utf-8")

        lines = text.splitlines()
        h1_pattern = re.compile(r"^#\s+")

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
        """Validate generated Python code via AST analysis."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"

        classes = [
            node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ]
        if not classes:
            return False, "No class definition found in generated code."

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

        methods = [
            node.name
            for node in ast.walk(formatter_class)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if "format_string" not in methods:
            return (
                False,
                f"Class '{formatter_class.name}' is missing the "
                f"'format_string' method.",
            )

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
