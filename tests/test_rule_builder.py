# tests/test_rule_builder.py
import pytest
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

from mathos.formatter.rule_builder import RuleBuilder

@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "dummy-key"}):
        yield



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
        code = "def broken(:\\n    pass"
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
