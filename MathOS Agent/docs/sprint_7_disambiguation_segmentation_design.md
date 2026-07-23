# Sprint 7: Heading Disambiguation & Segmentation Design

This document details the design for renaming the `mathos-segmentation-stage1` skill to `mathos-segmentation` and integrating a pre-splitting **heading disambiguation preprocessor** directly into `mathos_segmentation.py`.

## Goal

To automatically detect repeated, semantically ambiguous subheadings (like `## 小结` or `## 复习参考题 1`) across different chapters, prepend them with their parent chapter's core semantic name (e.g. `## 集合与常用逻辑用语 小结`), and execute the splitting so that Obsidian note filenames are unique and meaningful. Renaming the skill directories and testing files is also performed.

## Design Details

### 1. Renaming Files and References
- Folder: `skills/mathos-segmentation-stage1/` -> `skills/mathos-segmentation/`
- Script: `skills/mathos-segmentation/scripts/mathos_segmentation_stage1.py` -> `skills/mathos-segmentation/scripts/mathos_segmentation.py`
- Test: `tests/test_mathos_segmentation_stage1.py` -> `tests/test_mathos_segmentation.py`
- All constants in python script and test files (`STAGE_NAME`, `SKILL_NAME`, `SCRIPT_COMMAND`) will be updated to reflect the new names.

### 2. Disambiguation Algorithm

Before generating any plan or writing segments, the script reads the raw source markdown file and checks for ambiguous headings.

#### 2.1 Ambiguity Check
A heading `H` of level 2 (`##`) or level 3 (`###`) is considered ambiguous if:
1. It does NOT start with standard dotted numbering prefix (e.g. `6.1`, `6.1.1`).
2. AND it contains any of the predefined keywords:
   - `BLACKLIST = ["小结", "复习参考题", "阅读与思考", "探究与发现", "信息技术应用", "文献阅读与数学写作", "数学探究"]`

#### 2.2 Parent H1 Core Title Extraction
When an ambiguous heading is found, we find its parent H1 heading.
- If H1 title matches `第[一二三四五六七八九十百]+章\s+(.+)`, the core title is group 1.
- Otherwise, the core title is the H1 title itself.

#### 2.3 Replacement
- The heading title is updated to: `f"{h1_core_title} {original_title}"`.
- An idempotency check is performed: if the heading title already starts with `h1_core_title`, we skip it to prevent double-prefixing.

#### 2.4 Original Backup
- Before writing the modified content back to the source file, a `.md.bak` backup file of the *raw original* source is written (only if the `.bak` file doesn't already exist, to ensure we don't overwrite it with a preprocessed version).

## Verification Plan

### Automated Tests
- Rename the test suite and verify all tests pass via `pytest`.
- Add test cases in `tests/test_mathos_segmentation.py` specifically for testing the disambiguation logic.

### Manual Verification
- Execute `segment` on a textbook and confirm that files like `集合与常用逻辑用语 小结.md` are generated in the sandbox folder.
