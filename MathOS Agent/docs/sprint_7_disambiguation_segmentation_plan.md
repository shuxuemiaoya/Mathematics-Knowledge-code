# Sprint 7: Heading Disambiguation & Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `mathos-segmentation-stage1` to `mathos-segmentation` and add an automatic heading disambiguation preprocessing step that runs before planning/segmentation to rename ambiguous headings.

**Architecture:** We will rename the skill folder, script, and test suite. In the python script, we will write a preprocessor that scans the markdown file for H2/H3 headings, checks them against a blacklist, extracts the H1 parent's core title, modifies the headings in-place, and creates a `.bak` backup of the raw file before writing.

**Tech Stack:** Python, pytest.

---

### Task 1: Rename Folder, Files, and Constants

**Files:**
- Rename: `skills/mathos-segmentation-stage1` -> `skills/mathos-segmentation`
- Rename: `skills/mathos-segmentation/scripts/mathos_segmentation_stage1.py` -> `skills/mathos-segmentation/scripts/mathos_segmentation.py`
- Rename: `tests/test_mathos_segmentation_stage1.py` -> `tests/test_mathos_segmentation.py`

- [ ] **Step 1: Perform the physical file renames**
  Run powershell commands to rename directories and files.

- [ ] **Step 2: Update internal constants and paths**
  Update `STAGE_NAME`, `SKILL_NAME`, `SCRIPT_COMMAND`, imports, and file links in `mathos_segmentation.py`, `SKILL.md`, and `test_mathos_segmentation.py`.

### Task 2: Implement Heading Disambiguation Preprocessing Logic

**Files:**
- Modify: `skills/mathos-segmentation/scripts/mathos_segmentation.py`

- [ ] **Step 1: Write get_h1_core_title and is_ambiguous_heading helpers**
  Add the helper functions:
  ```python
  CHAPTER_PREFIX_RE = re.compile(r"^第[一二三四五六七八九十百]+章\s+(.+)$")
  BLACKLIST = ["小结", "复习参考题", "阅读与思考", "探究与发现", "信息技术应用", "文献阅读与数学写作", "数学探究"]
  DOTTED_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\s+")

  def get_h1_core_title(h1_title: str) -> str:
      match = CHAPTER_PREFIX_RE.match(h1_title)
      if match:
          return match.group(1).strip()
      return h1_title.strip()

  def is_ambiguous_heading(heading_text: str) -> bool:
      if DOTTED_NUMBER_RE.match(heading_text):
          return False
      for word in BLACKLIST:
          if word in heading_text:
              return True
      return False
  ```

- [ ] **Step 2: Write disambiguation preprocessor logic**
  Implement `disambiguate_source_file(source_path: Path)` which:
  1. Reads content.
  2. Processes line-by-line: tracks current H1 core title, checks H2/H3 for ambiguity, prepends H1 core title if not already present.
  3. If modifications are made: writes `.bak` backup first (if it doesn't exist), then overwrites source file in-place with modified markdown.

- [ ] **Step 3: Integrate preprocessing step into CLI entry points**
  Call `disambiguate_source_file` at the beginning of `command_plan` and `command_segment` in the script.

### Task 3: Update Test Suite and Verify Correctness

**Files:**
- Modify: `tests/test_mathos_segmentation.py`

- [ ] **Step 4: Add unit tests for disambiguation**
  Write tests in `test_mathos_segmentation.py` to verify that ambiguous headings are correctly modified and `.bak` files are created.

- [ ] **Step 5: Run pytest and confirm all 117+ tests pass**
  Run: `pytest` and verify success.

- [ ] **Step 6: Run segment on a textbook to verify in vault**
  Execute `segment` on a textbook and inspect the sandbox directory for renamed files.
