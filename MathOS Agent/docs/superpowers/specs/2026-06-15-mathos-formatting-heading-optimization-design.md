# MathOS Formatting Heading Optimization Design

This spec details the design for adding a heading optimization stage (Stage 5) to the `mathos-formatting` skill. This stage corrects OCR errors in headings and optimizes heading titles semantically using Deepseek.

## 1. Goal & Context
The current formatting pipeline runs 4 stages: heading rules generation, TOC detection & stripping, H1 extraction, and content rules formatting. Sometimes converted PDFs contain OCR errors in headings (e.g. `ϰο4` instead of `复习参考题 4`). To address this, we will add a 5th stage that extracts all headings, queries Deepseek to optimize them, applies the JSON mappings safely back to the Markdown file, and saves the mappings for local reuse.

---

## 2. Architectural Changes & Files to Touch

We will touch the following files:

### `skills/mathos-formatting/agents/heading_optimization_prompt.md` [NEW]
A system prompt template for Deepseek that:
- Instructs the LLM to standardize heading text, fix OCR typos/noise, and optimize brief heading titles semantically.
- Restricts the LLM to return a JSON object mapping `{"original_heading_line": "optimized_heading_line"}`.
- Mandates that the heading levels (number of `#` characters) must remain identical.

### `skills/mathos-formatting/scripts/mathos_formatting_core.py` [MODIFY]
- Add `run_heading_optimization(candidate_text: str, provider_client: object, prompt: str, timeout_seconds: int = 120) -> dict[str, str]` to extract headings, query the provider, parse the JSON mapping, and validate that heading levels are preserved.
- Update `run_learning_from_provider` to:
  - Extract headings from the candidate text after Stage 4 is completed.
  - Call `run_heading_optimization`.
  - Apply the validated replacements to `candidate.md`.
  - Write `heading_optimizations.json` to the work directory.
- Update `apply_approved_program` to check if `heading_optimizations.json` exists in the approved directory, and apply its rules locally.

### `skills/mathos-formatting/scripts/mathos_formatting.py` [MODIFY]
- Update `command_approve` to copy `heading_optimizations.json` from the work directory to the approved root.
- Update `command_candidate_from_artifacts` to accept `--heading-optimizations` parameter and apply manual mappings.

---

## 3. Detailed Data Flow

1. **Extraction**:
   ```python
   heading_lines = [line.strip() for line in markdown.splitlines() if line.strip().startswith("#")]
   ```
2. **Provider Call**:
   Send the system prompt and the list of headings to Deepseek. Request response format `{"type": "json_object"}`.
3. **Validation**:
   For each key-value pair `(original, optimized)` in the JSON:
   - Ensure `original` and `optimized` are non-empty and start with the same number of `#` characters.
   - If not, drop the pair and log a warning.
4. **Application**:
   Apply the validated mapping line-by-line:
   ```python
   lines = markdown.splitlines()
   for i, line in enumerate(lines):
       stripped = line.strip()
       if stripped in validated_mapping:
           # Maintain original indentation/newlines
           lines[i] = line.replace(stripped, validated_mapping[stripped])
   markdown = "\n".join(lines) + "\n"
   ```

---

## 4. Error Handling & Safety
- **Auditing Safe-Guards**: This stage executes after Stage 1-4 heading safety audits have finished.
- **Level Preservation**: If Deepseek attempts to change a heading's level (e.g. mapping `## ϰο` to `# 正常标题`), the validator discards it.
- **Graceful API Fallback**: If the Deepseek call fails (timeouts, empty response, invalid JSON schema), the failure is logged as a warning, heading optimization is skipped, and the candidate is successfully written with Stage 4 formatting intact.

---

## 5. Testing & Verification

We will add the following tests to `tests/test_mathos_formatting_guarded.py`:
- `test_heading_optimization_success`: Mocks a successful LLM response with heading replacements and verifies they are correctly applied and written to `heading_optimizations.json`.
- `test_heading_optimization_level_safety`: Mocks an LLM response containing level changes and verifies they are ignored.
- `test_heading_optimization_graceful_fallback`: Mocks a failed Deepseek call and verifies the pipeline completes without crashing.
