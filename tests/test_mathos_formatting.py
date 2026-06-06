from pathlib import Path
import py_compile
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "mathos-formatting"
REGISTRY_PATH = REPO_ROOT / "docs" / "agent" / "skill-registry.md"


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
    assert "scaffolded" in skill_text.lower()
    assert "scaffold for future mathos adaptive markdown formatting" in skill_text.lower()
    assert "do not use operationally until implementation tasks are complete" in skill_text.lower()
    assert "do not run it as an operational skill until implementation is complete" in skill_text.lower()
    assert "active after implementation is complete" in readme_text.lower()
    assert "candidate backup" in combined_text
    assert "user approval" in combined_text


def test_formatting_cli_fails_closed_while_scaffolded():
    result = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "mathos_formatting.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "scaffold" in result.stderr.lower()
    assert "not operational" in result.stderr.lower()


def test_formatting_skill_registry_marks_scaffold_non_operational():
    section = _registry_section("skills/mathos-formatting").lower()

    assert "scaffolded" in section
    assert "non-operational" in section
    assert "not operational until implementation tasks complete" in section
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
