# MathOS Preheader TOC Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract complete contiguous TOCs whose earliest entries precede the first recognized TOC page header, while preserving strict preface and body rejection.

**Architecture:** Locate the first recognized TOC header as an internal anchor before validating lines. Permit earlier headings only when they lead to page-bearing TOC evidence before that anchor; retain the existing post-anchor state machine, verbatim checks, adjacency checks, and fail-closed behavior.

**Tech Stack:** Python 3, `re`, pytest, existing MathOS formatter provider client.

---

## File Map

- Modify `tests/test_mathos_formatting_guarded.py`: preheader acceptance, missing-anchor rejection, and prompt contract.
- Modify `skills/mathos-formatting/scripts/step1_toc_extraction.py`: internal anchor discovery and bounded preheader evidence checks.
- Modify `skills/mathos-formatting/agents/toc_detection_prompt.md`: earliest-entry and later-anchor provider instructions.

The code files share the active uncommitted formatter refactor. Do not stage them wholesale or create a mixed implementation commit. Preserve all pre-existing changes and inspect only the scoped behavior.

### Task 1: Add Failing Preheader TOC Tests

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py:1115-1180`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add an acceptance test for entries before an internal header**

Add after `test_validate_verbatim_toc_response_accepts_wrapped_entries_and_repeated_headers`:

```python
def test_validate_verbatim_toc_response_accepts_entries_before_internal_header():
    sample = (
        "1: # 专题一\n2: # 集合与逻辑\n3: 考点 1 集合的概念 007\n"
        "4: ![](images/toc-page.jpg)\n5: # 目录\n6: # CONTENTS\n"
        "7: 考点 2 集合间的基本关系 008\n8: \n9: # 正文\n"
    )
    response = "\n".join(sample.splitlines()[:7]) + "\n"

    toc = core.validate_verbatim_toc_response(sample, response)

    assert (toc.start_line, toc.end_line) == (1, 7)
    assert toc.markdown == (
        "# 专题一\n# 集合与逻辑\n考点 1 集合的概念 007\n"
        "# 目录\n# CONTENTS\n考点 2 集合间的基本关系 008\n"
    )
```

- [ ] **Step 2: Add a rejection test for a headerless span**

Add beside the acceptance test:

```python
def test_validate_verbatim_toc_response_rejects_headerless_toc_like_span():
    sample = "1: # 专题一\n2: 考点 1 集合的概念 007\n3: 考点 2 集合间的基本关系 008\n"

    with pytest.raises(core.FormattingError, match="recognized TOC heading anchor"):
        core.validate_verbatim_toc_response(sample, sample)
```

The existing unsafe-span case beginning with `# 数学` before `# 目录` remains the regression for preface rejection.

- [ ] **Step 3: Run the new validator tests and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "entries_before_internal_header or headerless_toc_like_span"
```

Expected: both tests fail because the current validator requires the first semantic response line to be a TOC header.

### Task 2: Add a Failing Prompt Contract Test

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py:1149-1158`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Extend the TOC prompt test**

Add to `test_toc_detection_prompt_explains_wrapped_entries_and_body_boundary`:

```python
    assert "Begin at the earliest TOC title or entry" in prompt
    assert "later internal `# 目录` or `# CONTENTS` anchor" in prompt
    assert "Do not prepend cover, preface, author, or date lines" in prompt
```

- [ ] **Step 2: Run the prompt test and verify RED**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py::test_toc_detection_prompt_explains_wrapped_entries_and_body_boundary -q
```

Expected: FAIL because the current prompt still requires the span to begin with the TOC header.

### Task 3: Implement Internal Anchor Validation

**Files:**
- Modify: `skills/mathos-formatting/scripts/step1_toc_extraction.py:66-165`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add first-anchor discovery**

Add before `validate_verbatim_toc_response`:

```python
def _first_toc_anchor_index(response_lines: list[tuple[int, str]]) -> int | None:
    for index, (_, line) in enumerate(response_lines):
        if TOC_HEADING_RE.match(line.strip()):
            return index
    return None
```

- [ ] **Step 2: Bound TOC evidence lookup before an anchor**

Add an optional exclusive stop to `_next_semantic_line`:

```python
def _next_semantic_line(
    response_lines: list[tuple[int, str]],
    start_index: int,
    stop_index: int | None = None,
) -> tuple[int, str] | None:
    end_index = len(response_lines) if stop_index is None else stop_index
    in_details = False
    for index in range(start_index, end_index):
        # Keep the existing blank, details, and image skipping logic unchanged.
```

Add the same optional stop to `_has_following_toc_evidence` and pass it through every `_next_semantic_line` call:

```python
def _has_following_toc_evidence(
    response_lines: list[tuple[int, str]],
    start_index: int,
    stop_index: int | None = None,
) -> bool:
```

When recursively advancing, preserve `stop_index`. A preheader heading can therefore prove itself only with evidence before the internal anchor, never by skipping across it.

- [ ] **Step 3: Require an internal anchor and validate the prefix**

After contiguous/verbatim validation, add:

```python
    first_anchor_index = _first_toc_anchor_index(response_lines)
    if first_anchor_index is None:
        raise FormattingError("TOC response must contain a recognized TOC heading anchor")
```

In the main loop, remove the special branch that requires `not toc_lines` to match `TOC_HEADING_RE`. For an ATX heading before the first anchor, require bounded evidence:

```python
        heading_match = ATX_HEADING_RE.match(line)
        if heading_match is not None:
            evidence_stop = first_anchor_index if index < first_anchor_index else None
            if not _has_toc_reference(line) and not _has_following_toc_evidence(
                response_lines, index + 1, evidence_stop
            ):
                raise FormattingError("TOC response contains unrelated body text in a heading")
```

For a non-heading wrapped prefix before the anchor, call `_next_semantic_line` with the same bounded stop. If the response's first semantic line is neither an ATX heading nor a page-bearing TOC line, reject it as unrelated preheader text rather than accepting it as a wrapped continuation.

Track this with:

```python
    seen_semantic_toc_line = False
```

Set it after accepting an ATX heading or `_looks_like_toc_line`. Permit a non-heading wrapped prefix only when `seen_semantic_toc_line` is already true.

- [ ] **Step 4: Run all TOC validator tests and verify GREEN**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "validate_verbatim_toc_response"
```

Expected: all TOC validator tests pass, including the existing unsafe `# 数学` prefix rejection.

### Task 4: Update the Provider Prompt

**Files:**
- Modify: `skills/mathos-formatting/agents/toc_detection_prompt.md:10-20`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Replace the first-line requirement**

Replace `Begin with the TOC heading` with:

```markdown
- Begin at the earliest TOC title or entry, even when the first recognized TOC page header appears later in the span.
- Include that later internal `# 目录` or `# CONTENTS` anchor unchanged; the complete span must contain at least one recognized TOC page header.
- Do not prepend cover, preface, author, or date lines before the earliest TOC title or entry.
```

Keep the existing verbatim, wrapped-entry, repeated-header, final-boundary, and no-rewrite rules.

- [ ] **Step 2: Run prompt and validator tests**

Run:

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "toc_detection_prompt or validate_verbatim_toc_response"
```

Expected: all selected tests pass.

### Task 5: Verify and Re-run the Real Formatter

**Files:**
- Verify: `skills/mathos-formatting/scripts/step1_toc_extraction.py`
- Verify: `skills/mathos-formatting/agents/toc_detection_prompt.md`
- Verify: `tests/test_mathos_formatting_guarded.py`
- Runtime artifacts: `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\2025解题觉醒邓诚数学\`

- [ ] **Step 1: Run syntax, guarded-suite, and CLI verification**

Run:

```powershell
python -m py_compile skills\mathos-formatting\scripts\step1_toc_extraction.py
python -m pytest tests\test_mathos_formatting_guarded.py -q
$env:PYTHONUTF8 = '1'
python skills\mathos-formatting\scripts\mathos_formatting.py --help
```

Expected: compilation succeeds, the guarded suite has zero failures, and CLI help exits `0`.

- [ ] **Step 2: Run the formatter with source hashing**

Run:

```powershell
$env:PYTHONUTF8 = '1'
$source = 'C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\2025解题觉醒邓诚数学.md'
$before = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
python skills\mathos-formatting\scripts\mathos_formatting.py run $source --env 'C:\Mathematics-Knowledge\.env'
$runExit = $LASTEXITCODE
$after = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
if ($before -ne $after) { throw 'Source Markdown changed during formatting run' }
exit $runExit
```

Expected: source hashes match. The immutable TOC begins at or before `# 2025 高考创新题觉醒速递` and contains topics one through four.

- [ ] **Step 3: Read only the compact result and routed error**

Read `result-summary.json`. On failure, read only its `error_artifact`.

Expected: Step 5 no longer reports topic-one-through-four H3 headings as absent from the TOC. Any remaining error must be a new, bounded, fail-closed issue.

- [ ] **Step 4: Inspect the scoped final diff**

Run:

```powershell
git diff --check -- skills/mathos-formatting/agents/toc_detection_prompt.md tests/test_mathos_formatting_guarded.py
git diff -- skills/mathos-formatting/agents/toc_detection_prompt.md tests/test_mathos_formatting_guarded.py
rg -n "first_toc_anchor|stop_index|recognized TOC heading anchor" skills\mathos-formatting\scripts\step1_toc_extraction.py
```

Expected: no whitespace errors; only the approved prompt, validator, and regression-test behavior is added alongside recognized pre-existing changes.
