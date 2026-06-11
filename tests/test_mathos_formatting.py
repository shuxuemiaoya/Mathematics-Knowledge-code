from pathlib import Path
import importlib.util
import json
import py_compile
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "mathos-formatting"
REGISTRY_PATH = REPO_ROOT / "docs" / "agent" / "skill-registry.md"
PROVIDER_PATH = SKILL_ROOT / "scripts" / "mathos_provider.py"
CLI_PATH = SKILL_ROOT / "scripts" / "mathos_formatting.py"

provider_spec = importlib.util.spec_from_file_location("mathos_provider", PROVIDER_PATH)
provider = importlib.util.module_from_spec(provider_spec)
assert provider_spec.loader is not None
sys.modules["mathos_provider"] = provider
provider_spec.loader.exec_module(provider)


def _registry_section(skill_path: str) -> str:
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    start = text.index(f"### `{skill_path}`")
    next_section = text.find("\n### `", start + 1)
    if next_section == -1:
        return text[start:]
    return text[start:next_section]


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


def test_formatting_skill_scaffold_contract():
    for script_name in [
        "mathos_formatting.py",
        "mathos_formatting_core.py",
        "mathos_provider.py",
    ]:
        py_compile.compile(str(SKILL_ROOT / "scripts" / script_name), doraise=True)

    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme_text = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
    combined_text = f"{skill_text}\n{readme_text}".lower()

    assert "name: mathos-formatting" in skill_text
    assert "adaptive markdown formatting operator" in skill_text.lower()
    assert "status: operational" in combined_text
    assert "candidate-from-artifacts" in combined_text
    assert "apply-approved" in combined_text
    assert "approve" in combined_text
    assert "candidate backup" in combined_text
    assert "user approval" in combined_text


def test_formatting_cli_requires_an_explicit_command():
    result = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "mathos_formatting.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "the following arguments are required: command" in result.stderr.lower()
    assert "inspect" in result.stderr
    assert "apply-approved" in result.stderr


def test_formatting_skill_registry_marks_scaffold_non_operational():
    section = _registry_section("skills/mathos-formatting").lower()

    assert "mathos adaptive markdown formatting" in section
    assert "candidate backup" in section
    assert "user approval" in section
    assert "reserved, inactive" not in section
    assert "must not contain a `skill.md`" not in section


import importlib.util


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
    assert result.heading_like_lines == [
        "1.1 集合的概念…… 2",
        "阅读与思考 集合中元素的个数 …… 15",
    ]
    assert result.heading_level_distribution == {1: 4, 2: 1}
    assert result.h1_sections[0].heading == "数学"
    assert any(block.kind == "code_fence" for block in result.protected_blocks)
    assert any(block.kind == "math_block" for block in result.protected_blocks)
    assert any(block.kind == "image" for block in result.protected_blocks)


def test_extract_structure_keeps_fullwidth_dot_leader_entries_in_toc():
    markdown = """# 目录

# 第一章 集合 ．．．． 1

# 第一章 集合
"""

    result = core.extract_structure(markdown, source_label="toc.md")

    assert result.toc_block is not None
    assert "# 第一章 集合 ．．．． 1" in result.toc_block.text
    assert result.toc_block.end_line == 4


def test_extract_structure_protects_unclosed_backtick_code_fence_through_eof():
    markdown = """# 正文

```python
# not a heading
## not another heading
"""

    result = core.extract_structure(markdown, source_label="code.md")

    assert [heading.text for heading in result.headings] == ["正文"]
    assert result.protected_blocks == [
        core.TextBlock(
            "code_fence",
            "```python\n# not a heading\n## not another heading",
            3,
            5,
        )
    ]


def test_extract_structure_protects_tilde_code_fences():
    markdown = """# 正文

~~~python
# not a heading
~~~

## 真实小节
"""

    result = core.extract_structure(markdown, source_label="tilde.md")

    assert [heading.text for heading in result.headings] == ["正文", "真实小节"]
    assert any(
        block.kind == "code_fence"
        and block.start_line == 3
        and block.end_line == 5
        for block in result.protected_blocks
    )


def test_extract_structure_protects_unclosed_math_block_through_eof():
    markdown = """# 正文

$$
# not a heading
## not another heading
"""

    result = core.extract_structure(markdown, source_label="math.md")

    assert [heading.text for heading in result.headings] == ["正文"]
    assert result.protected_blocks == [
        core.TextBlock(
            "math_block",
            "$$\n# not a heading\n## not another heading",
            3,
            5,
        )
    ]


def test_extract_structure_ignores_math_delimiter_inside_code_fence():
    markdown = """# Before

```text
$$
```

# After
"""

    result = core.extract_structure(markdown, source_label="code-math.md")

    assert [heading.text for heading in result.headings] == ["Before", "After"]
    assert [block.kind for block in result.protected_blocks] == ["code_fence"]


def test_extract_structure_ignores_code_fence_marker_inside_math_block():
    markdown = """# Before

$$
```text
$$

# After
"""

    result = core.extract_structure(markdown, source_label="math-code.md")

    assert [heading.text for heading in result.headings] == ["Before", "After"]
    assert [block.kind for block in result.protected_blocks] == ["math_block"]


def test_extract_structure_honors_longer_backtick_fence_lengths():
    markdown = """# Before

````text
```
# not heading
````

# After
"""

    result = core.extract_structure(markdown, source_label="long-fence.md")

    assert [heading.text for heading in result.headings] == ["Before", "After"]
    assert [block.kind for block in result.protected_blocks] == ["code_fence"]


def test_extract_structure_allows_indented_closing_code_fence():
    markdown = """# Before

```text
# not heading
   ```

# After
"""

    result = core.extract_structure(markdown, source_label="indented-close.md")

    assert [heading.text for heading in result.headings] == ["Before", "After"]


def test_extract_structure_finds_atx_headings_indented_up_to_three_spaces():
    markdown = """   # Indented Heading
    # code-like heading

# After
"""

    result = core.extract_structure(markdown, source_label="indented-heading.md")

    assert [heading.text for heading in result.headings] == ["Indented Heading", "After"]


def test_extract_structure_repeated_page_leader_h1_terminates_toc():
    markdown = """# 目录

# 第一章 集合 …… 1

# 第一章 集合 …… 1

## 1.1 集合的概念
"""

    result = core.extract_structure(markdown, source_label="repeated-toc.md")

    assert result.toc_block is not None
    assert result.toc_block.text == "# 目录\n\n# 第一章 集合 …… 1\n"
    assert result.h1_sections[2].heading == "第一章 集合 …… 1"


def test_extract_structure_space_separated_page_numbers():
    markdown = """# 目录

# 第一章 集合 1

# 第一章 集合

## 1.1 集合的概念
"""
    result = core.extract_structure(markdown, source_label="space-separated-toc.md")
    assert result.toc_block is not None
    assert "# 第一章 集合 1" in result.toc_block.text
    # The first real H1 should start at "# 第一章 集合"
    assert result.toc_block.end_line == 4



def test_extract_structure_ignores_code_fence_openers_indented_four_spaces():
    markdown = """# Before

    ```
# After
"""

    result = core.extract_structure(markdown, source_label="indented-opener.md")

    assert [heading.text for heading in result.headings] == ["Before", "After"]
    assert result.protected_blocks == []


def test_extract_structure_parses_atx_closing_hash_sequences():
    markdown = """# 目录 ###

## 1.1 标题 ##

# 标题#
"""

    result = core.extract_structure(markdown, source_label="closing-hashes.md")

    assert [heading.text for heading in result.headings] == ["目录", "1.1 标题", "标题#"]
    assert result.toc_block is not None


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


def test_heading_rules_reject_non_object_rule():
    rules = {"rules": ["bad"]}

    with pytest.raises(core.FormattingError, match="heading rule must be an object"):
        core.validate_heading_rules(rules)


def test_heading_rules_broad_rule_preserves_code_fence_exactly():
    rules = core.validate_heading_rules(
        {
            "rules": [
                {
                    "id": "broad",
                    "pattern": r"^(.+)$",
                    "replacement": r"# \1",
                    "flags": ["MULTILINE"],
                }
            ]
        }
    )
    code_block = "```python\nprint('keep me')\n```\n"
    markdown = f"intro\n\n{code_block}\noutro\n"

    cleaned = core.apply_heading_rules(markdown, rules)

    assert code_block in cleaned
    assert "# ```python" not in cleaned
    assert "# print('keep me')" not in cleaned


def test_heading_rules_broad_rule_preserves_math_block_exactly():
    rules = core.validate_heading_rules(
        {
            "rules": [
                {
                    "id": "broad",
                    "pattern": r"^(.+)$",
                    "replacement": r"# \1",
                    "flags": ["MULTILINE"],
                }
            ]
        }
    )
    math_block = "$$\na^2 + b^2 = c^2\n$$\n"
    markdown = f"intro\n\n{math_block}\noutro\n"

    cleaned = core.apply_heading_rules(markdown, rules)

    assert math_block in cleaned
    assert "# $$" not in cleaned
    assert "# a^2 + b^2 = c^2" not in cleaned


def test_heading_rules_broad_rule_still_applies_to_normal_text():
    rules = core.validate_heading_rules(
        {
            "rules": [
                {
                    "id": "broad",
                    "pattern": r"^(.+)$",
                    "replacement": r"# \1",
                    "flags": ["MULTILINE"],
                }
            ]
        }
    )
    markdown = "intro\n\n```\nkeep code\n```\n\noutro\n"

    cleaned = core.apply_heading_rules(markdown, rules)

    assert cleaned.startswith("# intro\n")
    assert cleaned.endswith("\n# outro\n")


def test_heading_rules_translates_js_backreferences():
    rules = core.validate_heading_rules(
        {
            "rules": [
                {
                    "id": "js-style",
                    "pattern": r"^Chapter (\w+) - (.+)$",
                    "replacement": "## $1: $2 ($0)",
                    "flags": ["MULTILINE"],
                }
            ]
        }
    )
    markdown = "Chapter One - Introduction\n"
    cleaned = core.apply_heading_rules(markdown, rules)
    assert cleaned == "## One: Introduction (Chapter One - Introduction)\n"



def test_candidate_backup_is_recreated_from_original_each_iteration(tmp_path):
    original = tmp_path / "book.md"
    original.write_text("第一章 集合 …… 1\n\nbody\n", encoding="utf-8")

    first_candidate = core.create_fresh_candidate(original)
    first_candidate.write_text("mutated candidate\n", encoding="utf-8")

    second_candidate = core.create_fresh_candidate(original)

    assert first_candidate == second_candidate
    assert second_candidate.read_text(encoding="utf-8") == "第一章 集合 …… 1\n\nbody\n"
    assert original.read_text(encoding="utf-8") == "第一章 集合 …… 1\n\nbody\n"


def test_create_fresh_candidate_rejects_markdown_directory(tmp_path):
    original = tmp_path / "book.md"
    original.mkdir()

    with pytest.raises(core.FormattingError, match="source Markdown file must be a file"):
        core.create_fresh_candidate(original)


def test_unified_markdown_diff_keeps_control_lines_separate():
    diff_text = core.unified_markdown_diff("a\n", "b\n", "orig.md", "cand.md")
    diff_lines = diff_text.splitlines()

    assert any(line.startswith("--- orig.md") for line in diff_lines)
    assert any(line.startswith("+++ cand.md") for line in diff_lines)
    assert any(line.startswith("@@") for line in diff_lines)
    assert "-a" in diff_lines
    assert "+b" in diff_lines


def test_unified_markdown_diff_separates_content_without_trailing_newlines():
    diff_text = core.unified_markdown_diff("a", "b", "orig.md", "cand.md")
    diff_lines = diff_text.splitlines()

    assert any(line.startswith("--- orig.md") for line in diff_lines)
    assert any(line.startswith("+++ cand.md") for line in diff_lines)
    assert any(line.startswith("@@") for line in diff_lines)
    assert "-a" in diff_lines
    assert "+b" in diff_lines
    assert all("-a+b" not in line for line in diff_lines)


def test_unified_markdown_diff_shows_newline_only_changes():
    diff_text = core.unified_markdown_diff("a", "a\n", "orig.md", "cand.md")
    diff_lines = diff_text.splitlines()

    assert diff_text
    assert any(line.startswith("--- orig.md") for line in diff_lines)
    assert any(line.startswith("+++ cand.md") for line in diff_lines)
    assert any(line.startswith("@@") for line in diff_lines)
    assert "-a" in diff_lines
    assert "+a" in diff_lines
    assert any("No newline at end of file" in line for line in diff_lines)


def test_unified_markdown_diff_marks_removed_content_starting_with_dashes_without_newline():
    diff_text = core.unified_markdown_diff("--- heading", "changed", "orig.md", "cand.md")
    diff_lines = diff_text.splitlines()
    removed_index = diff_lines.index("---- heading")

    assert "---- heading" in diff_lines
    assert diff_lines[removed_index + 1] == r"\ No newline at end of file"


def test_unified_markdown_diff_marks_added_content_starting_with_pluses_without_newline():
    diff_text = core.unified_markdown_diff("changed", "+++ heading", "orig.md", "cand.md")
    diff_lines = diff_text.splitlines()
    added_index = diff_lines.index("++++ heading")

    assert "++++ heading" in diff_lines
    assert diff_lines[added_index + 1] == r"\ No newline at end of file"


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


def test_write_review_report_uses_safe_diff_fence_for_backticks(tmp_path):
    original = tmp_path / "book.md"
    candidate = tmp_path / ".mathos-formatting" / "book.candidate.md"
    report = tmp_path / ".mathos-formatting" / "book.report.md"
    original.write_text("before\n```\nkeep\n```\nold line\n", encoding="utf-8")
    candidate.parent.mkdir()
    candidate.write_text("before\n```\nkeep\n```\nnew line\n", encoding="utf-8")

    path = core.write_review_report(
        original_path=original,
        candidate_path=candidate,
        report_path=report,
        heading_summary=[],
        plugin_summary=[],
        warnings=[],
    )

    text = path.read_text(encoding="utf-8")
    assert " ```" in text
    assert "````diff" in text
    assert "-old line" in text
    assert "+new line" in text
    assert "\n````\n\n## Next Actions" in text
    assert text.index("````diff") < text.index("-old line") < text.index("## Next Actions")
    assert "- approve" in text


def test_write_review_report_rejects_original_path_collision_without_writing(tmp_path):
    original = tmp_path / "book.md"
    candidate = tmp_path / ".mathos-formatting" / "book.candidate.md"
    original_text = "original body\n"
    candidate_text = "candidate body\n"
    original.write_text(original_text, encoding="utf-8")
    candidate.parent.mkdir()
    candidate.write_text(candidate_text, encoding="utf-8")

    with pytest.raises(core.FormattingError, match="report path must not overwrite"):
        core.write_review_report(
            original_path=original,
            candidate_path=candidate,
            report_path=original,
            heading_summary=[],
            plugin_summary=[],
            warnings=[],
        )

    assert original.read_text(encoding="utf-8") == original_text
    assert candidate.read_text(encoding="utf-8") == candidate_text


def test_write_review_report_rejects_candidate_path_collision_without_writing(tmp_path):
    original = tmp_path / "book.md"
    candidate = tmp_path / ".mathos-formatting" / "book.candidate.md"
    original_text = "original body\n"
    candidate_text = "candidate body\n"
    original.write_text(original_text, encoding="utf-8")
    candidate.parent.mkdir()
    candidate.write_text(candidate_text, encoding="utf-8")

    with pytest.raises(core.FormattingError, match="report path must not overwrite"):
        core.write_review_report(
            original_path=original,
            candidate_path=candidate,
            report_path=candidate,
            heading_summary=[],
            plugin_summary=[],
            warnings=[],
        )

    assert original.read_text(encoding="utf-8") == original_text
    assert candidate.read_text(encoding="utf-8") == candidate_text


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


UNSAFE_BUILTINS_PLUGIN = '''
PLUGIN_ID = "unsafe_builtins_plugin"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"warnings": [], "summary": []}

def clean(markdown: str) -> str:
    return __builtins__.open("secrets.txt").read()
'''


UNSAFE_BUILTINS_SUBSCRIPT_PLUGIN = '''
PLUGIN_ID = "unsafe_builtins_subscript_plugin"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"warnings": [], "summary": []}

def clean(markdown: str) -> str:
    return __builtins__["open"]("secrets.txt").read()
'''


UNSAFE_BUILTINS_IMPORT_SUBSCRIPT_PLUGIN = '''
PLUGIN_ID = "unsafe_builtins_import_subscript_plugin"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"warnings": [], "summary": []}

def clean(markdown: str) -> str:
    return __builtins__["__import__"]("os").getcwd()
'''


MISSING_ATTRIBUTE_PLUGIN = '''
PLUGIN_ID = "missing_attribute_plugin"
PLUGIN_VERSION = "1.0.0"

def clean(markdown: str) -> str:
    return markdown
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


def test_plugin_runner_rejects_builtins_file_access(tmp_path):
    plugin_path = tmp_path / "content_cleaner.py"
    plugin_path.write_text(UNSAFE_BUILTINS_PLUGIN, encoding="utf-8")

    with pytest.raises(core.FormattingError, match="unsafe attribute access"):
        core.load_safe_plugin(plugin_path)


@pytest.mark.parametrize(
    "source",
    [
        UNSAFE_BUILTINS_SUBSCRIPT_PLUGIN,
        UNSAFE_BUILTINS_IMPORT_SUBSCRIPT_PLUGIN,
    ],
)
def test_plugin_runner_rejects_builtins_subscript_access(tmp_path, source):
    plugin_path = tmp_path / "content_cleaner.py"
    plugin_path.write_text(source, encoding="utf-8")

    with pytest.raises(core.FormattingError, match="unsafe subscript access"):
        core.load_safe_plugin(plugin_path)


def test_plugin_runner_removes_invalid_module_from_registry(tmp_path):
    plugin_path = tmp_path / "content_cleaner.py"
    plugin_path.write_text(MISSING_ATTRIBUTE_PLUGIN, encoding="utf-8")

    expected_module_name = f"mathos_candidate_{abs(hash(plugin_path.resolve()))}"

    with pytest.raises(core.FormattingError, match="plugin missing required attribute: analyze"):
        core.load_safe_plugin(plugin_path)

    assert expected_module_name not in sys.modules


def test_load_provider_settings_reads_deepseek_without_exposing_secret(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DEEPSEEK_API_KEY=secret-value\n"
        "DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        "DEEPSEEK_MODEL=deepseek-chat\n",
        encoding="utf-8",
    )

    settings = provider.load_provider_settings(env_path)

    assert settings.api_key == "secret-value"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-chat"
    assert "secret-value" not in repr(settings)


def test_parse_heading_rules_artifact_accepts_json_only():
    artifact = provider.parse_heading_rules_artifact(
        '{"rules": [{"id": "x", "pattern": "^x$", "replacement": "# x", "flags": []}]}'
    )

    assert artifact["rules"][0]["id"] == "x"


def test_parse_heading_rules_artifact_strips_markdown_fence():
    text = (
        "```json\n"
        '{"rules": [{"id": "x", "pattern": "^x$", "replacement": "# x", "flags": []}]}\n'
        "```"
    )
    artifact = provider.parse_heading_rules_artifact(text)
    assert artifact["rules"][0]["id"] == "x"


def test_parse_json_artifact_from_text_strips_markdown_fence():
    text = (
        "```json\n"
        '{"rules": []}\n'
        "```"
    )
    parsed = core.parse_json_artifact_from_text(text)
    assert parsed == '{"rules": []}'






def test_parse_python_artifact_strips_markdown_fence():
    text = (
        "```python\n"
        "PLUGIN_ID = 'x'\n"
        "PLUGIN_VERSION = '1.0.0'\n\n"
        "def analyze(markdown: str) -> dict:\n"
        "    return {'summary': [], 'warnings': []}\n\n"
        "def clean(markdown: str) -> str:\n"
        "    return markdown\n"
        "```"
    )

    parsed = provider.parse_python_artifact(text)

    assert parsed.startswith("PLUGIN_ID")
    assert "```" not in parsed


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
    heading_rules = {
        "rules": [
            {
                "id": "chapter",
                "pattern": r"^(第一章 .+?)(?: …… \d+)?$",
                "replacement": r"# \1",
                "flags": ["MULTILINE"],
            }
        ]
    }
    core.save_approved_program(approved_root, "safe_plugin", heading_rules, plugin, original, candidate, original, ["summary"])

    result = core.apply_approved_program(approved_root / "safe_plugin", target)

    assert result.candidate_path.read_text(encoding="utf-8") == "# 第一章 集合\n\na b\n"
    assert target.read_text(encoding="utf-8") == "第一章 集合 …… 1\n\na  b\n"


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
    heading_rules = {
        "rules": [
            {
                "id": "chapter",
                "pattern": r"^(第一章 .+?)(?: …… \d+)?$",
                "replacement": r"# \1",
                "flags": ["MULTILINE"],
            }
        ]
    }
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


def test_cli_candidate_from_artifacts_creates_backup_report_and_candidate_plugin(tmp_path):
    markdown = tmp_path / "book.md"
    heading_rules_path = tmp_path / "heading_rules.json"
    plugin_path = tmp_path / "generated_plugin.py"
    markdown.write_text("第一章 集合 …… 1\n\na  b\n", encoding="utf-8")
    heading_rules_path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "chapter",
                        "pattern": r"^(第一章 .+?)(?: …… \d+)?$",
                        "replacement": r"# \1",
                        "flags": ["MULTILINE"],
                    }
                ]
            }
        ),
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


def test_learning_work_dir_defaults_to_nested_source_stem(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 目录\n\n# 第一章 …… 1\n", encoding="utf-8")

    path = core.learning_work_dir_for(markdown)

    assert path == tmp_path / ".mathos-formatting" / "book"


def test_write_learning_state_records_error_without_secrets(tmp_path):
    work_dir = tmp_path / ".mathos-formatting" / "book"
    state = core.LearningRunState(
        source_path=tmp_path / "book.md",
        candidate_path=work_dir / "candidate.md",
        provider_base_url="https://api.deepseek.com",
        provider_model="deepseek-chat",
        stage="heading-provider",
        status="failed",
        artifacts={"toc_sample": work_dir / "toc_sample.md"},
        warnings=["sample warning"],
        errors=["TOC not found"],
        approved=False,
    )

    state_path = core.write_learning_state(work_dir, state)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["stage"] == "heading-provider"
    assert payload["errors"] == ["TOC not found"]
    assert payload["artifacts"]["toc_sample"].endswith("toc_sample.md")
    assert "api_key" not in state_path.read_text(encoding="utf-8").lower()


def test_extract_toc_sample_requires_detected_toc():
    markdown = "# 第一章\n\n正文\n"
    structure = core.extract_structure(markdown, "no-toc.md")

    with pytest.raises(core.FormattingError, match="TOC not found"):
        core.extract_toc_sample(markdown, structure)


def test_extract_toc_sample_contains_toc_and_heading_context():
    markdown = """# 数学

# 目录

# 第一章 分数乘法 …… 1
1.1 分数乘整数 …… 2

# 第一章 分数乘法

正文
"""
    structure = core.extract_structure(markdown, "book.md")

    sample = core.extract_toc_sample(markdown, structure)

    assert "# 目录" in sample
    assert "1.1 分数乘整数" in sample
    assert "# 第一章 分数乘法" in sample
    assert sample.index("# 目录") < sample.index("# 第一章 分数乘法")


def test_extract_h1_sample_uses_requested_h1_section():
    markdown = """# 第一章

正文一

# 第二章

正文二
"""
    structure = core.extract_structure(markdown, "candidate.md")

    sample = core.extract_h1_sample(markdown, structure, h1_index=1)

    assert sample.startswith("# 第二章")
    assert "正文二" in sample
    assert "正文一" not in sample


def test_extract_h1_sample_rejects_missing_h1():
    markdown = "正文\n"
    structure = core.extract_structure(markdown, "candidate.md")

    with pytest.raises(core.FormattingError, match="H1 section not found"):
        core.extract_h1_sample(markdown, structure, h1_index=0)


def test_run_content_plugin_rejects_heading_changes(tmp_path):
    plugin_path = tmp_path / "bad_cleaner.py"
    plugin_path.write_text(
        '''
PLUGIN_ID = "bad_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": [], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("# 第一章", "# Changed")
''',
        encoding="utf-8",
    )
    plugin = core.load_safe_plugin(plugin_path)
    markdown = "# 第一章\n\n正文\n"

    with pytest.raises(core.FormattingError, match="content cleaner modified heading lines"):
        core.run_content_plugin_protecting_headings(plugin, markdown)


def test_run_content_plugin_allows_text_changes(tmp_path):
    plugin_path = tmp_path / "text_cleaner.py"
    plugin_path.write_text(
        '''
PLUGIN_ID = "text_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": ["normalized spaces"], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("a  b", "a b")
''',
        encoding="utf-8",
    )
    plugin = core.load_safe_plugin(plugin_path)

    result = core.run_content_plugin_protecting_headings(plugin, "# 第一章\n\na  b\n")

    assert result.cleaned_markdown == "# 第一章\n\na b\n"
    assert result.summary == ["normalized spaces"]


class FakeFormattingProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self):
        self.calls = []

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120) -> str:
        self.calls.append((system_prompt, user_payload, timeout_seconds))
        if "Heading Rules Prompt" in system_prompt:
            return json.dumps(
                {
                    "rules": [
                        {
                            "id": "delete_toc",
                            "pattern": r"(?s)^# 目录.*?(?=\n# 第一章)",
                            "replacement": "",
                            "flags": ["MULTILINE"],
                        },
                        {
                            "id": "toc_chapter",
                            "pattern": r"^#? *(第一章 .+?)(?: *[…]+ *\d+)?$",
                            "replacement": r"# \1",
                            "flags": ["MULTILINE"],
                        },
                        {
                            "id": "section_heading",
                            "pattern": r"^1\\.1 (.+)$",
                            "replacement": r"## 1.1 \1",
                            "flags": ["MULTILINE"],
                        },
                        {
                            "id": "demote_non_toc_headings",
                            "pattern": r"^# (?!目录|第一章)(.+)$",
                            "replacement": r"#### \1",
                            "flags": ["MULTILINE"],
                        },
                    ]
                },
                ensure_ascii=False,
            )
        return """```python
PLUGIN_ID = "image_text_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": ["normalized image alt text"], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("![](images/a.png)", "![figure](images/a.png)")
```"""


def test_run_learning_from_provider_writes_artifacts_and_keeps_original(tmp_path):
    markdown = tmp_path / "book.md"
    original_text = SAMPLE_MARKDOWN
    markdown.write_text(original_text, encoding="utf-8")
    provider_client = FakeFormattingProvider()

    result = core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=provider_client,
        heading_prompt="# Heading Rules Prompt",
        content_prompt="# Content Cleaner Prompt",
        work_dir=tmp_path / ".mathos-formatting" / "book",
    )

    assert result.status == "candidate-written"
    assert markdown.read_text(encoding="utf-8") == original_text
    assert result.candidate_path.exists()
    assert result.report_path.exists()
    assert (result.work_dir / "toc_sample.md").exists()
    assert (result.work_dir / "heading_rules_response.json").exists()
    assert (result.work_dir / "heading_rules.json").exists()
    assert (result.work_dir / "h1_sample.md").exists()
    assert (result.work_dir / "content_cleaner_response.py").exists()
    assert (result.work_dir / "content_cleaner.py").exists()
    assert (result.work_dir / "run-state.json").exists()
    candidate_text = result.candidate_path.read_text(encoding="utf-8")
    assert "![figure](images/a.png)" in candidate_text
    
    # Verify TOC is deleted
    assert "# 目录" not in candidate_text
    assert "集合与常用逻辑用语 …… 1" not in candidate_text
    
    # Verify non-TOC heading is demoted
    assert "#### 数学" in candidate_text
    
    # Verify first real chapter heading is intact
    assert "# 第一章 集合与常用逻辑用语" in candidate_text
    
    assert len(provider_client.calls) == 2


class CountingProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self):
        self.calls = 0

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120) -> str:
        self.calls += 1
        return "{}"


def test_learning_without_toc_stops_before_provider_and_candidate(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 第一章\n\n正文\n", encoding="utf-8")
    provider_client = CountingProvider()
    work_dir = tmp_path / ".mathos-formatting" / "book"

    with pytest.raises(core.FormattingError, match="TOC not found"):
        core.run_learning_from_provider(
            markdown,
            provider_client,
            heading_prompt="# Heading Rules Prompt",
            content_prompt="# Content Cleaner Prompt",
            work_dir=work_dir,
        )

    assert provider_client.calls == 0
    assert not (work_dir / "candidate.md").exists()
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["stage"] == "toc-sample"
    assert state["errors"] == ["TOC not found"]


class HeadingMutatingProvider(FakeFormattingProvider):
    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120) -> str:
        if "Heading Rules Prompt" in system_prompt:
            return super().chat(system_prompt, user_payload, timeout_seconds)
        return """```python
PLUGIN_ID = "bad_heading_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": [], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("# 第一章", "# Changed")
```"""


def test_learning_restores_stage1_candidate_when_content_changes_heading(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / ".mathos-formatting" / "book"

    with pytest.raises(core.FormattingError, match="content cleaner modified heading lines"):
        core.run_learning_from_provider(
            markdown,
            HeadingMutatingProvider(),
            heading_prompt="# Heading Rules Prompt",
            content_prompt="# Content Cleaner Prompt",
            work_dir=work_dir,
        )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    assert "# Changed" not in candidate_text
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["stage"] == "stage2-apply"


def test_provider_client_exposes_redacted_identity(monkeypatch):
    settings = provider.ProviderSettings(
        api_key="secret-value",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )
    client = provider.DeepSeekProviderClient(settings)

    assert client.base_url == "https://api.deepseek.com"
    assert client.model == "deepseek-chat"
    assert "secret-value" not in repr(client)


def test_cli_learn_from_provider_outputs_json_with_env(tmp_path, monkeypatch):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("DEEPSEEK_API_KEY=secret\nDEEPSEEK_MODEL=deepseek-chat\n", encoding="utf-8")

    fake_cli = importlib.util.spec_from_file_location("mathos_formatting_cli_test", CLI_PATH)
    cli = importlib.util.module_from_spec(fake_cli)
    assert fake_cli.loader is not None
    sys.modules["mathos_formatting_cli_test"] = cli
    fake_cli.loader.exec_module(cli)

    class CliFakeProvider(FakeFormattingProvider):
        pass

    monkeypatch.setattr(cli.provider, "DeepSeekProviderClient", lambda settings: CliFakeProvider())

    exit_code = cli.main([
        "learn-from-provider",
        str(markdown),
        "--env",
        str(env_path),
        "--work-dir",
        str(tmp_path / ".mathos-formatting" / "book"),
    ])

    assert exit_code == 0
    assert (tmp_path / ".mathos-formatting" / "book" / "candidate.md").exists()


def test_provider_learning_docs_name_toc_h1_and_heading_protection():
    heading_prompt = (SKILL_ROOT / "agents" / "heading_rules_prompt.md").read_text(encoding="utf-8")
    content_prompt = (SKILL_ROOT / "agents" / "content_cleaner_prompt.md").read_text(encoding="utf-8")
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme_text = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
    combined = "\n".join([heading_prompt, content_prompt, skill_text, readme_text]).lower()

    assert "learn-from-provider" in combined
    assert "toc" in combined or "table of contents" in combined
    assert "complete h1" in combined
    assert "image/text" in combined
    assert "must not modify heading" in combined




