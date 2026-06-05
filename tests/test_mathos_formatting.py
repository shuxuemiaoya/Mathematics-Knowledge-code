from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "mathos-formatting"


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
