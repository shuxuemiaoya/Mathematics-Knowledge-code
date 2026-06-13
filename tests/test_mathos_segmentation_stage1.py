from pathlib import Path
import importlib.util
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "mathos-segmentation-stage1" / "scripts" / "mathos_segmentation_stage1.py"

spec = importlib.util.spec_from_file_location("mathos_segmentation_stage1", SCRIPT_PATH)
seg = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["mathos_segmentation_stage1"] = seg
spec.loader.exec_module(seg)


def assert_segmentation_error_contains(expected_text, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except seg.SegmentationError as exc:
        assert expected_text in str(exc)
    else:
        raise AssertionError("expected SegmentationError")


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
    assert plan.next_command.startswith(
        r"python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment"
    )
    assert "'" + str(source.resolve()) + "'" in plan.next_command
    assert "--vault-root '" + str(vault_root.resolve()) + "'" in plan.next_command
    assert plan.next_command.endswith("--yes")


def test_build_plan_rejects_source_outside_vault(tmp_path):
    source = tmp_path / "outside.md"
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    assert_segmentation_error_contains(
        "not under vault root",
        seg.build_segmentation_plan,
        source,
        vault_root=vault_root,
        target_depth=None,
    )


def test_build_plan_rejects_missing_and_non_file_source(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    missing_source = vault_root / "missing.md"

    assert_segmentation_error_contains(
        "Source file missing",
        seg.build_segmentation_plan,
        missing_source,
        vault_root=vault_root,
    )

    directory_source = vault_root / "folder.md"
    directory_source.mkdir()

    assert_segmentation_error_contains(
        "Source file missing",
        seg.build_segmentation_plan,
        directory_source,
        vault_root=vault_root,
    )


def test_build_plan_rejects_non_markdown_suffix(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.txt"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    assert_segmentation_error_contains(
        "Source file is not Markdown",
        seg.build_segmentation_plan,
        source,
        vault_root=vault_root,
    )


def test_build_plan_rejects_missing_and_non_directory_vault_root(tmp_path):
    source = tmp_path / "book.md"
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    assert_segmentation_error_contains(
        "Invalid vault root",
        seg.build_segmentation_plan,
        source,
        vault_root=tmp_path / "missing-vault",
    )

    vault_root_file = tmp_path / "vault-file"
    vault_root_file.write_text("not a directory", encoding="utf-8")

    assert_segmentation_error_contains(
        "Invalid vault root",
        seg.build_segmentation_plan,
        source,
        vault_root=vault_root_file,
    )


def test_build_plan_rejects_empty_text_and_no_numbered_headings(tmp_path):
    vault_root = tmp_path / "vault"
    empty_source = vault_root / "empty.md"
    empty_source.parent.mkdir(parents=True)
    empty_source.write_text(" \n\t\n", encoding="utf-8")

    assert_segmentation_error_contains(
        "Source file is empty",
        seg.build_segmentation_plan,
        empty_source,
        vault_root=vault_root,
    )

    unnumbered_source = vault_root / "unnumbered.md"
    unnumbered_source.write_text("# 第一章\n\n## 集合的概念\n\n正文\n", encoding="utf-8")

    assert_segmentation_error_contains(
        "No numbered headings detected",
        seg.build_segmentation_plan,
        unnumbered_source,
        vault_root=vault_root,
    )


def test_build_plan_rejects_unmatched_target_depth(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    assert_segmentation_error_contains(
        "Target depth 4 produced zero segments",
        seg.build_segmentation_plan,
        source,
        vault_root=vault_root,
        target_depth=4,
    )


def test_build_plan_defaults_to_deepest_numbered_headings(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    assert plan.detected_number_depths == [2, 3]
    assert plan.target_depth == 3
    assert [segment.heading.number_depth for segment in plan.segments] == [3, 3, 3]


def test_build_plan_uses_exact_segment_char_ranges(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    expected_ranges = [
        (SAMPLE_MARKDOWN.index("### 1.1.1 集合的概念"), SAMPLE_MARKDOWN.index("### 1.1.2 集合的基本关系")),
        (SAMPLE_MARKDOWN.index("### 1.1.2 集合的基本关系"), SAMPLE_MARKDOWN.index("## 1.2 函数")),
        (SAMPLE_MARKDOWN.index("### 1.2.1 函数的概念"), len(SAMPLE_MARKDOWN)),
    ]
    assert [(item.char_start, item.char_end) for item in plan.segments] == expected_ranges
    assert [
        item.byte_count for item in plan.segments
    ] == [
        len(SAMPLE_MARKDOWN[start:end].encode("utf-8")) for start, end in expected_ranges
    ]


def test_build_plan_filenames_preserve_numbered_link_titles(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    assert [item.filename for item in plan.segments] == [
        "1.1.1 集合的概念.md",
        "1.1.2 集合的基本关系.md",
        "1.2.1 函数的概念.md",
    ]
    assert [item.output_path for item in plan.segments] == [
        plan.sandbox_dir / "1.1.1 集合的概念.md",
        plan.sandbox_dir / "1.1.2 集合的基本关系.md",
        plan.sandbox_dir / "1.2.1 函数的概念.md",
    ]


def test_build_plan_disambiguates_duplicate_filenames(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        """# 第一章

## 1.1 重复

正文 A

## 1.1 重复

正文 B
""",
        encoding="utf-8",
    )

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    assert [item.link_title for item in plan.segments] == ["1.1 重复", "1.1 重复"]
    assert [item.filename for item in plan.segments] == ["1.1 重复.md", "1.1 重复 - 02.md"]
    assert plan.disambiguations == [{"original": "1.1 重复.md", "final": "1.1 重复 - 02.md"}]


def test_build_plan_disambiguates_case_only_duplicate_filenames(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        """# 第一章

## 1.1 Foo

正文 A

## 1.1 foo

正文 B
""",
        encoding="utf-8",
    )

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    assert [item.filename for item in plan.segments] == ["1.1 Foo.md", "1.1 foo - 02.md"]
    assert plan.disambiguations == [{"original": "1.1 foo.md", "final": "1.1 foo - 02.md"}]


def test_build_plan_does_not_write_content_files(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    assert not plan.sandbox_dir.exists()
    assert not plan.master_path.exists()
    assert not any(item.output_path.exists() for item in plan.segments)


def test_render_master_directory_contains_only_directory_links(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    master = seg.render_master_directory(plan)

    assert master.startswith("# 目录\n\n")
    assert "- [[1.1 集合的概念]]" not in master
    assert "- [[1.1.1 集合的概念]]" in master
    assert "- [[1.1.2 集合的基本关系]]" in master
    assert "- [[1.2.1 函数的概念]]" in master
    assert "集合正文" not in master
    for line in master.splitlines():
        assert line == "" or line == "# 目录" or line.startswith("- [[")


def test_render_master_directory_links_disambiguated_note_stems(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        """# 第一章

## 1.1 重复

正文 A

## 1.1 重复

正文 B
""",
        encoding="utf-8",
    )
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    master = seg.render_master_directory(plan)

    assert master == "# 目录\n\n- [[1.1 重复]]\n- [[1.1 重复 - 02]]\n"


def test_build_segment_command_uses_resolved_paths_and_yes(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    command = seg.build_segment_command(source, vault_root, target_depth=2)

    assert command == (
        r"python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment "
        f"'{source.resolve()}' --vault-root '{vault_root.resolve()}' --target-depth 2 --yes"
    )


def test_quote_command_is_powershell_safe_and_preserves_dollar_literals():
    quoted = seg.quote_command(r"C:\vault\$book's.md")

    assert quoted == r"'C:\vault\$book''s.md'"
    assert "$book" in quoted


def test_write_segmentation_package_creates_master_and_raw_slices(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    original_hash = seg.file_sha256(source)
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    result = seg.write_segmentation_package(plan, overwrite=False)

    assert result["status"] == "written"
    assert plan.master_path.exists()
    first_segment = (plan.sandbox_dir / "1.1.1 集合的概念.md").read_text(encoding="utf-8")
    assert first_segment.startswith("### 1.1.1 集合的概念")
    assert "# 1.1.1 集合的概念" not in first_segment.splitlines()
    assert plan.master_path.read_text(encoding="utf-8") == seg.render_master_directory(plan)
    assert source.read_text(encoding="utf-8") == SAMPLE_MARKDOWN
    assert seg.file_sha256(source) == original_hash


def test_write_refuses_existing_sandbox_without_overwrite(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    plan.sandbox_dir.mkdir()

    assert_segmentation_error_contains(
        "already exists",
        seg.write_segmentation_package,
        plan,
        overwrite=False,
    )


def test_write_run_records_creates_state_manifest_and_summary(tmp_path):
    repo_root = tmp_path / "repo"
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    seg.write_segmentation_package(plan)

    record_dir = seg.write_run_records(plan, repo_root=repo_root, status="completed", stop_reason="")

    state = json.loads((record_dir / "run-state.json").read_text(encoding="utf-8"))
    manifest = json.loads((record_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = (record_dir / "run-summary.md").read_text(encoding="utf-8")
    assert state["stage"] == "segmentation-stage1"
    assert state["status"] == "completed"
    assert state["counts"]["segments"] == 3
    assert manifest["master_path"] == str(plan.master_path)
    assert manifest["verification"]["status"] == "passed"
    assert "Stage name: segmentation-stage1" in summary


def test_verify_package_checks_links_and_source_hash(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    seg.write_segmentation_package(plan)

    verification = seg.verify_package(plan)

    assert verification["status"] == "passed"
    assert verification["segment_count"] == 3


def test_verify_package_rejects_missing_disambiguated_link(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        """# 第一章

## 1.1 重复

正文 A

## 1.1 重复

正文 B
""",
        encoding="utf-8",
    )
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    seg.write_segmentation_package(plan)
    plan.master_path.write_text("# 目录\n\n- [[1.1 重复]]\n- [[1.1 重复]]\n", encoding="utf-8")

    assert_segmentation_error_contains(
        "Master link missing or duplicated",
        seg.verify_package,
        plan,
    )


def test_main_plan_prints_json_without_writing_package(tmp_path, capsys):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    exit_code = seg.main(["plan", str(source), "--vault-root", str(vault_root), "--yes"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["stage"] == "segmentation-stage1"
    assert payload["counts"]["segments"] == 3
    assert not (source.parent / "book").exists()


def test_main_segment_writes_package_and_records(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    monkeypatch.chdir(repo_root)

    exit_code = seg.main(["segment", str(source), "--vault-root", str(vault_root), "--yes"])

    assert exit_code == 0
    assert (source.parent / "book" / "000_book目录.md").exists()
    assert list((repo_root / "agent-memory" / "records").glob("*-segmentation-stage1-book"))


def test_main_segment_requires_yes(tmp_path, capsys):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    exit_code = seg.main(["segment", str(source), "--vault-root", str(vault_root)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert "without --yes" in payload["error"]
    assert not (source.parent / "book").exists()


LAYERED_MARKDOWN = """# 第六章 平面向量及其应用

章导语原文

## 6.1 平面向量的概念

节导语原文

### 6.1.1 向量的实际背景与概念

6.1.1 正文

### 6.1.2 向量的几何表示

6.1.2 正文

## 阅读与思考

### 向量及向量符号的由来

阅读正文

## 6.2 平面向量的运算

### 6.2.1 向量的加法运算

6.2.1 正文

# 第七章 复数

第七章导语

## 7.1 复数的概念

### 7.1.1 数系的扩充和复数的概念

7.1.1 正文
"""


def _write_layered_source(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(LAYERED_MARKDOWN, encoding="utf-8")
    return vault_root, source


def test_build_plan_creates_layered_nodes_and_counts(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    assert plan.master_path == source.parent / "book" / "000_book目录.md"
    assert [node.note_stem for node in plan.top_level_nodes] == ["第六章 平面向量及其应用", "第七章 复数"]
    assert plan.counts["nodes"] == 10
    assert plan.counts["directory_nodes"] == 5
    assert plan.counts["leaf_nodes"] == 5
    assert plan.counts["special_merges"] == 1


def test_layered_plan_keeps_full_numeric_prefixes_for_leaf_nodes(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    leaf_filenames = [node.filename for node in plan.leaf_nodes]
    assert "6.1.1 向量的实际背景与概念.md" in leaf_filenames
    assert "6.1.2 向量的几何表示.md" in leaf_filenames
    assert "6.2.1 向量的加法运算.md" in leaf_filenames

