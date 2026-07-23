# Table of Contents Selective Stripping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the MathOS formatting pipeline to selectively delete only the Table of Contents (TOC) part, preserving cover pages, prefaces, and other introductory content before the TOC.

**Architecture:** Update the LLM prompt (`toc_detection_prompt.md`) to return both `toc_start_line` and `main_text_start_line`. Slices lines of the text before the TOC and from the main text start to retain introductory sections.

**Tech Stack:** Python 3.10+, Pytest.

---

### Task 1: Update LLM Prompt

**Files:**
- Modify: [toc_detection_prompt.md](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-formatting/agents/toc_detection_prompt.md)

- [ ] **Step 1: Modify `toc_detection_prompt.md`**
  Modify [toc_detection_prompt.md](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-formatting/agents/toc_detection_prompt.md) to ask the LLM to output both the `toc_start_line` and the `main_text_start_line` in its JSON payload, and handle the fallback scenario.
  
  Replace the entire file content with:
  ```markdown
  # TOC Detection Prompt
  
  You are identifying the exact line numbers where the Table of Contents (TOC) starts and ends (where the main text begins) in a Markdown document.
  
  The input document contains the first 20 pages of the Markdown file, with each line prepended with its 1-indexed line number in the format:
  `<line_number>: <line_content>`
  
  Your goal is to output a JSON object containing:
  - `toc_start_line`: The line number where the table of contents starts (e.g. '# 目录' or the first TOC item). If no TOC is found in the document, return null.
  - `main_text_start_line`: The line number where the main text begins (usually begins with the first actual chapter heading, e.g. '# 第一章').
  
  Return JSON only with this shape:
  
  ```json
  {
    "toc_start_line": 15,
    "main_text_start_line": 238,
    "reason": "The TOC starts at line 15 with '# 目录' and the main text begins at line 238 with '# 第七章 相交线与平行线'."
  }
  ```
  
  Important:
  - Return ONLY a valid JSON object. Do not include markdown code block markers (like ```json) or any explanation outside the JSON.
  - The line numbers MUST match the prefix line numbers exactly.
  - Ensure the line numbers are integers or null.
  ```

- [ ] **Step 2: Commit prompt changes**
  Run:
  ```bash
  git add skills/mathos-formatting/agents/toc_detection_prompt.md
  git commit -m "feat(formatting): update TOC detection prompt to return toc_start_line and main_text_start_line"
  ```

---

### Task 2: Mock Client Update & Unit Test Preparation

**Files:**
- Modify: [test_mathos_formatting_guarded.py](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/tests/test_mathos_formatting_guarded.py)

- [ ] **Step 1: Update `DestructiveProvider.chat` mock in `test_mathos_formatting_guarded.py`**
  Update the mock in `DestructiveProvider` to return the new JSON payload schema containing `toc_start_line`.
  
  Target content to replace (around lines 140-141):
  ```python
          if "TOC Detection Prompt" in system_prompt:
              return json.dumps({"main_text_start_line": 6}, ensure_ascii=False)
  ```
  
  Replacement content:
  ```python
          if "TOC Detection Prompt" in system_prompt:
              return json.dumps({"toc_start_line": 3, "main_text_start_line": 8}, ensure_ascii=False)
  ```

- [ ] **Step 2: Add a new unit test for fallback behavior and normal parsing**
  Add two test cases to `tests/test_mathos_formatting_guarded.py` at the end of the file.
  
  Code content to append:
  ```python
  class SuccessfulMockProvider:
      base_url = "https://fake.deepseek.local"
      model = "deepseek-test"
  
      def __init__(self, toc_start_line, main_text_start_line):
          self.toc_start = toc_start_line
          self.main_text_start = main_text_start_line
  
      def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120, response_format: dict | None = None) -> str:
          if "Heading Rules Prompt" in system_prompt:
              return json.dumps(
                  {
                      "rules": [
                          {
                              "id": "chapter",
                              "pattern": r"^# 第一章 数列(?: …… \d+)?$",
                              "replacement": "# 第一章 数列",
                              "flags": ["MULTILINE"],
                          }
                      ]
                  },
                  ensure_ascii=False,
              )
          if "TOC Detection Prompt" in system_prompt:
              return json.dumps({"toc_start_line": self.toc_start, "main_text_start_line": self.main_text_start}, ensure_ascii=False)
          return """```python
  PLUGIN_ID = "mock_cleaner"
  PLUGIN_VERSION = "1.0.0"
  def analyze(markdown: str) -> dict: return {"summary": [], "warnings": []}
  def clean(markdown: str) -> str: return markdown
  ```"""
  
  
  def test_learning_strips_only_toc(tmp_path):
      markdown = tmp_path / "book.md"
      markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
      work_dir = tmp_path / "mathos-formatting" / "book"
  
      core.run_learning_from_provider(
          markdown_path=markdown,
          provider_client=SuccessfulMockProvider(toc_start_line=3, main_text_start_line=8),
          heading_prompt="# Heading Rules Prompt",
          content_prompt="# Content Cleaner Prompt",
          work_dir=work_dir,
      )
  
      candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
      # Title heading before TOC must be kept
      assert "# 数学" in candidate_text
      # TOC must be stripped (lines 3 to 7)
      assert "# 目录" not in candidate_text
      # Main text must be kept
      assert "# 第一章 数列" in candidate_text
  
  
  def test_learning_fallback_when_toc_missing(tmp_path):
      markdown = tmp_path / "book.md"
      markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
      work_dir = tmp_path / "mathos-formatting" / "book"
  
      core.run_learning_from_provider(
          markdown_path=markdown,
          provider_client=SuccessfulMockProvider(toc_start_line=None, main_text_start_line=8),
          heading_prompt="# Heading Rules Prompt",
          content_prompt="# Content Cleaner Prompt",
          work_dir=work_dir,
      )
  
      candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
      # Fallback: keep entire document intact
      assert "# 数学" in candidate_text
      assert "# 目录" in candidate_text
  ```

- [ ] **Step 3: Run the tests to verify failure**
  Run:
  ```powershell
  python -m pytest tests/test_mathos_formatting_guarded.py -k "test_learning_strips_only_toc"
  ```
  Expected output: Fail (because `mathos_formatting_core.py` has not been updated yet, so `toc_start_line` is ignored and it deletes everything before `main_text_start_line`).

- [ ] **Step 4: Commit changes**
  Run:
  ```bash
  git add tests/test_mathos_formatting_guarded.py
  git commit -m "test: add unit tests for TOC selective stripping and update mock client"
  ```

---

### Task 3: Core Implementation Update

**Files:**
- Modify: [mathos_formatting_core.py](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-formatting/scripts/mathos_formatting_core.py)

- [ ] **Step 1: Modify `mathos_formatting_core.py`**
  Modify [mathos_formatting_core.py](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-formatting/scripts/mathos_formatting_core.py) in the `toc-detection-provider` stage to extract both lines and slice the file contents accordingly.
  
  Target content to replace (around lines 944-952):
  ```python
          toc_detection_payload = json.loads(parse_json_artifact_from_text(toc_detection_response))
          main_text_start_line = int(toc_detection_payload.get("main_text_start_line"))
          
          stage1_lines = stage1_text.splitlines(keepends=True)
          if main_text_start_line < 1 or main_text_start_line > len(stage1_lines):
              raise FormattingError(f"LLM returned invalid line number: {main_text_start_line}")
          
          stripped_text = "".join(stage1_lines[main_text_start_line - 1:])
  ```
  
  Replacement content:
  ```python
          toc_detection_payload = json.loads(parse_json_artifact_from_text(toc_detection_response))
          toc_start_line = toc_detection_payload.get("toc_start_line")
          main_text_start_line = int(toc_detection_payload.get("main_text_start_line"))
          
          stage1_lines = stage1_text.splitlines(keepends=True)
          if main_text_start_line < 1 or main_text_start_line > len(stage1_lines):
              raise FormattingError(f"LLM returned invalid line number: {main_text_start_line}")
          
          if toc_start_line is not None:
              toc_start_line = int(toc_start_line)
              if 1 <= toc_start_line <= main_text_start_line <= len(stage1_lines):
                  before_toc = stage1_lines[:toc_start_line - 1]
                  after_toc = stage1_lines[main_text_start_line - 1:]
                  stripped_text = "".join(before_toc + after_toc)
              else:
                  stripped_text = stage1_text
          else:
              stripped_text = stage1_text
  ```

- [ ] **Step 2: Run all tests to verify success**
  Run:
  ```powershell
  python -m pytest tests/test_mathos_formatting_guarded.py
  ```
  Expected output: All tests PASS.

- [ ] **Step 3: Commit implementation changes**
  Run:
  ```bash
  git add skills/mathos-formatting/scripts/mathos_formatting_core.py
  git commit -m "feat(formatting): implement selective TOC stripping and fallback preservation"
  ```
