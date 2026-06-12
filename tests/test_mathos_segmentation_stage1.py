from pathlib import Path
import importlib.util
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "mathos-segmentation-stage1" / "scripts" / "mathos_segmentation_stage1.py"

spec = importlib.util.spec_from_file_location("mathos_segmentation_stage1", SCRIPT_PATH)
seg = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["mathos_segmentation_stage1"] = seg
spec.loader.exec_module(seg)


def test_module_exposes_stage_constants():
    assert seg.STAGE_NAME == "segmentation-stage1"
    assert seg.SKILL_NAME == "skills/mathos-segmentation-stage1"


SAMPLE_MARKDOWN = """# 第一章 集合与常用逻辑用语

章导语

## 1.1 集合的概念

节导语

### 1.1.1 集合的概念

集合正文 A

### 1.1.2 集合的基本关系

集合正文 B

## 1.2 函数

### 1.2.1 函数的概念

函数正文 C
"""


def test_extract_numbered_headings_ignores_unnumbered_heading():
    headings = seg.extract_numbered_headings(SAMPLE_MARKDOWN)

    assert [item.number for item in headings] == ["1.1", "1.1.1", "1.1.2", "1.2", "1.2.1"]
    assert headings[0].depth == 2
    assert headings[1].number_depth == 3
    assert headings[1].title == "集合的概念"
    assert headings[1].full_title == "1.1.1 集合的概念"


def test_select_target_depth_defaults_to_deepest_numbering():
    headings = seg.extract_numbered_headings(SAMPLE_MARKDOWN)

    assert seg.select_target_depth(headings, None) == 3
    assert seg.select_target_depth(headings, 2) == 2


def test_build_plan_uses_sandbox_folder_and_short_links(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "高中" / "课本" / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    plan = seg.build_segmentation_plan(source, vault_root=vault_root, target_depth=None)

    assert plan.sandbox_dir == source.parent / "book"
    assert plan.master_path == source.parent / "book" / "000_book目录.md"
    assert [item.link_title for item in plan.segments] == [
        "1.1.1 集合的概念",
        "1.1.2 集合的基本关系",
        "1.2.1 函数的概念",
    ]
    assert plan.next_command.endswith('--vault-root "' + str(vault_root.resolve()) + '" --yes')


def test_build_plan_rejects_source_outside_vault(tmp_path):
    source = tmp_path / "outside.md"
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    try:
        seg.build_segmentation_plan(source, vault_root=vault_root, target_depth=None)
    except seg.SegmentationError as exc:
        assert "not under vault root" in str(exc)
    else:
        raise AssertionError("expected SegmentationError")
