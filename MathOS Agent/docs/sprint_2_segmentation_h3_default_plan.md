# default-to-h3-segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the segmentation stage 1 operator to default target depth to 3 and filter headings above the target depth, so that deeper levels are not segmented into separate files.

**Architecture:** Update `select_target_depth` in the segmentation script to return `3` as default target depth. In `build_segmentation_plan`, filter the heading list using `h.markdown_depth <= selected_depth` before constructing the directory tree. Update and write unit tests to verify these depth and filtering rules.

**Tech Stack:** Python, pytest

---

### Task 1: Update Target Depth Selection and Heading Filtering in Script

**Files:**
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py:223-234`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py:346`

- [ ] **Step 1: Update target depth selection logic**

Replace `select_target_depth` implementation in `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py` with:
```python
def select_target_depth(headings: list[Heading], requested_depth: int | None) -> int:
    if not headings:
        raise SegmentationError("No numbered headings detected")

    if requested_depth is None:
        if any(heading.number_depth == 3 for heading in headings):
            return 3
        return max(heading.number_depth for heading in headings)

    if not any(heading.number_depth == requested_depth for heading in headings):
        raise SegmentationError(f"Target depth {requested_depth} produced zero segments")

    return requested_depth
```

- [ ] **Step 2: Filter headings list before calling tree builder**

Modify `build_segmentation_plan` in `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py` to filter `headings` using `selected_depth`:
```python
    filtered_headings = [h for h in headings if h.markdown_depth <= selected_depth]
    top_level_nodes, nodes, special_merges, warnings = build_directory_tree(filtered_headings, markdown, sandbox_dir)
```

---

### Task 2: Update and Add Tests

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`

- [ ] **Step 1: Add unit tests for target depth default behavior**

Write a new test function `test_select_target_depth_defaults_to_3` and `test_select_target_depth_falls_back_when_no_depth_3` at the end of `tests/test_mathos_segmentation_stage1.py`:
```python
def test_select_target_depth_defaults_to_3():
    # A markdown with H4 headings
    markdown_with_h4 = SAMPLE_MARKDOWN + "\n#### 1.2.1.1 更加深层的内容\n"
    headings = seg.extract_numbered_headings(markdown_with_h4)
    # Target depth should default to 3 even though deepest is 4
    assert seg.select_target_depth(headings, None) == 3

def test_select_target_depth_falls_back_when_no_depth_3():
    # A markdown with only H2 headings
    markdown_with_h2 = "# 第一章\n## 1.1 集合\n"
    headings = seg.extract_numbered_headings(markdown_with_h2)
    # Target depth should fall back to max (2) since 3 doesn't exist
    assert seg.select_target_depth(headings, None) == 2
```

- [ ] **Step 2: Add unit test to verify filtering of deeper headings**

Write a test function `test_build_plan_filters_headings_above_target_depth` at the end of `tests/test_mathos_segmentation_stage1.py`:
```python
def test_build_plan_filters_headings_above_target_depth(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    
    # H4 heading under H3
    markdown_content = """# 第一章
## 1.1 集合
### 1.1.1 集合的概念
正文开始
#### 1.1.1.1 向量的物理背景
深层正文
"""
    source.write_text(markdown_content, encoding="utf-8")
    
    # Run plan with default target depth (which should be 3)
    plan = seg.build_segmentation_plan(source, vault_root=vault_root, target_depth=None)
    
    assert plan.target_depth == 3
    # Check that H4 is NOT created as a node (only top, ch, sec, subsec exist)
    node_names = [n.note_stem for n in plan.nodes]
    assert "1.1.1.1 向量的物理背景" not in node_names
    
    # Check that H4 text is preserved inside the parent H3 leaf note's content
    seg.write_segmentation_package(plan)
    leaf_file = plan.sandbox_dir / "1.1.1 集合的概念.md"
    assert leaf_file.exists()
    leaf_text = leaf_file.read_text(encoding="utf-8")
    assert "#### 1.1.1.1 向量的物理背景" in leaf_text
    assert "深层正文" in leaf_text
```

- [ ] **Step 3: Run all unit tests to verify**

Run `pytest` to make sure all 59 tests pass.
Run: `pytest -v`
Expected: 59 passed

---

### Task 3: Verify the Changes on the Real Textbook (Dry-Run)

- [ ] **Step 1: Execute dry-run plan on a real textbook**

Run:
```powershell
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py plan "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\高中\课本\【人教版】高中必修 第二册数学电子课本.md" --vault-root "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map" --yes
```
Expected:
Outputs JSON layout with `target_depth: 3` and correct counts of leaf_nodes and directory_nodes.
