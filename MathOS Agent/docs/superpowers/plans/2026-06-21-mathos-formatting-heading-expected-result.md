# MathOS Heading Expected Result Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `heading_expected_result.md` as a second DeepSeek output in Step 3, using the same `toc_and_headings.md` payload as the existing Python processor call.

**Architecture:** Keep the current Python generation and sandbox path unchanged. Add an independent Markdown prompt/call, validate its three-section response locally, reuse it when valid, and expose it as the routed artifact if its validation fails.

**Tech Stack:** Python 3, pathlib, pytest, existing DeepSeek provider adapter and MathOS guarded workflow.

---

## File Map

- Create `skills/mathos-formatting/agents/heading_expected_result_prompt.md`: Markdown-only DeepSeek contract.
- Modify `skills/mathos-formatting/scripts/step3_heading_processing.py`: validation, second call, reuse, and artifact registration.
- Modify `skills/mathos-formatting/scripts/automation_runner.py`: route a custom Step 3 artifact when supplied by an exception.
- Modify `tests/test_mathos_formatting_guarded.py`: dual-call, validation, reuse, and routing regressions.
- Modify `skills/mathos-formatting/SKILL.md`: document the new Step 3 artifact and call contract.

The modified code and test files share existing uncommitted formatter work. Preserve it, do not stage the files wholesale, and leave implementation changes uncommitted unless separately requested.

### Task 1: Add Failing Expected-Result Contract Tests

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add a reusable valid expected-result fixture**

Add near `_batch_processor_source`:

```python
HEADING_EXPECTED_RESULT = """# 修改后的目录

- `# 第一章 数列`
- `## 1.1 数列的概念`

# 标题修改明细

- `# 第一章 数列` -> `# 第一章 数列`
- `# 练习` -> `#### 练习`

# 预期效果

- TOC 标题保持 H1-H3，非目录标题降级为 H4-H6。
"""
```

- [ ] **Step 2: Add validation tests**

```python
def test_validate_heading_expected_result_requires_safe_three_section_markdown():
    assert core.validate_heading_expected_result(HEADING_EXPECTED_RESULT) == HEADING_EXPECTED_RESULT

    invalid_responses = [
        "",
        "# 修改后的目录\n\n# 预期效果\n",
        "# 标题修改明细\n\n# 修改后的目录\n\n# 预期效果\n",
        "```markdown\n# 修改后的目录\n```\n",
        '{"modified_toc": []}',
        "import os\n\ndef main():\n    pass\n",
    ]
    for response in invalid_responses:
        with pytest.raises(core.FormattingError, match="heading expected result"):
            core.validate_heading_expected_result(response)
```

- [ ] **Step 3: Run the validation test and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py::test_validate_heading_expected_result_requires_safe_three_section_markdown -q
```

Expected: FAIL because `validate_heading_expected_result` does not exist.

### Task 2: Add Failing Dual-Call and Reuse Tests

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add a recording provider**

```python
class HeadingDualOutputProvider:
    def __init__(self, expected_result=HEADING_EXPECTED_RESULT):
        self.expected_result = expected_result
        self.calls = []

    def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
        self.calls.append((system_prompt, user_payload, response_format))
        if "Heading Expected Result Prompt" in system_prompt:
            return self.expected_result
        return _batch_processor_source([])
```

- [ ] **Step 2: Add the two-call artifact test**

```python
def test_step3_writes_expected_result_from_same_payload_without_extra_work_artifacts(tmp_path):
    provider = HeadingDualOutputProvider()
    work_dir = tmp_path / "work"
    candidate = work_dir / "candidate.md"
    source = tmp_path / "book.md"
    original = "# 第一章 数列\n\n# 练习\n"
    source.write_text(original, encoding="utf-8")
    artifacts = {}

    core.run_heading_processing(
        source,
        original,
        "SAME TOC AND HEADINGS PAYLOAD",
        "# Heading Rules Prompt",
        provider,
        work_dir,
        candidate,
        artifacts,
        120,
    )

    assert len(provider.calls) == 2
    assert provider.calls[0][1] == provider.calls[1][1] == "SAME TOC AND HEADINGS PAYLOAD"
    assert (work_dir / "heading_expected_result.md").read_text(encoding="utf-8") == HEADING_EXPECTED_RESULT
    assert artifacts["heading_expected_result"] == work_dir / "heading_expected_result.md"
    assert not (work_dir / "heading_expected_result_prompt.md").exists()
    assert not (work_dir / "heading_expected_result_response.md").exists()
```

- [ ] **Step 3: Add reuse and missing-artifact regeneration tests**

```python
def test_step3_reuses_expected_result_and_regenerates_only_when_missing(tmp_path):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "heading_processor.py").write_text(_batch_processor_source([]), encoding="utf-8")
    (work_dir / "heading_expected_result.md").write_text(HEADING_EXPECTED_RESULT, encoding="utf-8")
    source = tmp_path / "book.md"
    source.write_text("# 第一章 数列\n", encoding="utf-8")

    reuse_provider = HeadingDualOutputProvider()
    core.run_heading_processing(
        source, "# 第一章 数列\n", "PAYLOAD", "# Heading Rules Prompt",
        reuse_provider, work_dir, work_dir / "candidate.md", {}, 120,
    )
    assert reuse_provider.calls == []

    (work_dir / "heading_expected_result.md").unlink()
    regenerate_provider = HeadingDualOutputProvider()
    core.run_heading_processing(
        source, "# 第一章 数列\n", "PAYLOAD", "# Heading Rules Prompt",
        regenerate_provider, work_dir, work_dir / "candidate.md", {}, 120,
    )
    assert len(regenerate_provider.calls) == 1
    assert "Heading Expected Result Prompt" in regenerate_provider.calls[0][0]
```

- [ ] **Step 4: Run the Step 3 tests and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "step3_writes_expected_result or step3_reuses_expected_result"
```

Expected: FAIL because Step 3 currently makes only the Python call and never writes the new file.

### Task 3: Implement the Markdown Prompt and Validator

**Files:**
- Create: `skills/mathos-formatting/agents/heading_expected_result_prompt.md`
- Modify: `skills/mathos-formatting/scripts/step3_heading_processing.py`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Create the DeepSeek Markdown prompt**

Create `heading_expected_result_prompt.md` with:

```markdown
# Heading Expected Result Prompt

Using the supplied immutable TOC and BODY HEADINGS, describe the complete expected heading result. Return Markdown only.

Required sections, exactly once and in this order:

# 修改后的目录
# 标题修改明细
# 预期效果

Under 修改后的目录, list every expected heading as a bullet containing a literal Markdown heading line, for example `- \`## 1.1 集合\``.
Under 标题修改明细, list every proposed change as `原标题 -> 预期标题`.
Under 预期效果, summarize TOC alignment, H1-H6 normalization, high-confidence OCR corrections, and non-TOC demotions.

The TOC is authoritative. Do not invent parent or chapter context. Do not rewrite educational body content. Do not return Python, JSON, Markdown fences, or text outside the three required sections.
```

- [ ] **Step 2: Add the response validator**

Add to `step3_heading_processing.py`:

```python
EXPECTED_RESULT_SECTIONS = (
    "# 修改后的目录",
    "# 标题修改明细",
    "# 预期效果",
)


class HeadingExpectedResultError(FormattingError):
    def __init__(self, message: str, artifact_path: Path):
        super().__init__(message)
        self.error_artifact = artifact_path


def validate_heading_expected_result(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise FormattingError("heading expected result is empty")
    if "```" in stripped or "~~~" in stripped:
        raise FormattingError("heading expected result must not contain Markdown fences")
    if stripped.startswith(("{", "[")):
        raise FormattingError("heading expected result must not be JSON")
    if re.search(r"(?m)^(?:import\s+|from\s+\S+\s+import\s+|def\s+\w+\s*\()", stripped):
        raise FormattingError("heading expected result must not contain Python")
    positions = []
    for section in EXPECTED_RESULT_SECTIONS:
        if stripped.count(section) != 1:
            raise FormattingError(f"heading expected result must contain {section} exactly once")
        positions.append(stripped.index(section))
    if positions != sorted(positions):
        raise FormattingError("heading expected result sections are out of order")
    return text
```

- [ ] **Step 3: Run the validator test and verify GREEN**

Run the Task 1 test. Expected: PASS.

### Task 4: Implement the Second Call and Recovery Behavior

**Files:**
- Modify: `skills/mathos-formatting/scripts/step3_heading_processing.py:80-120`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add expected-result loading/generation**

Add this helper:

```python
def _ensure_heading_expected_result(
    heading_payload: str,
    provider_client: object,
    work_dir: Path,
    artifacts: dict[str, Path],
    timeout_seconds: int,
) -> Path:
    path = work_dir / "heading_expected_result.md"
    if path.exists():
        try:
            validate_heading_expected_result(path.read_text(encoding="utf-8"))
            artifacts["heading_expected_result"] = path
            return path
        except FormattingError:
            pass
    prompt_path = Path(__file__).resolve().parent.parent / "agents" / "heading_expected_result_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    response = provider_client.chat(
        prompt, heading_payload, timeout_seconds=timeout_seconds, response_format=None
    )
    _write_text_artifact(path, response)
    artifacts["heading_expected_result"] = path
    try:
        validate_heading_expected_result(response)
    except FormattingError as exc:
        raise HeadingExpectedResultError(str(exc), path) from exc
    return path
```

- [ ] **Step 2: Invoke it after the Python script is ready**

Immediately after the existing script generation/reuse branch, call:

```python
    _ensure_heading_expected_result(
        heading_payload, provider_client, work_dir, artifacts, timeout_seconds
    )
```

Do not pass the Python response, generated script, processed candidate, or report to the second call.

- [ ] **Step 3: Add the artifact to the Step 3 summary**

Change the report summary to:

```python
heading_summary=["heading_processor.py", "heading_expected_result.md", *summary]
```

- [ ] **Step 4: Run all Step 3 focused tests**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "heading_expected_result or step3_"
```

Expected: all selected tests pass.

### Task 5: Route Invalid Markdown to the New Artifact

**Files:**
- Modify: `skills/mathos-formatting/scripts/automation_runner.py:190-210`
- Modify: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add a failing routing test**

Create a provider that returns valid TOC/Python outputs and `"invalid expected result"` for the expected-result prompt. Run `run_automated_formatting` and assert:

```python
assert result.exit_code == 1
assert Path(result.digest["error_artifact"]).name == "heading_expected_result.md"
```

- [ ] **Step 2: Verify the routing test fails**

Expected: it routes to `heading_processor_response.py` under the current generic Step 3 mapping.

- [ ] **Step 3: Honor exception-provided artifacts**

In `run_automated_formatting`'s exception handler, before `_failure_artifact`, add:

```python
        explicit_artifact = getattr(exc, "error_artifact", None)
        if isinstance(explicit_artifact, Path) and explicit_artifact.is_file():
            error_artifact = explicit_artifact
        else:
            error_artifact = _failure_artifact(work_dir, failed_stage)
```

- [ ] **Step 4: Run routing and automated-run tests**

Expected: the new routing test and existing one-artifact failure tests pass.

### Task 6: Document and Verify

**Files:**
- Modify: `skills/mathos-formatting/SKILL.md`
- Verify all changed files.

- [ ] **Step 1: Update the canonical skill contract**

Document that Step 3 makes two calls with the same `toc_and_headings.md` payload and add `heading_expected_result.md` to Artifact Layout. State that it is explanatory, structurally validated, and does not replace Step 5.

- [ ] **Step 2: Run complete verification**

```powershell
python -m py_compile skills\mathos-formatting\scripts\step3_heading_processing.py skills\mathos-formatting\scripts\automation_runner.py
python -m pytest tests\test_mathos_formatting_guarded.py -q
$env:PYTHONUTF8 = '1'
python skills\mathos-formatting\scripts\mathos_formatting.py --help
```

Expected: zero failures and CLI exit `0`.

- [ ] **Step 3: Run a focused real Step 3 generation**

Use the existing real `toc_and_headings.md` payload and a fresh work directory containing no `heading_expected_result.md`. Confirm the two provider calls receive identical payload bytes, the original four Step 3 files remain, the new MD exists with all three sections, and the source Markdown SHA-256 is unchanged.

- [ ] **Step 4: Inspect the scoped diff**

```powershell
git diff --check -- skills/mathos-formatting/SKILL.md tests/test_mathos_formatting_guarded.py
rg -n "heading_expected_result|HeadingExpectedResult" skills\mathos-formatting tests\test_mathos_formatting_guarded.py
```

Expected: only the approved new prompt, second call, validator, routing, tests, and documentation appear alongside recognized pre-existing changes.
