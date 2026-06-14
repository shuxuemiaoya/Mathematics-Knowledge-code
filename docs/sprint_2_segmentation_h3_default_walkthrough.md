# default-to-h3-segmentation Walkthrough

I have updated the `mathos-segmentation-stage1` operator to default target depth to 3 and filter headings above the target depth, ensuring that deeper headings (like H4) are not segmented into separate files but are preserved inside the parent H3 leaf note.

## Summary of Changes

### 1. Script Updates
In `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`:
- Updated `select_target_depth` to:
  - Default target depth to `3` (if depth-3 numbered headings exist in the document).
  - Fall back to the maximum detected numbering depth if no depth-3 headings are found.
  - Raise `SegmentationError` if a target depth is explicitly requested but not present in the document.
- Updated `build_segmentation_plan` to filter headings by `h.markdown_depth <= selected_depth` before constructing the tree, ensuring H4+ headings are excluded from directory/leaf node creation and their content remains within the parent H3 leaf note.

### 2. Test Coverage
In `tests/test_mathos_segmentation_stage1.py`:
- Added `test_select_target_depth_defaults_to_3_when_available_even_if_deeper_exist` to verify defaulting to 3.
- Added `test_select_target_depth_falls_back_when_no_depth_3` to verify fallback to maximum depth when depth 3 is not available.
- Added `test_build_plan_filters_headings_deeper_than_selected_depth` to verify H4 headings are not created as nodes, their character offsets span correctly, and when written, the H3 leaf file physically preserves the H4 heading and text block.

### 3. Verification Results
- **Automated Tests**: Ran all 59 unit tests and they passed successfully:
  ```
  ============================= 59 passed in 0.88s ==============================
  ```
- **Real Textbook Dry-Run**: Ran a dry-run plan on the textbook *【人教版】高中必修 第二册数学电子课本.md*. The default `target_depth` successfully resolved to `3`, and the resulting structure contained:
  - `nodes`: 227 (down from 312)
  - `directory_nodes`: 60 (down from 104)
  - `leaf_nodes`: 167 (down from 208)
  - `special_merges`: 9 (unchanged)
  - `disambiguations`: 80 (down from 133)
  All H4 headings were correctly preserved within the text of their parent H3 leaf notes.
