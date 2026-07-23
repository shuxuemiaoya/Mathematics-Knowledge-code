# Design Spec: Table of Contents (TOC) Selective Stripping

## Overview

In the current formatting pipeline of MathOS, the `toc-detection-provider` stage uses DeepSeek to identify the line number where the main content begins (`main_text_start_line`). It then strips/deletes everything in the document preceding that line, including the cover page, preface, and the Table of Contents itself.

This design updates the pipeline so that it **only deletes the Table of Contents (TOC) itself**, keeping any preface, title page, cover, or introductory material located before the TOC.

---

## Detailed Requirements

### 1. Identify TOC Boundaries via LLM
Instead of identifying only where the main text begins, the LLM will identify two specific line numbers:
- `toc_start_line`: The first line of the Table of Contents (e.g. `# 目录` or the first chapter item listed in the TOC).
- `main_text_start_line`: The first line of the actual main content (the end of the TOC).

### 2. Selective Slicing
- Keep lines from the start of the file up to `toc_start_line - 1`.
- Keep lines from `main_text_start_line` to the end of the file.
- Discard lines in between (from `toc_start_line` to `main_text_start_line - 1`).

### 3. Safe Fallback
If the LLM cannot find a TOC (e.g. `toc_start_line` is `null` or missing) or if the returned lines fail validation checks, keep the entire document intact (do not delete anything).

---

## Proposed Changes

### 1. LLM Prompt update
Modify `skills/mathos-formatting/agents/toc_detection_prompt.md`:
- Request JSON fields `toc_start_line` (integer or `null`) and `main_text_start_line` (integer).
- Provide updated instructions and a shape example:
  ```json
  {
    "toc_start_line": 15,
    "main_text_start_line": 238,
    "reason": "The TOC starts at line 15 with '# 目录' and the main text begins at line 238."
  }
  ```

### 2. Core implementation update
Modify `skills/mathos-formatting/scripts/mathos_formatting_core.py` in the `toc-detection-provider` stage:
- Parse `toc_start_line` and `main_text_start_line` from the LLM JSON response.
- Execute boundary check: `1 <= toc_start_line <= main_text_start_line <= len(lines)`.
- If valid, execute slice & join:
  ```python
  before_toc = stage1_lines[:toc_start_line - 1]
  after_toc = stage1_lines[main_text_start_line - 1:]
  stripped_text = "".join(before_toc + after_toc)
  ```
- If invalid or `toc_start_line` is `None`, fall back to keeping the original input: `stripped_text = stage1_text`.

### 3. Test updates
Modify the mock client `DestructiveProvider` in `tests/test_mathos_formatting_guarded.py`:
- Update mock response for `"TOC Detection Prompt"` to return:
  ```json
  {"toc_start_line": 3, "main_text_start_line": 8}
  ```

---

## Verification Plan

### Automated Tests
Run the existing formatting tests to ensure nothing breaks:
```powershell
python -m pytest tests/test_mathos_formatting_guarded.py
```

### Manual Verification
Review generated run state artifacts and candidate files to confirm only the TOC is stripped from testing documents.
