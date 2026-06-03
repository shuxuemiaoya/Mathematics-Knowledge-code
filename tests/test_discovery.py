# tests/test_discovery.py
import pytest
from mathos.formatter.discovery import discover_formatters

def test_discover_finds_textbook_formatter():
    """discover_formatters() should find TextbookFormatter and map it to 'textbook'."""
    formatters = discover_formatters()
    assert "textbook" in formatters
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
