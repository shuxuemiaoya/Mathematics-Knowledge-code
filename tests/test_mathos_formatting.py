from pathlib import Path
import py_compile
import subprocess
import sys


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
