# MathOS Formatting Multiline TOC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Stage 1 accept verbatim multiline and multi-page TOCs while continuing to reject provider responses that include body content.

**Architecture:** Keep provider output as one exact numbered source span. Add explicit prompt boundary rules, then replace per-line validation with a look-ahead classifier that recognizes page-bearing continuations and repeated TOC page headers without ever trimming an unrelated tail.

**Tech Stack:** Python 3, `re`, `pytest`, existing MathOS formatter CLI and provider client.

---

## File Map

- Modify `tests/test_mathos_formatting_guarded.py`: focused contract and regression tests.
- Modify `skills/mathos-formatting/scripts/step1_toc_extraction.py`: TOC reference detection and look-ahead validation.
- Modify `skills/mathos-formatting/agents/toc_detection_prompt.md`: provider instructions for wrapped entries and the final TOC boundary.
- Read only `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\2025解题觉醒邓诚数学\result-summary.json` after the final live run; read its single `error_artifact` only if it fails.

The first two files already contain uncommitted work from the active formatter refactor. Do not revert it, stage it wholesale, or create a mixed implementation commit. Inspect the final diff carefully and leave the new code changes uncommitted unless the user separately requests a commit.

### Task 1: Lock the Multiline TOC Contract With Failing Tests

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py:1089-1130`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add a failing acceptance test for wrapped entries and repeated page headers**

Add this test after `test_validate_verbatim_toc_response_keeps_media_in_span_but_not_toc_markdown`:

```python
def test_validate_verbatim_toc_response_accepts_wrapped_entries_and_repeated_headers():
    sample = (
        "1: # 目录\n2: # CONTENTS\n3: 考点 3 导数的基础（三）——\n"
        "4: \n5: 导数的几何意义 026\n6: # 目录\n7: # CONTENTS\n"
        "8: 新情境索引\n9: P154 T12\n10: \n11: # 正文\n"
    )
    response = "\n".join(sample.splitlines()[:9]) + "\n"

    toc = core.validate_verbatim_toc_response(sample, response)

    assert (toc.start_line, toc.end_line) == (1, 9)
    assert toc.markdown == (
        "# 目录\n# CONTENTS\n考点 3 导数的基础（三）——\n"
        "导数的几何意义 026\n# 目录\n# CONTENTS\n新情境索引\nP154 T12\n"
    )
```

- [ ] **Step 2: Add failing rejection tests for unfinished entries and body tails**

Add these tests beside the acceptance test:

```python
def test_validate_verbatim_toc_response_rejects_unfinished_wrapped_entry():
    sample = "1: # 目录\n2: 第一章 数列 1\n3: 考点 3 导数的基础（三）——\n"

    with pytest.raises(core.FormattingError, match="unfinished wrapped TOC entry"):
        core.validate_verbatim_toc_response(sample, sample)


def test_validate_verbatim_toc_response_rejects_body_tail_without_trimming():
    sample = (
        "1: # 目录\n2: 第一章 数列 1\n3: \n4: # 第一章 数列\n"
        "5: 本章学习数列的基本概念。\n"
    )

    with pytest.raises(core.FormattingError, match="unrelated body text"):
        core.validate_verbatim_toc_response(sample, sample)
```

- [ ] **Step 3: Run the three new tests and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "wrapped_entries or unfinished_wrapped_entry or body_tail_without_trimming"
```

Expected: the acceptance test fails on `考点 3 导数的基础（三）——`; the two rejection tests fail because the current errors are not the new precise messages.

### Task 2: Implement Strict Look-Ahead TOC Validation

**Files:**
- Modify: `skills/mathos-formatting/scripts/step1_toc_extraction.py:15-104`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add explicit page-reference recognition**

Add a regex beside `ATX_HEADING_RE` and split the current line predicate into page-reference and general predicates:

```python
TOC_TRAILING_REFERENCE_RE = re.compile(
    r"(?:\bP\d+(?:\s+T\d+)?|(?:→|\\rightarrow)\s*大招\s*\d+)\s*$",
    re.IGNORECASE,
)


def _has_toc_reference(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped
        and (
            TOC_ENTRY_PAGE_RE.search(stripped)
            or TOC_TRAILING_REFERENCE_RE.search(stripped)
        )
    )


def _looks_like_toc_line(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped
        and (
            TOC_HEADING_RE.match(stripped)
            or _has_toc_reference(stripped)
            or re.match(r"^(?:#{1,6}\s+)?\d+(?:[.．]\d+)+\s+.+", stripped)
        )
    )
```

- [ ] **Step 2: Add a helper that finds the next semantic source line**

Add this helper before `validate_verbatim_toc_response`:

```python
def _next_semantic_line(
    response_lines: list[tuple[int, str]], start_index: int
) -> tuple[int, str] | None:
    in_details = False
    for index in range(start_index, len(response_lines)):
        _, line = response_lines[index]
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^<details(?:\s|>)", stripped, flags=re.IGNORECASE):
            in_details = True
            continue
        if in_details:
            if re.match(r"^</details\s*>", stripped, flags=re.IGNORECASE):
                in_details = False
            continue
        if re.match(r"^!\[[^]]*]\([^)]+\)$", stripped):
            continue
        return index, line
    return None
```

- [ ] **Step 3: Replace independent rejection with look-ahead state handling**

Add a helper that requires a non-TOC heading to lead to actual TOC evidence rather than an arbitrary body paragraph:

```python
def _has_following_toc_evidence(
    response_lines: list[tuple[int, str]], start_index: int
) -> bool:
    next_semantic = _next_semantic_line(response_lines, start_index)
    while next_semantic is not None:
        index, line = next_semantic
        stripped = line.strip()
        if TOC_HEADING_RE.match(stripped) or ATX_HEADING_RE.match(line):
            next_semantic = _next_semantic_line(response_lines, index + 1)
            continue
        if _looks_like_toc_line(line):
            return True
        continuation = _next_semantic_line(response_lines, index + 1)
        return continuation is not None and _has_toc_reference(continuation[1])
    return False
```

Then enumerate `response_lines` in `validate_verbatim_toc_response`. Keep the existing contiguous and verbatim checks, media/details handling, and duplicate body-heading protection. Apply these rules in order:

```python
if TOC_HEADING_RE.match(stripped):
    toc_lines.append(line)
    continue

heading_match = ATX_HEADING_RE.match(line)
if heading_match is not None:
    if not _has_following_toc_evidence(response_lines, index + 1):
        raise FormattingError("TOC response contains unrelated body heading text")
    heading_key = TOC_ENTRY_PAGE_RE.sub("", heading_match.group(2)).strip().casefold()
    if heading_key in seen_heading_titles:
        raise FormattingError("TOC response contains unrelated repeated body heading text")
    seen_heading_titles.add(heading_key)
    toc_lines.append(line)
    continue

if _looks_like_toc_line(line):
    toc_lines.append(line)
    continue

next_semantic = _next_semantic_line(response_lines, index + 1)
if next_semantic is not None and _has_toc_reference(next_semantic[1]):
    toc_lines.append(line)
    continue
if next_semantic is None:
    raise FormattingError("TOC response ends with an unfinished wrapped TOC entry")
raise FormattingError("TOC response contains unrelated body text outside the TOC entries")
```

Do not slice `response_lines`, shorten `end_line`, or return a valid prefix when any tail is rejected.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "validate_verbatim_toc_response"
```

Expected: all verbatim TOC validation tests pass, including existing unsafe-span tests.

### Task 3: Strengthen the Provider Boundary Prompt

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py`
- Modify: `skills/mathos-formatting/agents/toc_detection_prompt.md`

- [ ] **Step 1: Add a failing prompt-contract test**

Add near the TOC validator tests:

```python
def test_toc_detection_prompt_explains_wrapped_entries_and_body_boundary():
    prompt = (SKILL_ROOT / "agents" / "toc_detection_prompt.md").read_text(encoding="utf-8")

    assert "wrapped TOC entry" in prompt
    assert "repeated `# 目录` or `# CONTENTS`" in prompt
    assert "stop before the first main-text line" in prompt
    assert "Do not return the remainder of the sample" in prompt
```

- [ ] **Step 2: Run the prompt test and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py::test_toc_detection_prompt_explains_wrapped_entries_and_body_boundary -q
```

Expected: FAIL because the current prompt lacks the four explicit phrases.

- [ ] **Step 3: Add precise prompt rules**

Append these bullets under `Requirements:` in `toc_detection_prompt.md`:

```markdown
- A wrapped TOC entry may place its title fragment on one line and its page reference on the next nonblank line; include both unchanged lines.
- A multi-page TOC may repeat `# 目录` or `# CONTENTS`; include repeated page headers only while TOC entries continue after them.
- End the span at the final TOC entry and stop before the first main-text line, body exercise, answer, or body heading.
- Do not return the remainder of the sample merely because the TOC begins before the twentieth page.
```

- [ ] **Step 4: Run the prompt and validator tests**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "toc_detection_prompt or validate_verbatim_toc_response"
```

Expected: PASS.

### Task 4: Verify the Formatter and Re-run the Target

**Files:**
- Verify: `skills/mathos-formatting/scripts/step1_toc_extraction.py`
- Verify: `skills/mathos-formatting/agents/toc_detection_prompt.md`
- Verify: `tests/test_mathos_formatting_guarded.py`
- Runtime artifacts: `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\2025解题觉醒邓诚数学\`

- [ ] **Step 1: Run syntax and guarded-suite verification**

Run:

```powershell
python -m py_compile skills\mathos-formatting\scripts\step1_toc_extraction.py
python -m pytest tests\test_mathos_formatting_guarded.py -q
python skills\mathos-formatting\scripts\mathos_formatting.py --help
```

Expected: compilation succeeds, the guarded suite reports zero failures, and CLI help exits `0`.

- [ ] **Step 2: Verify compatibility references remain legacy-only**

Run:

```powershell
rg "content_rules.json|heading_rules.json|heading_optimizations.json" skills\mathos-formatting tests
```

Expected: matches are limited to explicit legacy compatibility code, tests, and documentation.

- [ ] **Step 3: Capture source bytes and run the formatter**

Run from `C:\Mathematics-Knowledge\Mathematics-Knowledge-code`:

```powershell
$source = 'C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\2025解题觉醒邓诚数学.md'
$before = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
python skills\mathos-formatting\scripts\mathos_formatting.py run $source --env 'C:\Mathematics-Knowledge\.env'
$after = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
if ($before -ne $after) { throw 'Source Markdown changed during formatting run' }
```

Expected: source hashes match. The command either exits `0` with `status: passed` or exits nonzero with one precise Stage 1 boundary artifact; it must not silently trim an overlong response.

- [ ] **Step 4: Read only the normal result digest**

Run:

```powershell
Get-Content -Raw -Encoding UTF8 -LiteralPath 'C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\2025解题觉醒邓诚数学\result-summary.json'
```

Expected on success: `status` is `passed`, `safe_to_approve` is `true`, and `source_unchanged` is `true`. On failure, read only the file named by `error_artifact` and report the remaining strict boundary failure.

- [ ] **Step 5: Inspect the final scoped diff**

Run:

```powershell
git diff --check -- skills/mathos-formatting/agents/toc_detection_prompt.md skills/mathos-formatting/scripts/step1_toc_extraction.py tests/test_mathos_formatting_guarded.py
git diff -- skills/mathos-formatting/agents/toc_detection_prompt.md skills/mathos-formatting/scripts/step1_toc_extraction.py tests/test_mathos_formatting_guarded.py
```

Expected: no whitespace errors; only the planned Stage 1 prompt, validator, and regression-test changes appear alongside clearly recognized pre-existing refactor changes.
