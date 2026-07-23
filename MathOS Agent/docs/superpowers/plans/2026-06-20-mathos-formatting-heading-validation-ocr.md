# MathOS Heading Validation OCR Equivalence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align Step 5 with Stage 3's conservative OCR-equivalence rules and prevent repetitive provider errors from expanding into truncated JSON.

**Architecture:** Keep validation provider-backed and preserve the existing three-field JSON response. Tighten the prompt so meaning-preserving OCR variants are accepted, then enforce a maximum of 20 unique error strings in the Python response validator.

**Tech Stack:** Python 3, JSON, pytest, existing MathOS formatter provider client.

---

## File Map

- Modify `tests/test_mathos_formatting_guarded.py`: prompt and response-contract regressions.
- Modify `skills/mathos-formatting/agents/heading_check_prompt.md`: OCR equivalence and bounded errors.
- Modify `skills/mathos-formatting/scripts/step5_heading_validation.py`: deterministic duplicate and size rejection.

These code files share the current uncommitted formatter refactor. Do not stage them wholesale or create a mixed implementation commit. Preserve all pre-existing changes and inspect only the scoped diff.

### Task 1: Lock the Prompt Contract With a Failing Test

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py:1202-1213`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Extend the existing heading prompt test**

Add these assertions to `test_heading_check_payload_declares_local_count_and_prompt_accepts_non_toc_h4`:

```python
    assert "`③` and `3` are equivalent" in prompt
    assert "`⑨` and `3` are not equivalent" in prompt
    assert "at most 20 unique errors" in prompt
    assert "Do not repeat an error string" in prompt
    assert "every violation" not in prompt
```

- [ ] **Step 2: Run the prompt test and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py::test_heading_check_payload_declares_local_count_and_prompt_accepts_non_toc_h4 -q
```

Expected: FAIL because the current prompt lacks the OCR-equivalence and bounded-error wording.

### Task 2: Add Bounded Error Response Tests

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py:1229-1247`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add duplicate and oversized response tests**

Add this test after `test_validate_heading_check_response_requires_success_and_matching_count`:

```python
def test_validate_heading_check_response_rejects_duplicate_and_oversized_errors():
    duplicate_response = json.dumps(
        {
            "valid": False,
            "checked_heading_count": 2,
            "errors": ["same violation", "same violation"],
        }
    )
    with pytest.raises(core.FormattingError, match="unique"):
        core.validate_heading_check_response(duplicate_response, expected_heading_count=2)

    oversized_response = json.dumps(
        {
            "valid": False,
            "checked_heading_count": 21,
            "errors": [f"violation {index}" for index in range(21)],
        }
    )
    with pytest.raises(core.FormattingError, match="at most 20"):
        core.validate_heading_check_response(oversized_response, expected_heading_count=21)
```

- [ ] **Step 2: Run the parser test and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py::test_validate_heading_check_response_rejects_duplicate_and_oversized_errors -q
```

Expected: FAIL because both responses currently reach the generic candidate-rejected error rather than contract-specific errors.

### Task 3: Implement the Prompt and Parser Contract

**Files:**
- Modify: `skills/mathos-formatting/agents/heading_check_prompt.md:15-25`
- Modify: `skills/mathos-formatting/scripts/step5_heading_validation.py:8-30`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Define the deterministic error limit**

Add below the imports in `step5_heading_validation.py`:

```python
MAX_HEADING_CHECK_ERRORS = 20
```

- [ ] **Step 2: Enforce unique and bounded errors**

After validating that `errors` is a string list, add:

```python
    if len(errors) != len(set(errors)):
        raise FormattingError("heading validation errors must be unique")
    if len(errors) > MAX_HEADING_CHECK_ERRORS:
        raise FormattingError(
            f"heading validation errors must contain at most {MAX_HEADING_CHECK_ERRORS} entries"
        )
```

Keep invalid JSON, count mismatch, `valid: false`, and nonempty-error rejection unchanged.

- [ ] **Step 3: Replace the conflicting prompt rules**

Replace the final validation bullets in `heading_check_prompt.md` with:

```markdown
- Match headings using the same conservative, meaning-preserving OCR equivalence used by Stage 3.
- Circled digits and the same Arabic digit are equivalent; for example, `③` and `3` are equivalent.
- Numeric value must remain identical; for example, `⑨` and `3` are not equivalent.
- Full-width or half-width punctuation and insignificant spacing differences are equivalent only when title meaning, source order, and hierarchy are unchanged.
- Preserve the body heading text; validation does not require rewriting an equivalent OCR form to the TOC spelling.
- Set `valid` to false and return at most 20 unique errors that represent genuine violations.
- Do not repeat an error string, even when the same violation pattern occurs on several headings.
```

Retain the existing rules for hierarchy, non-TOC H4-H6 headings, invented entries, and generic parent context. Remove `add a precise error for every violation`.

- [ ] **Step 4: Run focused prompt and parser tests and verify GREEN**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "heading_check_payload or validate_heading_check_response"
```

Expected: all selected tests pass.

### Task 4: Verify and Re-run the Real Formatter

**Files:**
- Verify: `skills/mathos-formatting/agents/heading_check_prompt.md`
- Verify: `skills/mathos-formatting/scripts/step5_heading_validation.py`
- Verify: `tests/test_mathos_formatting_guarded.py`
- Runtime artifacts: `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\2025解题觉醒邓诚数学\`

- [ ] **Step 1: Run syntax, guarded-suite, and CLI verification**

Run:

```powershell
python -m py_compile skills\mathos-formatting\scripts\step5_heading_validation.py
python -m pytest tests\test_mathos_formatting_guarded.py -q
python skills\mathos-formatting\scripts\mathos_formatting.py --help
```

Expected: compilation succeeds, the guarded suite has zero failures, and CLI help exits `0`.

- [ ] **Step 2: Run the formatter with source hashing**

Run:

```powershell
$source = 'C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\2025解题觉醒邓诚数学.md'
$before = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
python skills\mathos-formatting\scripts\mathos_formatting.py run $source --env 'C:\Mathematics-Knowledge\.env'
$runExit = $LASTEXITCODE
$after = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
if ($before -ne $after) { throw 'Source Markdown changed during formatting run' }
exit $runExit
```

Expected: the hashes match. The run must not fail from repeated equivalent-circle-number errors or truncated Step 5 JSON.

- [ ] **Step 3: Read the compact result contract**

Read only:

```powershell
Get-Content -Raw -Encoding UTF8 -LiteralPath 'C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\2025解题觉醒邓诚数学\result-summary.json'
```

Expected on success: `status: passed`, `safe_to_approve: true`, and `source_unchanged: true`. On failure, read only `error_artifact` and verify that any remaining rejection is a genuine, bounded contract error rather than repeated OCR-equivalence noise or truncated JSON.

- [ ] **Step 4: Inspect the scoped final diff**

Run:

```powershell
git diff --check -- skills/mathos-formatting/agents/heading_check_prompt.md tests/test_mathos_formatting_guarded.py
git diff -- skills/mathos-formatting/agents/heading_check_prompt.md tests/test_mathos_formatting_guarded.py
rg -n "MAX_HEADING_CHECK_ERRORS|must be unique|at most" skills\mathos-formatting\scripts\step5_heading_validation.py
```

Expected: no whitespace errors; only the approved prompt, parser, and regression-test behavior is added alongside recognized pre-existing changes.
