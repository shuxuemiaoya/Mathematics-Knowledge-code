from pathlib import Path
import importlib.util
import json
import subprocess
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


STAGE1_HEADING_MARKDOWN = """# 目录

# 第十章 数据的收集、整理与描述 100
# 第十一章 不等式与不等式组 120
# Chapter 5 Derivatives 200

# 第十章 数据的收集、整理与描述

#### 小节

正文。

# 第十一章 不等式与不等式组

#### 复习题 (11)

# Chapter 5 Derivatives

#### Review Questions
"""


def _plugin(clean_func):
    plugin = ModuleType("plugin")
    plugin.PLUGIN_ID = "test"
    plugin.PLUGIN_VERSION = "1.0.0"
    plugin.analyze = lambda markdown: {"summary": [], "warnings": []}
    plugin.clean = clean_func
    return plugin


def _content_rules(rules=None, summary=None, warnings=None):
    return {
        "plugin_id": "chapter_inner_markdown_formatter",
        "plugin_version": "2.0.0",
        "schema_version": "1.0.0",
        "stage": "chapter_inner_formatting",
        "description": "test rules",
        "safety": {
            "never_modify_heading_lines": True,
            "heading_line_pattern": r"^\s*#{1,6}\s+.*$",
            "never_delete_images": True,
            "never_rewrite_content": True,
            "never_infer_answers": True,
            "never_modify_markdown_tables": True,
            "preserve_code_blocks": True,
            "preserve_html_blocks": True,
            "preserve_math_blocks": True,
            "preserve_yaml_frontmatter": True,
        },
        "execution_contract": {
            "executor_language": "python",
            "regex_engine": "python_re",
            "allowed_regex_flags": ["MULTILINE", "DOTALL", "IGNORECASE"],
            "default_rule_scope": "non_heading_lines",
            "restore_protected_blocks_order": "reverse",
            "regex_replacement_backslash_policy": "use_lambda_replacement_when_replacement_mode_is_literal",
            "variable_width_lookbehind_allowed": False,
            "dry_run_required_before_write": True,
            "report_required": True,
        },
        "protected_blocks": [
            {"id": "fenced_code_block", "name": "code", "type": "block", "pattern": r"```[\s\S]*?```", "flags": []}
        ],
        "analyze": {"checks": [{"id": "heading_count", "name": "headings", "type": "count", "pattern": r"^#", "flags": ["MULTILINE"], "message": "headings"}]},
        "rules": rules or [],
        "warnings": warnings or [],
        "summary": summary or ["json rules"],
    }


def _heading_rules():
    return {
        "rules": [
            {
                "id": "identity_chapter",
                "pattern": r"^# 第一章 数列$",
                "replacement": "# 第一章 数列",
                "flags": ["MULTILINE"],
            }
        ]
    }


def _batch_processor_source(replacements=None):
    replacements = replacements or []
    replacement_lines = "\n".join(
        f"    text = text.replace({old!r}, {new!r})" for old, new in replacements
    )
    return f'''import os
from pathlib import Path
import re

def get_target_root() -> Path:
    return Path(input().strip()).resolve()

def protect_blocks(text: str):
    return text, []

def restore_blocks(text: str, blocks):
    return text

def replace_in_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
{replacement_lines or "    text = text"}
    path.write_text(text, encoding="utf-8")

def main() -> None:
    root = get_target_root()
    for path in root.rglob("*.md"):
        replace_in_file(path)

if __name__ == "__main__":
    main()
'''


def _title_rewrite_source(mapping=None):
    mapping = mapping or {}
    return "TITLE_REWRITE_MAP: dict[str, str] = " + repr(mapping) + "\n"


def test_content_cleaner_prompt_forbids_destructive_edits():
    prompt = (SKILL_ROOT / "agents" / "content_cleaner_prompt.md").read_text(encoding="utf-8").lower()

    assert "图片" in prompt
    assert "<details>" in prompt
    assert "公式" in prompt
    assert "表格" in prompt
    assert "禁止" in prompt or "不允许" in prompt



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


def test_stage1_audit_is_validation_only():
    # After heading rules applied, audit validates TOC chapter headings remain H1.
    # No enrichment step required — the audit only checks structure.
    summary = core.audit_stage1_headings(STAGE1_HEADING_MARKDOWN, STAGE1_HEADING_MARKDOWN)

    assert "Stage 1 audit: chapter headings preserved as H1" in summary


def test_stage1_audit_rejects_demoted_body_chapter_matching_toc():
    broken = STAGE1_HEADING_MARKDOWN.replace(
        "# 第十一章 不等式与不等式组",
        "#### 第十一章 不等式与不等式组",
    )

    with pytest.raises(core.FormattingError, match="chapter heading.+H1"):
        core.audit_stage1_headings(STAGE1_HEADING_MARKDOWN, broken)



class DestructiveProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "Heading Rules Prompt" in system_prompt:
            return _batch_processor_source([("# 第一章 数列 …… 1", "# 第一章 数列"), ("# 数学", "#### 数学")])
        if "TOC Detection Prompt" in system_prompt:
            return json.dumps({"toc_start_line": 3, "main_text_start_line": 8}, ensure_ascii=False)
        if "Content Cleaner Prompt" in system_prompt:
            return _batch_processor_source([("![](images/a.png)\n\n", "")])
        return _title_rewrite_source()


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
            return _batch_processor_source([("# 第一章 数列 …… 1", "# 第一章 数列"), ("# 数学", "#### 数学")])
        if "TOC Detection Prompt" in system_prompt:
            return json.dumps({"toc_start_line": self.toc_start, "main_text_start_line": self.main_text_start}, ensure_ascii=False)
        if "Content Cleaner Prompt" in system_prompt:
            return _batch_processor_source()
        return _title_rewrite_source()


class JsonRulesProvider(SuccessfulMockProvider):
    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "Content Cleaner Prompt" in system_prompt:
            return _batch_processor_source([("**粗体**", "粗体")])
        return super().chat(system_prompt, user_payload, timeout_seconds, response_format)


class DemotingChapterProvider(SuccessfulMockProvider):
    def __init__(self):
        super().__init__(toc_start_line=1, main_text_start_line=7)

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "Heading Rules Prompt" in system_prompt:
            return _batch_processor_source([("# 第十一章 不等式与不等式组", "#### 第十一章 不等式与不等式组")])
        return super().chat(system_prompt, user_payload, timeout_seconds, response_format)


def test_learning_fails_closed_when_stage1_demotes_body_chapter(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(
        """# 目录

# 第十一章 不等式与不等式组 120

# 第十一章 不等式与不等式组

正文。
""",
        encoding="utf-8",
    )
    work_dir = tmp_path / "mathos-formatting" / "book"

    with pytest.raises(core.FormattingError, match="chapter heading.+H1"):
        core.run_learning_from_provider(
            markdown_path=markdown,
            provider_client=DemotingChapterProvider(),
            heading_prompt="# Heading Rules Prompt",
            content_prompt="# Content Cleaner Prompt",
            work_dir=work_dir,
        )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    assert "#### 第十一章 不等式与不等式组" in candidate_text
    assert (work_dir / "stage1_heading_report.md").exists()
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["stage"] == "stage1-audit"


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
    assert "#### 数学" in candidate_text
    # TOC must be stripped (lines 3 to 7)
    assert "# 目录" not in candidate_text
    assert "1.1 数列的概念 …… 2" not in candidate_text
    # Main text must be kept
    assert "# 第一章 数列" in candidate_text


def test_learning_stage4_uses_python_processor_not_json_rules(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN + "\n正文有 **粗体**。\n", encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    result = core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=JsonRulesProvider(toc_start_line=3, main_text_start_line=8),
        heading_prompt="# Heading Rules Prompt",
        content_prompt="# Content Cleaner Prompt",
        work_dir=work_dir,
    )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    assert "正文有 粗体。" in candidate_text
    assert (work_dir / "heading_processor.py").exists()
    assert (work_dir / "content_processor_response.py").exists()
    assert (work_dir / "content_processor.py").exists()
    assert (work_dir / "title_rewrite_map.py").exists()
    assert not (work_dir / "content_rules_response.json").exists()
    assert not (work_dir / "content_rules.json").exists()
    assert not (work_dir / "content_cleaner.py").exists()
    assert result.summary == [
        "content_processor.py applied",
        "Preservation images: 1 -> 1",
        "Preservation details blocks: 1 -> 1",
        "Preservation math delimiters: 2 -> 2",
        "Preservation table-like lines: 3 -> 3",
        "Final heading audit: all H1-H3 headings verified against TOC",
    ]


def test_json_rule_executor_preserves_headings_and_protected_blocks():
    markdown = """# **标题**

正文 **加粗**。

```
code **keep**
```

$$
x **keep**
$$

| **表** | 值 |
| --- | --- |
"""
    payload = _content_rules(
        rules=[
            {
                "id": "remove_bold",
                "name": "remove bold markers",
                "enabled": True,
                "type": "regex_replace",
                "scope": "non_heading_lines",
                "phase": "pre_clean",
                "risk_level": "low",
                "pattern": r"\*\*([^\n*]+?)\*\*",
                "replacement": "$1",
                "flags": [],
                "replacement_mode": "regex_template",
                "notes": "remove bold markers outside protected regions",
            }
        ]
    )

    result = core.run_content_rules_protecting_headings(payload, markdown)

    assert "# **标题**" in result.cleaned_markdown
    assert "正文 加粗。" in result.cleaned_markdown
    assert "code **keep**" in result.cleaned_markdown
    assert "x **keep**" in result.cleaned_markdown
    assert "| **表** | 值 |" in result.cleaned_markdown


def test_json_rule_executor_fails_closed_on_destructive_image_rule():
    payload = _content_rules(
        rules=[
            {
                "id": "delete_images",
                "name": "delete images",
                "enabled": True,
                "type": "regex_replace",
                "scope": "all_unprotected_text",
                "phase": "post_clean",
                "risk_level": "high",
                "pattern": r"!\[[^\]]*\]\([^)]+\)\n?",
                "replacement": "",
                "flags": [],
                "replacement_mode": "regex_template",
                "notes": "destructive",
            }
        ]
    )

    with pytest.raises(core.FormattingError, match="image"):
        core.run_content_rules_protecting_headings(payload, SAMPLE_MARKDOWN)


def test_json_rule_executor_literal_replacement_handles_latex_backslashes():
    payload = _content_rules(
        rules=[
            {
                "id": "fix_formula",
                "name": "fix formula",
                "enabled": True,
                "type": "regex_replace",
                "scope": "all_unprotected_non_heading_text",
                "phase": "formula_fix",
                "risk_level": "low",
                "pattern": r"\\int_\{\\mathbb\{R\}\}",
                "replacement": r"\complement_{\mathbb{R}}",
                "flags": [],
                "replacement_mode": "literal",
                "notes": "literal replacement",
            }
        ]
    )

    result = core.run_content_rules_protecting_headings(payload, "正文 \\int_{\\mathbb{R}}\n")

    assert r"\complement_{\mathbb{R}}" in result.cleaned_markdown


def test_json_rule_executor_rejects_enabled_image_caption_fix():
    payload = _content_rules(
        rules=[
            {
                "id": "caption",
                "name": "caption",
                "enabled": True,
                "type": "image_caption_fix",
                "scope": "image_caption_region",
                "phase": "image_caption_fix",
                "risk_level": "high",
                "pattern": "图",
                "replacement": "图",
                "flags": [],
                "replacement_mode": "regex_template",
                "notes": "not supported in v1",
            }
        ]
    )

    with pytest.raises(core.FormattingError, match="image_caption_fix"):
        core.validate_content_rules(payload)


def test_legacy_python_cleaner_still_works_for_candidate_approve_and_apply(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 第一章 数列\n\n正文 **加粗**。\n", encoding="utf-8")
    heading_rules_path = tmp_path / "heading_rules.json"
    heading_rules_path.write_text(json.dumps(_heading_rules(), ensure_ascii=False), encoding="utf-8")
    plugin_path = tmp_path / "content_cleaner.py"
    plugin_path.write_text(
        '''
PLUGIN_ID = "legacy"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": ["legacy cleaner"], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("**", "")
'''.lstrip(),
        encoding="utf-8",
    )

    candidate = core.run_candidate_from_artifacts(
        markdown_path=markdown,
        heading_rules_path=heading_rules_path,
        plugin_path=plugin_path,
    )
    assert "正文 加粗。" in candidate.candidate_path.read_text(encoding="utf-8")

    approved_root = tmp_path / "approved"
    program_dir = core.save_approved_program(
        approved_root=approved_root,
        plugin_id="legacy-template",
        heading_rules=_heading_rules(),
        plugin_path=plugin_path,
        content_rules_path=None,
        original_path=markdown,
        candidate_path=candidate.candidate_path,
        approving_source_path=markdown,
        operations_summary=["approved legacy"],
    )
    assert (program_dir / "content_cleaner.py").exists()
    assert not (program_dir / "content_rules.json").exists()

    applied = core.apply_approved_program(program_dir, markdown)
    assert "正文 加粗。" in applied.candidate_path.read_text(encoding="utf-8")


def test_cli_candidate_output_includes_self_check_required_and_next_actions(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 第一章 数列\n\n正文 **加粗**。\n", encoding="utf-8")
    heading_script = tmp_path / "heading_processor.py"
    content_script = tmp_path / "content_processor.py"
    heading_script.write_text(_batch_processor_source(), encoding="utf-8")
    content_script.write_text(_batch_processor_source([("**加粗**", "加粗")]), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "mathos_formatting.py"),
            "candidate-from-artifacts",
            str(markdown),
            "--heading-script",
            str(heading_script),
            "--content-script",
            str(content_script),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(completed.stdout)

    assert payload["self_check_required"] is True
    assert isinstance(payload["next_actions"], list)
    assert any("self-check passes" in action for action in payload["next_actions"])
    assert "正文 加粗。" in Path(payload["candidate_path"]).read_text(encoding="utf-8")


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
    assert "#### 数学" in candidate_text
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
    assert "#### 数学" in candidate_text
    assert "# 目录" in candidate_text


def test_learning_fails_when_main_text_start_line_invalid(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"
    with pytest.raises(core.FormattingError, match="main_text_start_line"):
        core.run_learning_from_provider(
            markdown_path=markdown,
            provider_client=SuccessfulMockProvider(toc_start_line=3, main_text_start_line="invalid"),
            heading_prompt="# Heading Rules Prompt",
            content_prompt="# Content Cleaner Prompt",
            work_dir=work_dir,
        )


def test_content_cleaner_prompt_describes_python_batch_contract():
    prompt_path = SKILL_ROOT / "agents" / "content_cleaner_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8").lower()

    assert "python" in prompt
    assert "import os" in prompt
    assert "from pathlib import path" in prompt
    assert "import re" in prompt
    assert "get_target_root" in prompt
    assert "replace_in_file" in prompt
    assert "def main" in prompt
    assert "完整 python 文件" in prompt
    assert "json" in prompt
    assert "json。" in prompt or "不要输出 json" in prompt or "禁止输出 json" in prompt
    assert "plugin_id" not in prompt
    assert "schema_version" not in prompt
    assert "execution_contract" not in prompt
    assert "def clean" not in prompt
    assert "def analyze" not in prompt
    assert "main()" in prompt or "def main" in prompt


class MockOptimizationProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self, response_source):
        self.response_source = response_source

    def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
        return self.response_source

def test_heading_optimization_success(tmp_path):
    markdown_text = "# 第一章 数列\n## ϰο4\n正文内容\n"
    markdown_file = tmp_path / "book.md"
    markdown_file.write_text(markdown_text, encoding="utf-8")
    
    provider = MockOptimizationProvider(_title_rewrite_source({"## ϰο4": "## 复习参考题 4"}))
    heading_prompt = "# Headings prompt"
    
    mapping = core.run_heading_optimization(markdown_text, provider, heading_prompt)
    assert mapping == {"## ϰο4": "## 复习参考题 4"}

def test_heading_optimization_allows_deepseek_demotion_with_parent_context(tmp_path):
    markdown_text = "# Chapter 5 Sequences\n## Review Questions 5\n正文内容\n"
    provider = MockOptimizationProvider(_title_rewrite_source({"## Review Questions 5": "#### Chapter 5 Review Questions 5"}))
    heading_prompt = "# Headings prompt"

    mapping = core.run_heading_optimization(markdown_text, provider, heading_prompt)

    assert mapping == {"## Review Questions 5": "#### Chapter 5 Review Questions 5"}

def test_heading_optimization_blocks_promotions_to_toc_levels(tmp_path):
    markdown_text = "## ϰο4\n"
    # Mapping to a different level (H1 instead of H2)
    provider = MockOptimizationProvider(_title_rewrite_source({"## ϰο4": "# 复习参考题 4"}))
    heading_prompt = "# Headings prompt"
    
    mapping = core.run_heading_optimization(markdown_text, provider, heading_prompt)
    # Promotions into TOC-owned H1-H3 levels should be discarded by validation safety check.
    assert mapping == {}


@pytest.mark.parametrize(
    "source, message",
    [
        (_batch_processor_source() + "\nos.remove('x.md')\n", "unsafe"),
        ("import os\nimport subprocess\nfrom pathlib import Path\nimport re\n" + _batch_processor_source().split("import re\n", 1)[1], "unsafe import"),
        (_batch_processor_source().replace("text = text", "eval('1 + 1')"), "unsafe call"),
        ("import os\nfrom pathlib import Path\nimport re\nimport urllib\n\ndef get_target_root(): pass\n\ndef protect_blocks(text): pass\n\ndef restore_blocks(text, blocks): pass\n\ndef replace_in_file(path): pass\n\ndef main(): pass\n", "unsafe import"),
        ("import os\nfrom pathlib import Path\nimport re\n\ndef main(): pass\n", "missing functions"),
    ],
)
def test_python_batch_artifact_rejects_dangerous_or_incomplete_source(source, message):
    with pytest.raises(core.FormattingError, match=message):
        core.validate_batch_processor_source(source)


def test_python_batch_artifact_runs_in_sandbox_without_touching_original(tmp_path):
    original = tmp_path / "book.md"
    original.write_text("# 第一章\n\n正文 **加粗**。\n", encoding="utf-8")
    script = tmp_path / "content_processor.py"
    script.write_text(_batch_processor_source([("**加粗**", "加粗")]), encoding="utf-8")

    candidate = core.run_candidate_from_artifacts(
        markdown_path=original,
        heading_script_path=script,
        content_script_path=script,
    )

    assert "正文 加粗。" in candidate.candidate_path.read_text(encoding="utf-8")
    assert "正文 **加粗**。" in original.read_text(encoding="utf-8")


def test_python_batch_artifact_rejects_candidate_too_short(tmp_path):
    original = tmp_path / "book.md"
    original.write_text("# 第一章\n\n" + ("正文内容。\n" * 80), encoding="utf-8")
    heading_script = tmp_path / "heading_processor.py"
    content_script = tmp_path / "content_processor.py"
    heading_script.write_text(_batch_processor_source(), encoding="utf-8")
    content_script.write_text(
        _batch_processor_source([(("正文内容。\n" * 80), "")]),
        encoding="utf-8",
    )

    with pytest.raises(core.FormattingError, match="candidate too short"):
        core.run_candidate_from_artifacts(
            markdown_path=original,
            heading_script_path=heading_script,
            content_script_path=content_script,
        )


def test_title_rewrite_map_python_source_is_parsed_and_applied():
    source = _title_rewrite_source({"## Review Questions 5": "#### Chapter 5 Review Questions 5"})
    mapping = core.validate_title_rewrite_source(source)

    assert mapping == {"## Review Questions 5": "#### Chapter 5 Review Questions 5"}
    assert "#### Chapter 5 Review Questions 5" in core.apply_title_rewrite_map("## Review Questions 5\n", mapping)


def test_candidate_from_artifacts_does_not_enrich_headings(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 第一章 数列\n\n# 小节\n\n正文\n", encoding="utf-8")
    heading_script = tmp_path / "heading_processor.py"
    content_script = tmp_path / "content_processor.py"
    heading_script.write_text(_batch_processor_source(), encoding="utf-8")
    content_script.write_text(_batch_processor_source(), encoding="utf-8")

    result = core.run_candidate_from_artifacts(
        markdown_path=markdown,
        heading_script_path=heading_script,
        content_script_path=content_script,
    )
    candidate_text = result.candidate_path.read_text(encoding="utf-8")
    # Enrichment is removed: headings are only modified by provider artifacts.
    # 小节 should remain as-is (no chapter prefix added by core code).
    assert "第一章 小节" not in candidate_text


def test_apply_approved_program_does_not_enrich_headings(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 第一章 数列\n\n# 小节\n\n正文\n", encoding="utf-8")
    heading_script = tmp_path / "heading_processor.py"
    content_script = tmp_path / "content_processor.py"
    heading_script.write_text(_batch_processor_source(), encoding="utf-8")
    content_script.write_text(_batch_processor_source(), encoding="utf-8")

    candidate = core.run_candidate_from_artifacts(
        markdown_path=markdown,
        heading_script_path=heading_script,
        content_script_path=content_script,
    )

    approved_root = tmp_path / "approved"
    program_dir = core.save_approved_program(
        approved_root=approved_root,
        plugin_id="test-no-enrich",
        heading_script_path=heading_script,
        content_script_path=content_script,
        original_path=markdown,
        candidate_path=candidate.candidate_path,
        approving_source_path=markdown,
        operations_summary=["test"],
    )

    applied = core.apply_approved_program(program_dir, markdown)
    candidate_text = applied.candidate_path.read_text(encoding="utf-8")
    # Enrichment is removed: no chapter prefix should be added by core code.
    assert "第一章 小节" not in candidate_text


def test_apply_approved_program_strips_toc_conditionally(tmp_path):
    # original markdown with a TOC
    original_markdown = "#### 数学\n\n# 目录\n\n# 第一章 数列 …… 1\n\n# 第一章 数列\n\n正文\n"
    markdown = tmp_path / "book.md"
    markdown.write_text(original_markdown, encoding="utf-8")

    heading_script = tmp_path / "heading_processor.py"
    content_script = tmp_path / "content_processor.py"
    heading_script.write_text(_batch_processor_source([("# 第一章 数列 …… 1", "# 第一章 数列")]), encoding="utf-8")
    content_script.write_text(_batch_processor_source(), encoding="utf-8")

    # For save_approved_program, we need a candidate.
    # We strip the TOC manually for the candidate to mimic provider learning.
    candidate_markdown = "#### 数学\n\n# 第一章 数列\n\n正文\n"
    candidate_path = tmp_path / "candidate.md"
    candidate_path.write_text(candidate_markdown, encoding="utf-8")

    approved_root = tmp_path / "approved"
    program_dir = core.save_approved_program(
        approved_root=approved_root,
        plugin_id="test-toc-strip",
        heading_script_path=heading_script,
        content_script_path=content_script,
        original_path=markdown,
        candidate_path=candidate_path,
        approving_source_path=markdown,
        operations_summary=["test"],
    )

    # Verify that metadata.json has toc_signature = True
    metadata = json.loads((program_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["toc_signature"] is True

    # Now apply the approved program to a fresh target (which has a TOC)
    target_markdown = "#### 数学\n\n# 目录\n\n# 第一章 数列 …… 1\n\n# 第一章 数列\n\n正文\n"
    target_path = tmp_path / "target.md"
    target_path.write_text(target_markdown, encoding="utf-8")

    applied = core.apply_approved_program(program_dir, target_path)
    candidate_text = applied.candidate_path.read_text(encoding="utf-8")
    assert "#### 数学" in candidate_text
    assert "# 第一章 数列" in candidate_text
    assert "# 目录" not in candidate_text
    assert "…… 1" not in candidate_text


def test_run_candidate_from_artifacts_applies_title_rewrite_map(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 目录\n\n# 第一章 数列 …… 1\n\n# 第一章 数列\n\n## ϰο4\n", encoding="utf-8")
    heading_script = tmp_path / "heading_processor.py"
    content_script = tmp_path / "content_processor.py"
    title_map = tmp_path / "title_rewrite_map.py"
    heading_script.write_text(_batch_processor_source(), encoding="utf-8")
    content_script.write_text(_batch_processor_source(), encoding="utf-8")
    title_map.write_text(_title_rewrite_source({"## ϰο4": "#### 第一章 数列 复习题 4"}), encoding="utf-8")

    result = core.run_candidate_from_artifacts(
        markdown_path=markdown,
        heading_script_path=heading_script,
        content_script_path=content_script,
        title_rewrite_map_path=title_map,
    )
    candidate_text = result.candidate_path.read_text(encoding="utf-8")
    assert "#### 第一章 数列 复习题 4" in candidate_text
    assert "## ϰο4" not in candidate_text


def test_apply_heading_rules_handles_latex_backslashes_in_replacement(tmp_path):
    markdown = "# 章节\n"
    rules = [
        {
            "id": "latex_heading",
            "pattern": r"^# 章节$",
            "replacement": r"# $\sqrt{2}$",
            "flags": ["MULTILINE"]
        }
    ]
    validated = core.validate_heading_rules({"rules": rules})
    result = core.apply_heading_rules(markdown, validated)
    assert r"# $\sqrt{2}$" in result


def test_parse_json_artifact_with_invalid_escapes():
    bad_json_raw = r'{"notes": "test \circ \d \s \u1234 \\d"}'
    parsed = core.parse_json_artifact_from_text(bad_json_raw)
    parsed_json = json.loads(parsed)
    # \circ, \d, \s are invalid escape sequences so they should be escaped to \\circ, \\d, \\s
    # \u1234 is a valid unicode escape sequence so it should remain untouched
    # \\d is a valid escape sequence (escaped backslash followed by d) so it should remain untouched as \\d
    assert parsed_json["notes"] == "test \\circ \\d \\s \u1234 \\d"


def test_learning_stage1_input_contains_toc_and_h1(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    captured_payloads = []
    class CapturingProvider(SuccessfulMockProvider):
        def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
            if "Heading Rules Prompt" in system_prompt:
                captured_payloads.append(user_payload)
            return super().chat(system_prompt, user_payload, timeout_seconds, response_format)

    core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=CapturingProvider(toc_start_line=3, main_text_start_line=8),
        heading_prompt="# Heading Rules Prompt",
        content_prompt="# Content Cleaner Prompt",
        work_dir=work_dir,
    )

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert "# Table of Contents Sample" in payload
    assert "# All H1 Headings in Original Text" in payload
    assert "# 目录" in payload
    assert "# 第一章 数列" in payload
