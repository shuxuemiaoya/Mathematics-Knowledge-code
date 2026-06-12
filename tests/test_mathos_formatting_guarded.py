from pathlib import Path
import importlib.util
import json
from types import ModuleType
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "mathos-formatting"
CORE_PATH = SKILL_ROOT / "scripts" / "mathos_formatting_core.py"

core_spec = importlib.util.spec_from_file_location("mathos_formatting_core", CORE_PATH)
core = importlib.util.module_from_spec(core_spec)
assert core_spec.loader is not None
sys.modules["mathos_formatting_core"] = core
core_spec.loader.exec_module(core)


SAMPLE_MARKDOWN = """# 数学

# 目录

# 第一章 数列 …… 1
1.1 数列的概念 …… 2

# 第一章 数列

## 1.1 数列的概念

正文第一段。

![](images/a.png)

<details>
<summary>text_image</summary>

图中文字
</details>

| 项 | 值 |
| --- | --- |
| a_n | 1 |

$$
a_n = n
$$
"""


def _plugin(clean_func):
    plugin = ModuleType("plugin")
    plugin.PLUGIN_ID = "test"
    plugin.PLUGIN_VERSION = "1.0.0"
    plugin.analyze = lambda markdown: {"summary": [], "warnings": []}
    plugin.clean = clean_func
    return plugin


def test_content_cleaner_prompt_forbids_destructive_edits():
    prompt = (SKILL_ROOT / "agents" / "content_cleaner_prompt.md").read_text(encoding="utf-8").lower()

    assert "图片" in prompt
    assert "<details>" in prompt
    assert "公式" in prompt
    assert "表格" in prompt
    assert "警告" in prompt or "报告" in prompt or "analyze" in prompt


def test_preservation_gate_rejects_image_removal():
    plugin = _plugin(lambda markdown: "\n".join(line for line in markdown.splitlines() if not line.startswith("![](")))

    with pytest.raises(core.FormattingError, match="image"):
        core.run_content_plugin_protecting_headings(plugin, SAMPLE_MARKDOWN)


def test_preservation_gate_rejects_details_removal():
    def clean(markdown: str) -> str:
        lines = []
        in_details = False
        for line in markdown.splitlines():
            if line.strip().startswith("<details>"):
                in_details = True
                continue
            if in_details:
                if line.strip().startswith("</details>"):
                    in_details = False
                continue
            lines.append(line)
        return "\n".join(lines)

    with pytest.raises(core.FormattingError, match="details"):
        core.run_content_plugin_protecting_headings(_plugin(clean), SAMPLE_MARKDOWN)


def test_preservation_gate_rejects_math_block_count_change():
    plugin = _plugin(lambda markdown: markdown.replace("$$", "", 1))

    with pytest.raises(core.FormattingError, match="math"):
        core.run_content_plugin_protecting_headings(plugin, SAMPLE_MARKDOWN)


def test_preservation_gate_rejects_table_line_loss():
    plugin = _plugin(lambda markdown: "\n".join(line for line in markdown.splitlines() if "|" not in line))

    with pytest.raises(core.FormattingError, match="table"):
        core.run_content_plugin_protecting_headings(plugin, SAMPLE_MARKDOWN)


def test_preservation_gate_allows_blank_line_normalization():
    plugin = _plugin(lambda markdown: markdown.replace("\n\n\n", "\n\n"))

    result = core.run_content_plugin_protecting_headings(plugin, SAMPLE_MARKDOWN)

    assert result.cleaned_markdown.count("![](") == SAMPLE_MARKDOWN.count("![](")
    assert result.cleaned_markdown.count("<details>") == SAMPLE_MARKDOWN.count("<details>")
    assert result.cleaned_markdown.count("$$") == SAMPLE_MARKDOWN.count("$$")


class DestructiveProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "Heading Rules Prompt" in system_prompt:
            return json.dumps(
                {
                    "rules": [
                        {
                            "id": "chapter",
                            "pattern": r"^# 第一章 数列(?: …… \d+)?$",
                            "replacement": "# 第一章 数列",
                            "flags": ["MULTILINE"],
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if "TOC Detection Prompt" in system_prompt:
            return json.dumps({"toc_start_line": 3, "main_text_start_line": 8}, ensure_ascii=False)
        return """```python
PLUGIN_ID = "destructive"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": ["removed media"], "warnings": []}

def clean(markdown: str) -> str:
    lines = []
    in_details = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("<details>"):
            in_details = True
            continue
        if in_details:
            if stripped.startswith("</details>"):
                in_details = False
            continue
        if stripped.startswith("![]("):
            continue
        lines.append(line)
    return "\\n".join(lines)
```"""


def test_learning_fails_closed_when_generated_cleaner_is_destructive(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    with pytest.raises(core.FormattingError, match="image"):
        core.run_learning_from_provider(
            markdown_path=markdown,
            provider_client=DestructiveProvider(),
            heading_prompt="# Heading Rules Prompt",
            content_prompt="# Content Cleaner Prompt",
            work_dir=work_dir,
        )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    assert "![](images/a.png)" in candidate_text
    assert "<details>" in candidate_text
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["stage"] == "stage4-apply"
    assert "image" in state["errors"][0]


class SuccessfulMockProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self, toc_start_line, main_text_start_line):
        self.toc_start = toc_start_line
        self.main_text_start = main_text_start_line

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "Heading Rules Prompt" in system_prompt:
            return json.dumps(
                {
                    "rules": [
                        {
                            "id": "chapter",
                            "pattern": r"^# 第一章 数列(?: …… \d+)?$",
                            "replacement": "# 第一章 数列",
                            "flags": ["MULTILINE"],
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if "TOC Detection Prompt" in system_prompt:
            return json.dumps({"toc_start_line": self.toc_start, "main_text_start_line": self.main_text_start}, ensure_ascii=False)
        return """```python
PLUGIN_ID = "mock_cleaner"
PLUGIN_VERSION = "1.0.0"
def analyze(markdown: str) -> dict: return {"summary": [], "warnings": []}
def clean(markdown: str) -> str: return markdown
```"""


def test_learning_strips_only_toc(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=SuccessfulMockProvider(toc_start_line=3, main_text_start_line=8),
        heading_prompt="# Heading Rules Prompt",
        content_prompt="# Content Cleaner Prompt",
        work_dir=work_dir,
    )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    # Title heading before TOC must be kept
    assert "# 数学" in candidate_text
    # TOC must be stripped (lines 3 to 7)
    assert "# 目录" not in candidate_text
    assert "1.1 数列的概念 …… 2" not in candidate_text
    # Main text must be kept
    assert "# 第一章 数列" in candidate_text


def test_learning_fallback_when_toc_missing(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=SuccessfulMockProvider(toc_start_line=None, main_text_start_line=8),
        heading_prompt="# Heading Rules Prompt",
        content_prompt="# Content Cleaner Prompt",
        work_dir=work_dir,
    )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    # Fallback: keep entire document intact
    assert "# 数学" in candidate_text
    assert "# 目录" in candidate_text


def test_learning_fallback_when_boundaries_invalid(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    # Mismatched bounds: toc_start_line > main_text_start_line
    core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=SuccessfulMockProvider(toc_start_line=10, main_text_start_line=5),
        heading_prompt="# Heading Rules Prompt",
        content_prompt="# Content Cleaner Prompt",
        work_dir=work_dir,
    )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    # Fallback: keep entire document intact
    assert "# 数学" in candidate_text
    assert "# 目录" in candidate_text
