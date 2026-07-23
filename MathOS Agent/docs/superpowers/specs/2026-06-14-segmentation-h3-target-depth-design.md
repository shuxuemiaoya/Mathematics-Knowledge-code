# Specification: Switch Segmentation Default Depth to H3 and Support Filtering

## 1. Goal
Modify the `mathos-segmentation-stage1` tool so that:
1. The default segmentation target depth is `3` (H3).
2. Headings deeper than the resolved target depth (e.g., H4) are not segmented into separate files. They remain inside their parent leaf notes as raw text.

## 2. Requirements & Behavior

### 2.1 Target Depth Selection
In `select_target_depth(headings, requested_depth)`:
- Accept `requested_depth: int | None`.
- If `requested_depth` is `None` (not specified via CLI), the default target depth is `3`.
- If the document's maximum heading depth is less than `3` (e.g., only H1 and H2 headings exist), the default target depth falls back to the maximum detected heading depth in the document.
- If `requested_depth` is explicitly provided but no headings exist at that depth, raise `SegmentationError`.

### 2.2 Heading Filtering
In `build_segmentation_plan`:
- Prior to calling `build_directory_tree`, filter the extracted heading list:
  ```python
  filtered_headings = [h for h in headings if h.markdown_depth <= target_depth]
  ```
- Pass `filtered_headings` to `build_directory_tree`. This ensures that:
  - Only headings up to the resolved `target_depth` are constructed as directory or leaf nodes.
  - Headings deeper than `target_depth` (e.g., H4 headings when target depth is 3) are not parsed as nodes, so they are not split. Instead, their text content naturally remains within the character range of the parent leaf node.

## 3. Verification Plan

### 3.1 Automated Tests
- Run existing unit tests to identify any assertions that assumed H4 default segmentation, and update them to expect H3 default.
- Add new unit tests in `tests/test_mathos_segmentation_stage1.py`:
  - Verify that when no target depth is passed, the target depth defaults to `3`.
  - Verify that when target depth is `3` on a document with H4 headings, the H4 headings are NOT split into separate files but exist inside the parent H3 leaf note's content.
  - Verify that if the document only has H2 headings and no depth is requested, it safely falls back to depth `2`.

### 3.2 Manual Verification
- Run a dry-run plan on the textbook:
  ```powershell
  python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py plan "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\高中\课本\【人教版】高中必修 第二册数学电子课本.md" --vault-root "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map" --yes
  ```
- Confirm that the default `target_depth` is `3`, and the resulting leaf nodes correspond to H3 headings.
