from pathlib import Path
import importlib.util
import json
import re
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "mathos-formatting"
CORE_PATH = SKILL_ROOT / "scripts" / "mathos_formatting_core.py"
PROVIDER_PATH = SKILL_ROOT / "scripts" / "mathos_provider.py"
LEGACY_CONTENT_RESPONSE = "content_" + "processor_response.py"

core_spec = importlib.util.spec_from_file_location("mathos_formatting_core", CORE_PATH)
core = importlib.util.module_from_spec(core_spec)
assert core_spec.loader is not None
sys.modules["mathos_formatting_core"] = core
core_spec.loader.exec_module(core)

provider_spec = importlib.util.spec_from_file_location("mathos_provider", PROVIDER_PATH)
provider = importlib.util.module_from_spec(provider_spec)
assert provider_spec.loader is not None
sys.modules["mathos_provider"] = provider
provider_spec.loader.exec_module(provider)


def test_provider_defaults_to_deepseek_v4_flash_when_env_has_only_api_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=test-key\n", encoding="utf-8")

    settings = provider.load_provider_settings(env_file)

    assert settings.model == "deepseek-v4-flash"


def test_current_workflow_uses_one_clearly_named_module_per_step():
    scripts = SKILL_ROOT / "scripts"
    expected = {
        "step1_toc_extraction.py",
        "step2_heading_extraction.py",
        "step3_heading_processing.py",
        "step4_toc_removal.py",
        "step5_heading_validation.py",
    }
    legacy_stage_names = {
        "stage1_workflow.py",
        "stage2_3_toc.py",
        "stage4_content.py",
        "stage5_optimize.py",
    }

    assert expected <= {path.name for path in scripts.glob("*.py")}
    assert legacy_stage_names.isdisjoint(path.name for path in scripts.glob("*.py"))

    orchestrator = (scripts / "learning_pipeline.py").read_text(encoding="utf-8")
    for module_name in sorted(expected):
        assert f"from {module_name[:-3]} import" in orchestrator
    assert "stage4-apply" not in orchestrator
    assert "stage4-content" not in orchestrator


def test_prompt_sources_use_step_prefixed_filenames():
    agents = SKILL_ROOT / "agents"
    expected = {
        "step1_toc_detection_prompt.md",
        "step3_heading_processor_prompt.md",
        "step3_heading_expected_result_prompt.md",
        "step5_heading_validation_prompt.md",
        "legacy_heading_optimization_prompt.md",
    }
    superseded = {
        "toc_detection_prompt.md",
        "heading_rules_prompt.md",
        "heading_expected_result_prompt.md",
        "heading_check_prompt.md",
        "content_cleaner_prompt.md",
        "heading_optimization_prompt.md",
    }

    actual = {path.name for path in agents.glob("*_prompt.md")}
    assert expected <= actual
    assert superseded.isdisjoint(actual)


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


HEADING_EXPECTED_RESULT = """- # 第一章 数列
- ## 1.1 数列的概念
"""


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


class HeadingDualOutputProvider:
    def __init__(self, expected_result=HEADING_EXPECTED_RESULT):
        self.expected_result = expected_result
        self.calls = []

    def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
        self.calls.append((system_prompt, user_payload, response_format))
        if "Heading Expected Result Prompt" in system_prompt:
            return self.expected_result
        return _batch_processor_source()


def test_validate_heading_expected_result_requires_safe_markdown():
    assert core.validate_heading_expected_result(HEADING_EXPECTED_RESULT) == HEADING_EXPECTED_RESULT

    invalid_responses = [
        "",
        "```markdown\n- # 第一章 数列\n```\n",
        '{"modified_toc": []}',
        "import os\n\ndef main():\n    pass\n",
    ]
    for response in invalid_responses:
        with pytest.raises(core.FormattingError, match="heading expected result"):
            core.validate_heading_expected_result(response)


def test_step3_writes_expected_result_from_same_payload_without_extra_work_artifacts(tmp_path):
    provider = HeadingDualOutputProvider()
    work_dir = tmp_path / "work"
    candidate = work_dir / "candidate.md"
    source = tmp_path / "book.md"
    original = "# 第一章 数列\n\n# 练习\n"
    source.write_text(original, encoding="utf-8")
    artifacts = {}

    core.run_heading_processing(
        source,
        original,
        "SAME TOC AND HEADINGS PAYLOAD",
        "# Heading Rules Prompt",
        provider,
        work_dir,
        candidate,
        artifacts,
        120,
        toc_markdown="TOC",
    )

    assert len(provider.calls) == 2
    assert provider.calls[0][1] == "SAME TOC AND HEADINGS PAYLOAD"
    assert provider.calls[1][1] == "TOC"
    expected_path = work_dir / "heading_expected_result.md"
    assert expected_path.read_text(encoding="utf-8") == HEADING_EXPECTED_RESULT
    assert artifacts["heading_expected_result"] == expected_path
    assert not (work_dir / "step3_heading_expected_result_prompt.md").exists()
    assert not (work_dir / "heading_expected_result_response.md").exists()


def test_step3_reuses_expected_result_and_regenerates_only_when_missing(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "heading_processor.py").write_text(_batch_processor_source(), encoding="utf-8")
    (work_dir / "heading_expected_result.md").write_text(HEADING_EXPECTED_RESULT, encoding="utf-8")
    source = tmp_path / "book.md"
    source.write_text("# 第一章 数列\n", encoding="utf-8")

    reuse_provider = HeadingDualOutputProvider()
    core.run_heading_processing(
        source,
        "# 第一章 数列\n",
        "PAYLOAD",
        "# Heading Rules Prompt",
        reuse_provider,
        work_dir,
        work_dir / "candidate.md",
        {},
        120,
        toc_markdown="TOC",
    )
    assert reuse_provider.calls == []

    (work_dir / "heading_expected_result.md").unlink()
    regenerate_provider = HeadingDualOutputProvider()
    core.run_heading_processing(
        source,
        "# 第一章 数列\n",
        "PAYLOAD",
        "# Heading Rules Prompt",
        regenerate_provider,
        work_dir,
        work_dir / "candidate.md",
        {},
        120,
        toc_markdown="TOC",
    )
    assert len(regenerate_provider.calls) == 1
    assert "Heading Expected Result Prompt" in regenerate_provider.calls[0][0]


def _title_rewrite_source(mapping=None):
    mapping = mapping or {}
    return "TITLE_REWRITE_MAP: dict[str, str] = " + repr(mapping) + "\n"


def test_preservation_gate_rejects_image_removal():
    cleaned = "\n".join(line for line in SAMPLE_MARKDOWN.splitlines() if not line.startswith("![]("))

    with pytest.raises(core.FormattingError, match="image"):
        core.validate_content_preservation(
            core.content_preservation_counts(SAMPLE_MARKDOWN),
            core.content_preservation_counts(cleaned),
        )


def test_preservation_gate_rejects_math_block_count_change():
    cleaned = SAMPLE_MARKDOWN.replace("$$", "", 1)

    with pytest.raises(core.FormattingError, match="math"):
        core.validate_content_preservation(
            core.content_preservation_counts(SAMPLE_MARKDOWN),
            core.content_preservation_counts(cleaned),
        )


def test_preservation_gate_rejects_table_line_loss():
    cleaned = "\n".join(line for line in SAMPLE_MARKDOWN.splitlines() if "|" not in line)

    with pytest.raises(core.FormattingError, match="table"):
        core.validate_content_preservation(
            core.content_preservation_counts(SAMPLE_MARKDOWN),
            core.content_preservation_counts(cleaned),
        )


def test_preservation_gate_allows_blank_line_normalization():
    cleaned = SAMPLE_MARKDOWN.replace("\n\n\n", "\n\n")

    core.validate_content_preservation(
        core.content_preservation_counts(SAMPLE_MARKDOWN),
        core.content_preservation_counts(cleaned),
    )


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
        if "TOC Verbatim Extraction Prompt" in system_prompt:
            return "3: # 目录\n4: \n5: # 第一章 数列 …… 1\n6: 1.1 数列的概念 …… 2\n"
        if "Heading Rules Prompt" in system_prompt:
            return _batch_processor_source([("# 第一章 数列 …… 1", "# 第一章 数列"), ("# 数学", "#### 数学")])
        if "Heading Expected Result Prompt" in system_prompt:
            return HEADING_EXPECTED_RESULT
        if "Heading Validation Prompt" in system_prompt:
            return json.dumps({"valid": True, "checked_heading_count": 3, "errors": []})
        raise AssertionError(f"unexpected provider prompt: {system_prompt[:80]}")


def test_learning_never_calls_content_modification_provider(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    result = core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=DestructiveProvider(),
        heading_prompt="# Heading Rules Prompt",
        work_dir=work_dir,
    )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    assert "正文第一段。" in candidate_text
    assert not (work_dir / ("step" + "6_llm_response.md")).exists()
    assert not (work_dir / LEGACY_CONTENT_RESPONSE).exists()
    assert not (work_dir / ("content_" + "processor.py")).exists()
    assert result.summary == [
        "Stage 1 processor preserved line count, heading order, and non-heading content",
        "DeepSeek heading validation passed for 2 headings",
    ]
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "candidate-written"
    assert state["stage"] == "complete"
    assert not state["errors"]


class SuccessfulMockProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self, toc_start_line, main_text_start_line):
        self.toc_start = toc_start_line
        self.main_text_start = main_text_start_line

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "TOC Verbatim Extraction Prompt" in system_prompt:
            return "3: # 目录\n4: \n5: # 第一章 数列 …… 1\n6: 1.1 数列的概念 …… 2\n"
        if "Heading Rules Prompt" in system_prompt:
            return _batch_processor_source([("# 第一章 数列 …… 1", "# 第一章 数列"), ("# 数学", "#### 数学")])
        if "Heading Expected Result Prompt" in system_prompt:
            return HEADING_EXPECTED_RESULT
        if "Heading Validation Prompt" in system_prompt:
            count = sum(1 for line in user_payload.splitlines() if re.match(r"^\d+: #{1,6}\s+", line))
            return json.dumps({"valid": True, "checked_heading_count": count, "errors": []})
        raise AssertionError(f"unexpected provider prompt: {system_prompt[:80]}")


class DemotingChapterProvider(SuccessfulMockProvider):
    def __init__(self):
        super().__init__(toc_start_line=1, main_text_start_line=7)

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
        if "TOC Verbatim Extraction Prompt" in system_prompt:
            return "1: # 目录\n2: \n3: # 第十一章 不等式与不等式组 120\n"
        if "Heading Rules Prompt" in system_prompt:
            return _batch_processor_source([("# 第十一章 不等式与不等式组", "#### 第十一章 不等式与不等式组")])
        if "Heading Validation Prompt" in system_prompt:
            return json.dumps({"valid": False, "checked_heading_count": 1, "errors": ["TOC chapter is not H1"]})
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

    with pytest.raises(core.FormattingError, match="rejected"):
        core.run_learning_from_provider(
            markdown_path=markdown,
            provider_client=DemotingChapterProvider(),
            heading_prompt="# Heading Rules Prompt",
            work_dir=work_dir,
        )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    assert "#### 第十一章 不等式与不等式组" in candidate_text
    assert (work_dir / "stage1_heading_report.md").exists()
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["stage"] == "step5-heading-validation"


def test_learning_strips_only_toc(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=SuccessfulMockProvider(toc_start_line=3, main_text_start_line=8),
        heading_prompt="# Heading Rules Prompt",
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


def test_learning_writes_step5_validated_markdown_as_candidate(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN + "\n正文有 **粗体**。\n", encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    result = core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=SuccessfulMockProvider(toc_start_line=3, main_text_start_line=8),
        heading_prompt="# Heading Rules Prompt",
        work_dir=work_dir,
    )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    assert "# 目录" not in candidate_text
    assert "1.1 数列的概念 …… 2" not in candidate_text
    assert "#### 数学" in candidate_text
    assert "正文有 **粗体**。" in candidate_text
    assert (work_dir / "heading_processor.py").exists()
    assert not (work_dir / LEGACY_CONTENT_RESPONSE).exists()
    assert not (work_dir / ("content_" + "processor.py")).exists()
    assert not (work_dir / ("step" + "6_llm_response.md")).exists()
    assert not (work_dir / "title_rewrite_map.py").exists()
    assert not (work_dir / "content_rules_response.json").exists()
    assert not (work_dir / "content_rules.json").exists()
    assert not (work_dir / "content_cleaner.py").exists()
    assert result.summary == [
        "Stage 1 processor preserved line count, heading order, and non-heading content",
        "DeepSeek heading validation passed for 2 headings",
    ]


def test_cli_help_exposes_only_current_public_commands():
    completed = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "mathos_formatting.py"), "--help"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    help_text = completed.stdout

    assert "inspect" in help_text
    assert "learn-from-provider" in help_text
    assert "run" in help_text
    assert ("candidate-from-" + "artifacts") not in help_text
    assert ("apply-" + "appr" + "oved") not in help_text


def test_learning_fallback_when_toc_missing(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    class MissingTocProvider(SuccessfulMockProvider):
        def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
            if "TOC Verbatim Extraction Prompt" in system_prompt:
                return ""
            return super().chat(system_prompt, user_payload, timeout_seconds, response_format)

    with pytest.raises(core.FormattingError, match="empty"):
        core.run_learning_from_provider(
            markdown_path=markdown,
            provider_client=MissingTocProvider(None, None),
            heading_prompt="# Heading Rules Prompt",
            work_dir=work_dir,
        )
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["stage"] == "step1-toc-extraction"


def test_learning_fallback_when_boundaries_invalid(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    class DisjointTocProvider(SuccessfulMockProvider):
        def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
            if "TOC Verbatim Extraction Prompt" in system_prompt:
                return "3: # 目录\n5: # 第一章 数列 …… 1\n"
            return super().chat(system_prompt, user_payload, timeout_seconds, response_format)

    with pytest.raises(core.FormattingError, match="contiguous"):
        core.run_learning_from_provider(
            markdown_path=markdown,
            provider_client=DisjointTocProvider(None, None),
            heading_prompt="# Heading Rules Prompt",
            work_dir=work_dir,
        )


def test_learning_fails_when_toc_text_is_modified(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"
    class ModifiedTocProvider(SuccessfulMockProvider):
        def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
            if "TOC Verbatim Extraction Prompt" in system_prompt:
                return "3: # 目录\n4: \n5: # 第一章 数列 1\n6: 1.1 数列的概念 …… 2\n"
            return super().chat(system_prompt, user_payload, timeout_seconds, response_format)

    with pytest.raises(core.FormattingError, match="verbatim"):
        core.run_learning_from_provider(
            markdown_path=markdown,
            provider_client=ModifiedTocProvider(None, None),
            heading_prompt="# Heading Rules Prompt",
            work_dir=work_dir,
        )


def test_skill_documents_heading_only_workflow():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").lower()

    assert "step 5 heading validation" in skill
    assert "candidate.md" in skill
    assert ("run-step" + "6-content") not in skill
    assert ("step" + "6") not in skill


def test_skill_default_run_contract_is_heading_only():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").lower()

    assert "ordinary formatting run" in skill
    assert "heading" in skill
    assert ("run-step" + "6-content") not in skill
    assert ("concept-" + "extraction") not in skill


def test_heading_prompt_forbids_sys_and_uses_builtin_input_for_sandbox_root():
    prompt = (SKILL_ROOT / "agents" / "step3_heading_processor_prompt.md").read_text(encoding="utf-8").lower()

    assert "markdown 标题结构规范化专家" in prompt
    assert "toc 是唯一权威来源" in prompt
    assert "目录外的标题禁止使用 h1-h3" in prompt
    assert "应降级为 h4-h6" in prompt
    assert "不得自行创造新的 h1、h2、h3" in prompt
    assert "仅处理标题行" in prompt
    assert "title_rewrite_map" in prompt
    assert "只输出 python 文件源码，不输出解释" in prompt


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


def test_title_rewrite_map_python_source_is_parsed_and_applied():
    source = _title_rewrite_source({"## Review Questions 5": "#### Chapter 5 Review Questions 5"})
    mapping = core.validate_title_rewrite_source(source)

    assert mapping == {"## Review Questions 5": "#### Chapter 5 Review Questions 5"}
    assert "#### Chapter 5 Review Questions 5" in core.apply_title_rewrite_map("## Review Questions 5\n", mapping)


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
        work_dir=work_dir,
    )

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert "<!-- BEGIN IMMUTABLE TOC -->" in payload
    assert "<!-- BEGIN BODY HEADINGS -->" in payload
    assert "# 目录" in payload
    assert "1: # 数学" in payload
    assert "# 第一章 数列" in payload


def test_validate_verbatim_toc_response_returns_exact_contiguous_source_span():
    sample = "1: # 数学\n2: \n3: # 目录\n4: # 第一章 数列 …… 1\n5: 1.1 数列的概念 …… 2\n6: \n7: # 第一章 数列\n"
    response = "3: # 目录\n4: # 第一章 数列 …… 1\n5: 1.1 数列的概念 …… 2\n"

    toc = core.validate_verbatim_toc_response(sample, response)

    assert toc.start_line == 3
    assert toc.end_line == 5
    assert toc.markdown == "# 目录\n# 第一章 数列 …… 1\n1.1 数列的概念 …… 2\n"


def test_validate_verbatim_toc_response_keeps_media_in_span_but_not_toc_markdown():
    sample = (
        "104: # 目录\n105: \n106: # 第一章 有理数\n"
        "107: \n108: ![](images/chapter.jpg)\n109: \n110: <details>\n"
        "111: <summary>natural_image</summary>\n112: chapter artwork\n113: </details>\n"
        "114: \n115: 1.1 正数和负数 2\n116: \n117: # 第一章 有理数\n"
    )
    response = "\n".join(sample.splitlines()[:12]) + "\n"

    toc = core.validate_verbatim_toc_response(sample, response)

    assert (toc.start_line, toc.end_line) == (104, 115)
    assert toc.markdown == "# 目录\n# 第一章 有理数\n1.1 正数和负数 2\n"


def test_validate_verbatim_toc_response_accepts_wrapped_entries_and_repeated_headers():
    sample = (
        "1: # 目录\n2: # CONTENTS\n3: 考点 3 导数的基础（三）——\n"
        "4: \n5: 导数的几何意义 026\n6: # 目录\n7: # CONTENTS\n"
        "8: 新情境索引\n9: P154 T12\n10: \n11: # 正文\n"
    )
    response = "\n".join(sample.splitlines()[:9]) + "\n"

    toc = core.validate_verbatim_toc_response(sample, response)

    assert (toc.start_line, toc.end_line) == (1, 9)
    assert toc.markdown == (
        "# 目录\n# CONTENTS\n考点 3 导数的基础（三）——\n"
        "导数的几何意义 026\n# 目录\n# CONTENTS\n新情境索引\nP154 T12\n"
    )


def test_validate_verbatim_toc_response_accepts_entries_before_internal_header():
    sample = (
        "1: # 专题一\n2: # 集合与逻辑\n3: 考点 1 集合的概念 007\n"
        "4: ![](images/toc-page.jpg)\n5: # 目录\n6: # CONTENTS\n"
        "7: 考点 2 集合间的基本关系 008\n8: \n9: # 正文\n"
    )
    response = "\n".join(sample.splitlines()[:7]) + "\n"

    toc = core.validate_verbatim_toc_response(sample, response)

    assert (toc.start_line, toc.end_line) == (1, 7)
    assert toc.markdown == (
        "# 专题一\n# 集合与逻辑\n考点 1 集合的概念 007\n"
        "# 目录\n# CONTENTS\n考点 2 集合间的基本关系 008\n"
    )


def test_validate_verbatim_toc_response_rejects_headerless_toc_like_span():
    sample = "1: # 专题一\n2: 考点 1 集合的概念 007\n3: 考点 2 集合间的基本关系 008\n"

    with pytest.raises(core.FormattingError, match="recognized TOC heading anchor"):
        core.validate_verbatim_toc_response(sample, sample)


def test_validate_verbatim_toc_response_rejects_unfinished_wrapped_entry():
    sample = "1: # 目录\n2: 第一章 数列 1\n3: 考点 3 导数的基础（三）——\n"

    with pytest.raises(core.FormattingError, match="unfinished wrapped TOC entry"):
        core.validate_verbatim_toc_response(sample, sample)


def test_validate_verbatim_toc_response_rejects_body_tail_without_trimming():
    sample = (
        "1: # 目录\n2: 第一章 数列 1\n3: \n4: # 第一章 数列\n"
        "5: 本章学习数列的基本概念。\n"
    )

    with pytest.raises(core.FormattingError, match="unrelated body text"):
        core.validate_verbatim_toc_response(sample, sample)


def test_toc_detection_prompt_explains_wrapped_entries_and_body_boundary():
    prompt = (SKILL_ROOT / "agents" / "step1_toc_detection_prompt.md").read_text(encoding="utf-8")

    assert "wrapped TOC entry" in prompt
    assert "repeated `# 目录` or `# CONTENTS`" in prompt
    assert "stop before the first main-text line" in prompt
    assert "Do not return the remainder of the sample" in prompt
    assert "Begin at the earliest TOC title or entry" in prompt
    assert "later internal `# 目录` or `# CONTENTS` anchor" in prompt
    assert "Do not prepend cover, preface, author, or date lines" in prompt


@pytest.mark.parametrize(
    "response, message",
    [
        ("3: # 目录\n5: 1.1 数列的概念 …… 2\n", "contiguous"),
        ("3: # 目录\n4: # 第一章 数列 1\n", "verbatim"),
        ("3: # 目录\n4: # 第一章 数列 …… 1\n", "incomplete"),
        ("1: # 数学\n2: \n3: # 目录\n4: # 第一章 数列 …… 1\n5: 1.1 数列的概念 …… 2\n", "unrelated"),
        ("3: # 目录\n4: # 第一章 数列 …… 1\n5: 1.1 数列的概念 …… 2\n6: \n7: # 第一章 数列\n", "unrelated"),
    ],
)
def test_validate_verbatim_toc_response_rejects_unsafe_spans(response, message):
    sample = "1: # 数学\n2: \n3: # 目录\n4: # 第一章 数列 …… 1\n5: 1.1 数列的概念 …… 2\n6: \n7: # 第一章 数列\n"

    with pytest.raises(core.FormattingError, match=message):
        core.validate_verbatim_toc_response(sample, response)


def test_extract_body_headings_excludes_toc_code_and_math_blocks():
    markdown = """# 封面

# 目录
# 第一章 数列 …… 1

```md
# 伪标题
```

$$
# 伪数学标题
$$

# 第一章 数列
#### 练习
"""

    headings = core.extract_body_headings(markdown, toc_start_line=3, toc_end_line=4)

    assert [(item.line_number, item.raw_line) for item in headings] == [
        (1, "# 封面"),
        (14, "# 第一章 数列"),
        (15, "#### 练习"),
    ]


def test_heading_check_payload_declares_local_count_and_prompt_accepts_non_toc_h4():
    headings = [
        core.ExtractedHeading(1, "第一章", "# 第一章", 10),
        core.ExtractedHeading(4, "练习", "#### 练习", 20),
    ]

    payload = core.build_toc_and_headings_markdown("# 目录\n# 第一章\n", headings)
    prompt = (SKILL_ROOT / "agents" / "step5_heading_validation_prompt.md").read_text(encoding="utf-8")

    assert "<!-- BODY HEADING COUNT: 2 -->" in payload
    assert "must not be reported as errors" in prompt
    assert "copy the declared body heading count" in prompt.lower()
    assert "`③` and `3` are equivalent" in prompt
    assert "`⑨` and `3` are not equivalent" in prompt
    assert "at most 20 unique errors" in prompt
    assert "Do not repeat an error string" in prompt
    assert "every violation" not in prompt


def test_validate_heading_processor_result_rejects_non_heading_and_parent_context_changes():
    original = "# 第一章 数列\n\n# 练习\n\n正文。\n"

    with pytest.raises(core.FormattingError, match="non-heading"):
        core.validate_heading_processor_result(original, original.replace("正文。", "改写正文。"))

    with pytest.raises(core.FormattingError, match="parent context"):
        core.validate_heading_processor_result(original, original.replace("# 练习", "#### 第一章 练习"))

    with pytest.raises(core.FormattingError, match="parent context"):
        core.validate_heading_processor_result(original, original.replace("# 练习", "#### 1.1 练习"))


def test_validate_heading_check_response_requires_success_and_matching_count():
    summary = core.validate_heading_check_response(
        json.dumps({"valid": True, "checked_heading_count": 2, "errors": []}, ensure_ascii=False),
        expected_heading_count=2,
    )
    assert summary == ["DeepSeek heading validation passed for 2 headings"]

    with pytest.raises(core.FormattingError, match="count"):
        core.validate_heading_check_response(
            json.dumps({"valid": True, "checked_heading_count": 1, "errors": []}),
            expected_heading_count=2,
        )

    with pytest.raises(core.FormattingError, match="rejected"):
        core.validate_heading_check_response(
            json.dumps({"valid": False, "checked_heading_count": 2, "errors": ["non-TOC H1"]}),
            expected_heading_count=2,
        )


def test_validate_heading_check_response_rejects_duplicate_and_oversized_errors():
    duplicate_response = json.dumps(
        {
            "valid": False,
            "checked_heading_count": 2,
            "errors": ["same violation", "same violation"],
        }
    )
    with pytest.raises(core.FormattingError, match="unique"):
        core.validate_heading_check_response(duplicate_response, expected_heading_count=2)

    oversized_response = json.dumps(
        {
            "valid": False,
            "checked_heading_count": 21,
            "errors": [f"violation {index}" for index in range(21)],
        }
    )
    with pytest.raises(core.FormattingError, match="at most 20"):
        core.validate_heading_check_response(oversized_response, expected_heading_count=21)


@pytest.mark.parametrize(
    "error",
    [
        "Circled digits are equivalent, so this is not an error.",
        "圈号数字与阿拉伯数字等价，因此这不是错误。",
    ],
)
def test_validate_heading_check_response_rejects_self_negating_errors(error):
    response = json.dumps(
        {
            "valid": False,
            "checked_heading_count": 1,
            "errors": [error],
        },
        ensure_ascii=False,
    )

    with pytest.raises(core.FormattingError, match="internally contradictory"):
        core.validate_heading_check_response(response, expected_heading_count=1)


def test_validate_heading_check_response_keeps_genuine_candidate_rejections():
    response = json.dumps(
        {
            "valid": False,
            "checked_heading_count": 1,
            "errors": ["Non-TOC heading uses H2."],
        }
    )

    with pytest.raises(core.FormattingError, match="rejected the candidate"):
        core.validate_heading_check_response(response, expected_heading_count=1)


class Stage1WorkflowProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self, heading_check_valid=True):
        self.heading_check_valid = heading_check_valid
        self.calls = []

    def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
        if "TOC Verbatim Extraction Prompt" in system_prompt:
            stage = "toc"
            response = "3: # 目录\n4: \n5: # 第一章 数列 …… 1\n6: 1.1 数列的概念 …… 2\n"
        elif "Heading Rules Prompt" in system_prompt:
            stage = "heading"
            response = _batch_processor_source([("# 数学", "#### 数学")])
        elif "Heading Expected Result Prompt" in system_prompt:
            stage = "heading-expected-result"
            response = HEADING_EXPECTED_RESULT if self.heading_check_valid else "- # Mismatched Heading"
        elif "Heading Validation Prompt" in system_prompt:
            stage = "heading-check"
            errors = [] if self.heading_check_valid else ["non-TOC H1: 数学"]
            response = json.dumps(
                {
                    "valid": self.heading_check_valid,
                    "checked_heading_count": 3,
                    "errors": errors,
                },
                ensure_ascii=False,
            )
        else:
            raise AssertionError(f"unexpected provider prompt: {system_prompt[:80]}")
        self.calls.append((stage, user_payload, response_format))
        return response


def test_learning_uses_new_stage1_provider_order_and_artifacts(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    original_hash = markdown.read_bytes()
    work_dir = tmp_path / "mathos-formatting" / "book"
    provider = Stage1WorkflowProvider()

    result = core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=provider,
        heading_prompt="# Heading Rules Prompt",
        work_dir=work_dir,
    )

    assert [call[0] for call in provider.calls] == [
        "toc",
        "heading",
        "heading-expected-result",
    ]
    assert (work_dir / "toc.md").read_text(encoding="utf-8") == (
        "# 目录\n# 第一章 数列 …… 1\n1.1 数列的概念 …… 2\n"
    )
    assert "<!-- BEGIN IMMUTABLE TOC -->" in (work_dir / "toc_and_headings.md").read_text(encoding="utf-8")
    assert "#### 数学" in (work_dir / "heading_check_input.md").read_text(encoding="utf-8")
    assert (work_dir / "heading_check_response.json").exists()
    expected_prompt_artifacts = {
        "step1_toc_detection_prompt.md",
        "step3_heading_processor_prompt.md",
        "step5_heading_validation_prompt.md",
    }
    superseded_prompt_artifacts = {
        "toc_detection_prompt.md",
        "heading_processor_prompt.md",
        "heading_check_prompt.md",
        "content_cleaner_prompt.md",
    }
    work_files = {path.name for path in work_dir.iterdir() if path.is_file()}
    assert expected_prompt_artifacts <= work_files
    assert superseded_prompt_artifacts.isdisjoint(work_files)
    assert "step3_heading_expected_result_prompt.md" not in work_files
    assert not (work_dir / LEGACY_CONTENT_RESPONSE).exists()
    assert not (work_dir / ("step" + "6_llm_response.md")).exists()
    assert not (work_dir / "title_rewrite_map.py").exists()
    assert "# 目录" not in result.candidate_path.read_text(encoding="utf-8")
    assert markdown.read_bytes() == original_hash
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["toc_start_line"] == 3
    assert state["toc_end_line"] == 6
    assert state["stage1_validated"] is True


def test_learning_stops_before_stage2_when_heading_check_rejects(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"
    provider = Stage1WorkflowProvider(heading_check_valid=False)

    with pytest.raises(core.FormattingError, match="rejected"):
        core.run_learning_from_provider(
            markdown_path=markdown,
            provider_client=provider,
            heading_prompt="# Heading Rules Prompt",
            work_dir=work_dir,
        )

    assert [call[0] for call in provider.calls] == [
        "toc",
        "heading",
        "heading-expected-result",
    ]
    assert not (work_dir / LEGACY_CONTENT_RESPONSE).exists()
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["stage"] == "step5-heading-validation"
    assert state["status"] == "failed"


def _load_automation_runner():
    runner_path = SKILL_ROOT / "scripts" / "automation_runner.py"
    spec = importlib.util.spec_from_file_location("automation_runner", runner_path)
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["automation_runner"] = runner
    spec.loader.exec_module(runner)
    return runner


def test_automated_run_writes_one_passing_digest_and_keeps_source_unchanged(tmp_path):
    runner = _load_automation_runner()
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    original_bytes = markdown.read_bytes()
    work_dir = tmp_path / "mathos-formatting" / "book"

    result = runner.run_automated_formatting(
        markdown_path=markdown,
        provider_client=Stage1WorkflowProvider(),
        heading_prompt="# Heading Rules Prompt",
        work_dir=work_dir,
    )

    digest = json.loads((work_dir / "result-summary.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert digest["status"] == "passed"
    assert digest["failed_stage"] is None
    assert digest["error_artifact"] is None
    assert digest["source_unchanged"] is True
    assert digest["stage1_validated"] is True
    assert digest["preservation_validated"] is True
    assert ("step" + "6_content_processed") not in digest
    assert ("safe_to_" + "appr" + "ove") not in digest
    assert digest["next_action"] == "review-candidate"
    assert Path(digest["candidate_path"]).exists()
    assert markdown.read_bytes() == original_bytes


class InvalidTocProvider(Stage1WorkflowProvider):
    def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
        if "TOC Verbatim Extraction Prompt" in system_prompt:
            self.calls.append(("toc", user_payload, response_format))
            return "not numbered TOC output"
        return super().chat(system_prompt, user_payload, timeout_seconds, response_format)


class InvalidHeadingExpectedResultProvider(Stage1WorkflowProvider):
    def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
        if "Heading Expected Result Prompt" in system_prompt:
            self.calls.append(("heading-expected-result", user_payload, response_format))
            return "```python\nprint('invalid expected result')\n```"
        return super().chat(system_prompt, user_payload, timeout_seconds, response_format)


def test_automated_run_failure_digest_routes_to_exactly_one_error_artifact(tmp_path):
    runner = _load_automation_runner()
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    result = runner.run_automated_formatting(
        markdown_path=markdown,
        provider_client=InvalidTocProvider(),
        heading_prompt="# Heading Rules Prompt",
        work_dir=work_dir,
    )

    digest = json.loads((work_dir / "result-summary.json").read_text(encoding="utf-8"))
    assert result.exit_code == 1
    assert digest["status"] == "failed"
    assert digest["failed_stage"] == "step1-toc-extraction"
    assert Path(digest["error_artifact"]).name == "toc_detection_response.md"
    assert ("safe_to_" + "appr" + "ove") not in digest
    assert len(digest["errors"]) == 1


def test_automated_run_routes_invalid_heading_expected_result_to_new_artifact(tmp_path):
    runner = _load_automation_runner()
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    result = runner.run_automated_formatting(
        markdown_path=markdown,
        provider_client=InvalidHeadingExpectedResultProvider(),
        heading_prompt="# Heading Rules Prompt",
        work_dir=work_dir,
    )

    assert result.exit_code == 1
    assert result.digest["failed_stage"] == "step3-heading-processing"
    assert Path(result.digest["error_artifact"]).name == "heading_expected_result.md"
    assert (work_dir / "heading_expected_result.md").read_text(encoding="utf-8") == (
        "```python\nprint('invalid expected result')\n```"
    )


def test_cli_exposes_fully_automated_run_command():
    cli = SKILL_ROOT / "scripts" / "mathos_formatting.py"
    completed = subprocess.run(
        [sys.executable, str(cli), "run", "--help"],
        text=True,
        capture_output=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    assert "--env" in completed.stdout
    assert "--work-dir" in completed.stdout
    assert "--timeout-seconds" in completed.stdout


def test_automated_run_recovers_with_matching_fingerprint(tmp_path):
    runner = _load_automation_runner()
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / "mathos-formatting" / "book"

    first_provider = Stage1WorkflowProvider()
    first = runner.run_automated_formatting(
        markdown_path=markdown,
        provider_client=first_provider,
        heading_prompt="# Heading Rules Prompt",
        work_dir=work_dir,
    )
    second_provider = Stage1WorkflowProvider()
    second = runner.run_automated_formatting(
        markdown_path=markdown,
        provider_client=second_provider,
        heading_prompt="# Heading Rules Prompt",
        work_dir=work_dir,
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert second.digest["resumed"] is True
    assert [call[0] for call in second_provider.calls] == ["toc"]
