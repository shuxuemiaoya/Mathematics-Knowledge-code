# MathOS Step-Prefixed Prompt Names Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename every formatter prompt source and every newly written prompt-copy artifact so the owning workflow step is visible in the filename.

**Architecture:** Rename the six prompt sources in place, then update only their direct runtime and test references. Keep artifact dictionary keys, provider response names, processors, recovery schema, and historical work directories unchanged.

**Tech Stack:** Python 3, pathlib, pytest, Git file moves, existing MathOS formatter CLI.

---

## File Map

- Rename six files under `skills/mathos-formatting/agents/` according to the approved mapping.
- Modify `skills/mathos-formatting/scripts/mathos_formatting.py`: load Step 3 and Step 6 prompts by new source names.
- Modify `skills/mathos-formatting/scripts/step1_toc_extraction.py`: Step 1 source lookup and prompt-copy artifact.
- Modify `skills/mathos-formatting/scripts/step3_heading_processing.py`: Step 3 expected-result source lookup and processor prompt-copy artifact.
- Modify `skills/mathos-formatting/scripts/step5_heading_validation.py`: Step 5 source lookup and prompt-copy artifact.
- Modify `skills/mathos-formatting/scripts/step6_content_processing.py`: Step 6 prompt-copy artifact.
- Modify `tests/test_mathos_formatting_guarded.py`: source-name and run-artifact regressions.
- Modify `skills/mathos-formatting/SKILL.md`: canonical artifact layout.

The worktree contains user-owned changes. Preserve them and leave implementation changes uncommitted unless the user separately requests a commit.

### Task 1: Lock the Source Filename Contract

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add a failing source filename test**

Add near `test_current_workflow_uses_one_clearly_named_module_per_step`:

```python
def test_prompt_sources_use_step_prefixed_filenames():
    agents = SKILL_ROOT / "agents"
    expected = {
        "step1_toc_detection_prompt.md",
        "step3_heading_processor_prompt.md",
        "step3_heading_expected_result_prompt.md",
        "step5_heading_validation_prompt.md",
        "step6_content_processor_prompt.md",
        "legacy_heading_optimization_prompt.md",
    }
    superseded = {
        "toc_detection_prompt.md",
        "heading_rules_prompt.md",
        "heading_expected_result_prompt.md",
        "heading_check_prompt.md",
        "content_cleaner_prompt.md",
        "heading_optimization_prompt.md",
    }

    actual = {path.name for path in agents.glob("*_prompt.md")}
    assert expected <= actual
    assert superseded.isdisjoint(actual)
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py::test_prompt_sources_use_step_prefixed_filenames -q
```

Expected: FAIL because all six sources still use the superseded filenames.

### Task 2: Rename Prompt Sources and Runtime References

**Files:**
- Rename: `skills/mathos-formatting/agents/toc_detection_prompt.md` to `skills/mathos-formatting/agents/step1_toc_detection_prompt.md`
- Rename: `skills/mathos-formatting/agents/heading_rules_prompt.md` to `skills/mathos-formatting/agents/step3_heading_processor_prompt.md`
- Rename: `skills/mathos-formatting/agents/heading_expected_result_prompt.md` to `skills/mathos-formatting/agents/step3_heading_expected_result_prompt.md`
- Rename: `skills/mathos-formatting/agents/heading_check_prompt.md` to `skills/mathos-formatting/agents/step5_heading_validation_prompt.md`
- Rename: `skills/mathos-formatting/agents/content_cleaner_prompt.md` to `skills/mathos-formatting/agents/step6_content_processor_prompt.md`
- Rename: `skills/mathos-formatting/agents/heading_optimization_prompt.md` to `skills/mathos-formatting/agents/legacy_heading_optimization_prompt.md`
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Modify: `skills/mathos-formatting/scripts/step1_toc_extraction.py`
- Modify: `skills/mathos-formatting/scripts/step3_heading_processing.py`
- Modify: `skills/mathos-formatting/scripts/step5_heading_validation.py`
- Modify: `skills/mathos-formatting/scripts/step6_content_processing.py`
- Modify: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Rename all six source files without changing content**

```powershell
git mv skills/mathos-formatting/agents/toc_detection_prompt.md skills/mathos-formatting/agents/step1_toc_detection_prompt.md
git mv skills/mathos-formatting/agents/heading_rules_prompt.md skills/mathos-formatting/agents/step3_heading_processor_prompt.md
git mv skills/mathos-formatting/agents/heading_expected_result_prompt.md skills/mathos-formatting/agents/step3_heading_expected_result_prompt.md
git mv skills/mathos-formatting/agents/heading_check_prompt.md skills/mathos-formatting/agents/step5_heading_validation_prompt.md
git mv skills/mathos-formatting/agents/content_cleaner_prompt.md skills/mathos-formatting/agents/step6_content_processor_prompt.md
git mv skills/mathos-formatting/agents/heading_optimization_prompt.md skills/mathos-formatting/agents/legacy_heading_optimization_prompt.md
```

- [ ] **Step 2: Update source lookups and prompt-copy artifact paths**

Apply these exact substitutions in active runtime files:

```text
mathos_formatting.py:
  heading_rules_prompt.md -> step3_heading_processor_prompt.md
  content_cleaner_prompt.md -> step6_content_processor_prompt.md

step1_toc_extraction.py:
  agents/toc_detection_prompt.md -> agents/step1_toc_detection_prompt.md
  work_dir/toc_detection_prompt.md -> work_dir/step1_toc_detection_prompt.md

step3_heading_processing.py:
  agents/heading_expected_result_prompt.md -> agents/step3_heading_expected_result_prompt.md
  work_dir/heading_processor_prompt.md -> work_dir/step3_heading_processor_prompt.md

step5_heading_validation.py:
  agents/heading_check_prompt.md -> agents/step5_heading_validation_prompt.md
  work_dir/heading_check_prompt.md -> work_dir/step5_heading_validation_prompt.md

step6_content_processing.py:
  work_dir/content_cleaner_prompt.md -> work_dir/step6_content_processor_prompt.md
```

Keep artifact dictionary keys such as `heading_prompt`, `content_prompt`, and `heading_check_prompt` unchanged.

- [ ] **Step 3: Update tests that read prompt sources**

Replace direct test lookups with the approved source names:

```text
content_cleaner_prompt.md -> step6_content_processor_prompt.md
heading_rules_prompt.md -> step3_heading_processor_prompt.md
toc_detection_prompt.md -> step1_toc_detection_prompt.md
heading_check_prompt.md -> step5_heading_validation_prompt.md
```

Do not replace the superseded-name strings inside `test_prompt_sources_use_step_prefixed_filenames`; they are intentional negative assertions.

- [ ] **Step 4: Run the source-name test and prompt-content tests**

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "prompt_sources_use_step_prefixed or prompt_forbids or toc_detection_prompt or heading_check_prompt"
```

Expected: all selected tests pass.

### Task 3: Lock the New Run-Artifact Names

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py`
- Test: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Extend the successful provider-run artifact test**

In `test_learning_uses_new_stage1_provider_order_and_artifacts`, add:

```python
    expected_prompt_artifacts = {
        "step1_toc_detection_prompt.md",
        "step3_heading_processor_prompt.md",
        "step5_heading_validation_prompt.md",
        "step6_content_processor_prompt.md",
    }
    superseded_prompt_artifacts = {
        "toc_detection_prompt.md",
        "heading_processor_prompt.md",
        "heading_check_prompt.md",
        "content_cleaner_prompt.md",
    }
    work_files = {path.name for path in work_dir.iterdir() if path.is_file()}
    assert expected_prompt_artifacts <= work_files
    assert superseded_prompt_artifacts.isdisjoint(work_files)
    assert "step3_heading_expected_result_prompt.md" not in work_files
```

- [ ] **Step 2: Update the direct Step 3 no-extra-artifact assertion**

In `test_step3_writes_expected_result_from_same_payload_without_extra_work_artifacts`, assert:

```python
    assert not (work_dir / "step3_heading_expected_result_prompt.md").exists()
    assert not (work_dir / "heading_expected_result_response.md").exists()
```

Remove the obsolete assertion for `heading_expected_result_prompt.md` because the source-name contract test now covers that superseded source filename.

- [ ] **Step 3: Run the artifact tests**

```powershell
python -m pytest tests\test_mathos_formatting_guarded.py -q -k "new_stage1_provider_order_and_artifacts or writes_expected_result_from_same_payload"
```

Expected: both tests pass and confirm that no extra Step 3 prompt copy exists.

### Task 4: Update Documentation and Verify

**Files:**
- Modify: `skills/mathos-formatting/SKILL.md`
- Verify: all renamed and modified files.

- [ ] **Step 1: Replace prompt names in Artifact Layout**

Use this prompt subset:

```markdown
- `step1_toc_detection_prompt.md`
- `step3_heading_processor_prompt.md`
- `step5_heading_validation_prompt.md`
- `step6_content_processor_prompt.md`
```

Do not add `step3_heading_expected_result_prompt.md` to the run Artifact Layout because it remains a repository source only.

- [ ] **Step 2: Run complete verification**

```powershell
python -m py_compile skills\mathos-formatting\scripts\mathos_formatting.py skills\mathos-formatting\scripts\step1_toc_extraction.py skills\mathos-formatting\scripts\step3_heading_processing.py skills\mathos-formatting\scripts\step5_heading_validation.py skills\mathos-formatting\scripts\step6_content_processing.py
python -m pytest tests\test_mathos_formatting_guarded.py -q
$env:PYTHONUTF8 = '1'
python skills\mathos-formatting\scripts\mathos_formatting.py --help
git diff --check -- skills/mathos-formatting/SKILL.md skills/mathos-formatting/agents skills/mathos-formatting/scripts/mathos_formatting.py skills/mathos-formatting/scripts/step1_toc_extraction.py skills/mathos-formatting/scripts/step3_heading_processing.py skills/mathos-formatting/scripts/step5_heading_validation.py skills/mathos-formatting/scripts/step6_content_processing.py tests/test_mathos_formatting_guarded.py
```

Expected: compilation succeeds, the full guarded suite has zero failures, CLI exits `0`, and the scoped diff has no whitespace errors.

- [ ] **Step 3: Inspect remaining superseded references**

```powershell
rg -n "toc_detection_prompt\.md|heading_rules_prompt\.md|heading_expected_result_prompt\.md|heading_check_prompt\.md|content_cleaner_prompt\.md|heading_optimization_prompt\.md|heading_processor_prompt\.md" skills\mathos-formatting tests\test_mathos_formatting_guarded.py
```

Expected: superseded names appear only in the intentional negative filename and run-artifact assertions, plus historical prose outside the active runtime contract if any.
