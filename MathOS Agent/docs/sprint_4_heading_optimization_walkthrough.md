# Sprint 4 Walkthrough: Heading Optimization Stage

This document outlines the implementation, testing, and validation of Stage 5 (Heading Optimization) for the `mathos-formatting` module.

## Summary of Accomplishments

1. **Heading Optimization Prompt**: Created a system prompt in `skills/mathos-formatting/agents/heading_optimization_prompt.md` to instruct the DeepSeek model on OCR correction (e.g. correcting `ϰο4` to `复习参考题 4`) and semantic refinement under strict heading level preservation constraints.
2. **Logic Implementation in Core**:
    - Implemented `run_heading_optimization` in `skills/mathos-formatting/scripts/mathos_formatting_core.py` to extract heading lines, call DeepSeek, parse the JSON response mapping, and validate that the heading levels (`#` counts) are preserved.
    - Integrated the heading optimization stage at the end of the learn-from-provider process.
    - Updated `apply_approved_program` to automatically replay the optimizations saved in `heading_optimizations.json` without executing another LLM call.
3. **CLI Controller Commands updated**:
    - Updated `command_approve` in `skills/mathos-formatting/scripts/mathos_formatting.py` to copy `heading_optimizations.json` to the approved program directory.
    - Updated `command_candidate_from_artifacts` and registered the new `--heading-optimizations` flag in `candidate_parser` to allow manually replaying optimization mappings.
4. **Unit and Integration Verification**:
    - Added unit tests for successful heading optimization mapping and level safety validation. All tests passed.
    - Successfully validated the entire flow end-to-end using a deterministic CLI integration script (`verify_cli.py`).

---

## Code Changes Details

### Added Files
- [NEW] [heading_optimization_prompt.md](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-formatting/agents/heading_optimization_prompt.md): System prompt for DeepSeek heading optimization.
- [NEW] [sprint_4_heading_optimization_task.md](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/docs/sprint_4_heading_optimization_task.md): Task checklist.
- [NEW] [sprint_4_heading_optimization_walkthrough.md](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/docs/sprint_4_heading_optimization_walkthrough.md): This walkthrough document.

### Modified Files
- [MODIFY] [mathos_formatting_core.py](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-formatting/scripts/mathos_formatting_core.py): Added helper function, integrated Stage 5, and updated the replay logic.
- [MODIFY] [mathos_formatting.py](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-formatting/scripts/mathos_formatting.py): Propagated optimizations in `approve` and `candidate-from-artifacts` CLI commands.
- [MODIFY] [test_mathos_formatting_guarded.py](file:///C:/Mathematics-Knowledge/Mathematics-Knowledge-code/tests/test_mathos_formatting_guarded.py): Added success and level-mismatch safety test cases.

---

## Verification and Testing Results

### 1. Unit Tests
All 68 unit tests passed successfully:
```powershell
============================= 68 passed in 0.81s ==============================
```

### 2. E2E Integration Flow Verification
We executed the CLI integration verification script `verify_cli.py` to validate:
- **Phase 1: Candidate Generation**: Successfully converted `## ϰο4` -> `## Review Exercise 4` using `--heading-optimizations` option.
- **Phase 2: Program Approval**: Successfully stored `heading_optimizations.json` in the approved directory.
- **Phase 3: Replay Local Optimization**: Successfully replayed the saved template during `apply-approved` to format `new_book.md` without invoking the DeepSeek API.

Resulting CLI stdout trace:
```json
ALL CLI INTEGRATION TESTS PASSED SUCCESSFULLY!
```
