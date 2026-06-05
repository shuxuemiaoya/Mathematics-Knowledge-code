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
