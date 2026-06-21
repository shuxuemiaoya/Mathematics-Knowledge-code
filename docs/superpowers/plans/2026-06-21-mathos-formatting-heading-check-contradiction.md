# MathOS Heading-Check Contradiction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject internally contradictory Step 5 error entries, strengthen the DeepSeek contract, and resume the failed formatter run without weakening candidate validation.

**Architecture:** Keep the existing JSON schema and fail-closed execution path. Add a small deterministic marker check inside the Step 5 validator and reinforce the provider prompt so allowed OCR equivalences never enter `errors`; do not filter errors or infer success locally.

**Tech Stack:** Python 3, `json`, pytest, existing DeepSeek provider adapter and MathOS guarded workflow.

---

## File Map

- Modify `tests/test_mathos_formatting_guarded.py`: regression coverage for contradictory and genuine error entries.
- Modify `skills/mathos-formatting/agents/heading_check_prompt.md`: explicit output consistency contract.
- Modify `skills/mathos-formatting/scripts/step5_heading_validation.py`: deterministic self-negating-error rejection.
- Modify `skills/mathos-formatting/SKILL.md`: document contradictory provider output as a fail-closed condition.

The worktree already contains user-owned formatter changes in these files. Preserve them and leave implementation changes uncommitted unless the user separately requests a commit.

### Task 1: Reproduce the Contradictory Response

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add a focused English and Chinese regression test**

Add after the existing heading-check response tests:

```python
@pytest.mark.parametrize(
    "error",
    [
        "Circled digits are equivalent, so this is not an error.",
        "圈号数字与阿拉伯数字等价，因此这不是错误。",
    ],
)
def test_validate_heading_check_response_rejects_self_negating_errors(error):
    response = json.dumps(
        {
            "valid": False,
            "checked_heading_count": 1,
            "errors": [error],
        },
        ensure_ascii=False,
    )

    with pytest.raises(core.FormattingError, match="internally contradictory"):
        core.validate_heading_check_response(response, expected_heading_count=1)
```

- [ ] **Step 2: Prove genuine violations keep the existing rejection behavior**

```python
def test_validate_heading_check_response_keeps_genuine_candidate_rejections():
    response = json.dumps(
        {
            "valid": False,
            "checked_heading_count": 1,
            "errors": ["Non-TOC heading uses H2."],
        }
    )

    with pytest.raises(core.FormattingError, match="rejected the candidate"):
        core.validate_heading_check_response(response, expected_heading_count=1)
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "self_negating_errors or genuine_candidate_rejections"
```

Expected: the genuine-violation test passes; both self-negating cases fail because the current validator reports them as ordinary candidate rejections rather than internally contradictory provider output.

### Task 2: Strengthen Prompt and Validator

**Files:**
- Modify: `skills/mathos-formatting/agents/heading_check_prompt.md`
- Modify: `skills/mathos-formatting/scripts/step5_heading_validation.py`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add explicit prompt invariants**

Append these rules before the JSON-only output rule:

```markdown
- The `errors` array may contain only genuine violations. Never include an allowed equivalence, a non-error explanation, or any sentence saying that something is not an error.
- Before responding, remove every allowed equivalence from `errors`. If no genuine violations remain, return `valid: true` and `errors: []`.
- `valid: false` requires at least one genuine violation in `errors`; `valid: true` requires `errors: []`.
```

- [ ] **Step 2: Add a small explicit marker set**

Near `MAX_HEADING_CHECK_ERRORS`, add:

```python
SELF_NEGATING_ERROR_MARKERS = (
    "not an error",
    "isn't an error",
    "不是错误",
    "并非错误",
    "不算错误",
    "不属于错误",
)
```

- [ ] **Step 3: Reject contradictory entries before candidate judgment**

After validating that `errors` is a list of strings, add:

```python
    contradictory_errors = [
        error
        for error in errors
        if any(marker in error.casefold() for marker in SELF_NEGATING_ERROR_MARKERS)
    ]
    if contradictory_errors:
        raise FormattingError(
            "heading validation response is internally contradictory: "
            "errors must contain genuine violations only"
        )
```

Do not remove entries, change `valid`, or infer candidate success.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Task 1 command. Expected: all selected tests pass.

### Task 3: Document, Verify, and Resume

**Files:**
- Modify: `skills/mathos-formatting/SKILL.md`
- Verify: all scoped files and the existing test work directory.

- [ ] **Step 1: Extend the failure contract**

Add under Failure Handling:

```markdown
- Heading validation errors contain self-negating text such as `not an error` or `不是错误`; treat the provider response as internally contradictory and fail closed.
```

- [ ] **Step 2: Run complete verification**

```powershell
python -m py_compile skills\mathos-formatting\scripts\step5_heading_validation.py
python -m pytest tests\test_mathos_formatting_guarded.py -q
$env:PYTHONUTF8 = '1'
python skills\mathos-formatting\scripts\mathos_formatting.py --help
git diff --check -- skills/mathos-formatting/SKILL.md skills/mathos-formatting/agents/heading_check_prompt.md skills/mathos-formatting/scripts/step5_heading_validation.py tests/test_mathos_formatting_guarded.py
```

Expected: compilation succeeds, all tests pass, CLI exits `0`, and no whitespace errors appear.

- [ ] **Step 3: Resume the real formatter run**

```powershell
$env:PYTHONUTF8 = '1'
python skills\mathos-formatting\scripts\mathos_formatting.py run "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\2025解题觉醒邓诚数学.md" --env "C:\Mathematics-Knowledge\.env" --timeout-seconds 180
```

Expected: Step 5 receives the strengthened prompt. A coherent valid response advances to Step 6; a contradictory response fails explicitly as invalid provider output rather than as a candidate violation.

- [ ] **Step 4: Read only the final digest and routed artifact when needed**

Read:

```powershell
Get-Content -LiteralPath "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\2025解题觉醒邓诚数学\result-summary.json" -Encoding UTF8
```

If failed, read only its `error_artifact`. Confirm the source SHA-256 remains `3FBBC65A0A05C8E5D58917CCAC7A9C7B8367173CD0A5BC88457FE4313CA02027`.
