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

# 小节

正文。

# 第十一章 不等式与不等式组

# 复习题 (11)

# Chapter 5 Derivatives

# Review Questions
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


def test_content_cleaner_prompt_forbids_destructive_edits():
    prompt = (SKILL_ROOT / "agents" / "content_cleaner_prompt.md").read_text(encoding="utf-8").lower()

    assert "图片" in prompt
    assert "<details>" in prompt
    assert "公式" in prompt
    assert "表格" in prompt
    assert "警告" in prompt or "报告" in prompt or "analyze" in prompt


def test_heading_rules_prompt_describes_generic_heading_context_policy():
    prompt = (SKILL_ROOT / "agents" / "heading_rules_prompt.md").read_text(encoding="utf-8")

    assert "复习题 (11)" in prompt
    assert "第十一章 复习题 11" in prompt
    assert "nearest preceding H1 chapter" in prompt
    assert "Review Questions" in prompt


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


def test_enrich_generic_headings_adds_explicit_and_current_chapter_context():
    enriched = core.enrich_generic_headings_with_chapter_context(STAGE1_HEADING_MARKDOWN)

    assert "#### 第十章 小节" in enriched
    assert "#### 第十一章 复习题 11" in enriched
    assert "#### Chapter 5 Review Questions" in enriched
    assert "# 小节" not in enriched
    assert "# 复习题 (11)" not in enriched
    assert "# Review Questions" not in enriched


def test_enrich_generic_headings_forces_contextual_generic_headings_to_h4():
    markdown = """# 第五章 一元一次方程

# 第五章 章末复习
"""

    enriched = core.enrich_generic_headings_with_chapter_context(markdown)
    lines = enriched.splitlines()

    assert "#### 第五章 章末复习" in lines
    assert "# 第五章 章末复习" not in lines


def test_stage1_audit_rejects_demoted_body_chapter_matching_toc():
    broken = STAGE1_HEADING_MARKDOWN.replace(
        "# 第十一章 不等式与不等式组\n\n# 复习题 (11)",
        "#### 第十一章 不等式与不等式组\n\n#### 第十一章 复习题 11",
    )

    with pytest.raises(core.FormattingError, match="chapter heading.+H1"):
        core.audit_stage1_headings(STAGE1_HEADING_MARKDOWN, broken)


def test_stage1_audit_rejects_unenriched_generic_headings():
    with pytest.raises(core.FormattingError, match="generic heading"):
        core.audit_stage1_headings(STAGE1_HEADING_MARKDOWN, STAGE1_HEADING_MARKDOWN)


def test_stage1_audit_rejects_contextual_generic_heading_at_h1():
    bad = core.enrich_generic_headings_with_chapter_context(STAGE1_HEADING_MARKDOWN).replace(
        "#### 第十一章 复习题 11",
        "# 第十一章 复习题 11",
    )

    with pytest.raises(core.FormattingError, match="generic heading.+H4"):
        core.audit_stage1_headings(STAGE1_HEADING_MARKDOWN, bad)


def test_stage1_audit_is_validation_only():
    enriched = core.enrich_generic_headings_with_chapter_context(STAGE1_HEADING_MARKDOWN)
    before = enriched

    summary = core.audit_stage1_headings(STAGE1_HEADING_MARKDOWN, enriched)

    assert enriched == before
    assert "Stage 1 audit: chapter headings preserved as H1" in summary
    assert "Stage 1 audit: generic headings include chapter context" in summary


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
        return json.dumps(
            _content_rules(
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
                ],
                summary=["removed media"],
            ),
            ensure_ascii=False,
        )


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
        return json.dumps(_content_rules(summary=[]), ensure_ascii=False)


class JsonRulesProvider(SuccessfulMockProvider):
    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "Content Cleaner Prompt" in system_prompt:
            return json.dumps(
                _content_rules(
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
                            "notes": "remove bold markers outside headings",
                        }
                    ],
                    summary=["removed bold markers"],
                ),
                ensure_ascii=False,
            )
        return super().chat(system_prompt, user_payload, timeout_seconds, response_format)


class DemotingChapterProvider(SuccessfulMockProvider):
    def __init__(self):
        super().__init__(toc_start_line=1, main_text_start_line=7)

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "Heading Rules Prompt" in system_prompt:
            return json.dumps(
                {
                    "rules": [
                        {
                            "id": "bad_demote_chapter",
                            "pattern": r"^# 第十一章 不等式与不等式组$",
                            "replacement": "#### 第十一章 不等式与不等式组",
                            "flags": ["MULTILINE"],
                        }
                    ]
                },
                ensure_ascii=False,
            )
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
    assert "# 数学" in candidate_text
    # TOC must be stripped (lines 3 to 7)
    assert "# 目录" not in candidate_text
    assert "1.1 数列的概念 …… 2" not in candidate_text
    # Main text must be kept
    assert "# 第一章 数列" in candidate_text


def test_learning_stage4_uses_json_rules_not_python_plugin(tmp_path):
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
    assert (work_dir / "content_rules_response.json").exists()
    assert (work_dir / "content_rules.json").exists()
    assert not (work_dir / "content_cleaner.py").exists()
    assert result.summary == ["removed bold markers", "Preservation images: 1 -> 1", "Preservation details blocks: 1 -> 1", "Preservation math delimiters: 2 -> 2", "Preservation table-like lines: 3 -> 3"]


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


def test_cli_candidate_output_includes_review_required_and_next_actions(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 第一章 数列\n\n正文 **加粗**。\n", encoding="utf-8")
    heading_rules_path = tmp_path / "heading_rules.json"
    heading_rules_path.write_text(json.dumps(_heading_rules(), ensure_ascii=False), encoding="utf-8")
    content_rules_path = tmp_path / "content_rules.json"
    content_rules_path.write_text(
        json.dumps(
            _content_rules(
                rules=[
                    {
                        "id": "remove_bold",
                        "name": "remove bold",
                        "enabled": True,
                        "type": "regex_replace",
                        "scope": "non_heading_lines",
                        "phase": "pre_clean",
                        "risk_level": "low",
                        "pattern": r"\*\*([^\n*]+?)\*\*",
                        "replacement": "$1",
                        "flags": [],
                        "replacement_mode": "regex_template",
                        "notes": "remove bold markers",
                    }
                ]
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "mathos_formatting.py"),
            "candidate-from-artifacts",
            str(markdown),
            "--heading-rules",
            str(heading_rules_path),
            "--content-rules",
            str(content_rules_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(completed.stdout)

    assert payload["review_required"] is True
    assert isinstance(payload["next_actions"], list)
    assert any("approve" in action for action in payload["next_actions"])
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


def test_content_cleaner_prompt_describes_json_rule_contract():
    prompt_path = SKILL_ROOT / "agents" / "content_cleaner_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8").lower()

    assert "合法 json 对象" in prompt
    assert "不输出 python 代码" in prompt
    assert "plugin_id" in prompt
    assert "schema_version" in prompt
    assert "execution_contract" in prompt
    assert "protected_blocks" in prompt
    assert "analyze" in prompt
    assert "rules" in prompt
    assert "warnings" in prompt
    assert "summary" in prompt
    assert "literal_replace" in prompt
    assert "replacement_mode" in prompt
    assert "never_modify_heading_lines" in prompt
    assert "replace_in_file" not in prompt
    assert "def main" not in prompt
    assert "def clean" not in prompt
    assert "def analyze" not in prompt
    assert "批量处理入口" not in prompt


class MockOptimizationProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self, response_json):
        self.response_json = response_json

    def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
        return self.response_json

def test_heading_optimization_success(tmp_path):
    markdown_text = "# 第一章 数列\n## ϰο4\n正文内容\n"
    markdown_file = tmp_path / "book.md"
    markdown_file.write_text(markdown_text, encoding="utf-8")
    
    provider = MockOptimizationProvider('{"## ϰο4": "## 复习参考题 4"}')
    heading_prompt = "# Headings prompt"
    
    mapping = core.run_heading_optimization(markdown_text, provider, heading_prompt)
    assert mapping == {"## ϰο4": "## 复习参考题 4"}

def test_heading_optimization_level_safety(tmp_path):
    markdown_text = "## ϰο4\n"
    # Mapping to a different level (H1 instead of H2)
    provider = MockOptimizationProvider('{"## ϰο4": "# 复习参考题 4"}')
    heading_prompt = "# Headings prompt"
    
    mapping = core.run_heading_optimization(markdown_text, provider, heading_prompt)
    # Different heading levels should be discarded by validation safety check
    assert mapping == {}
