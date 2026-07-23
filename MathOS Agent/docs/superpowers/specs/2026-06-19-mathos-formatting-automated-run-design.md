# MathOS Formatting Automated Run Design

## Goal

Add one `run` command that executes provider learning, recovery, deterministic self-checking, and final judgment, then writes one compact `result-summary.json` for Codex.

## Architecture

The new `automation_runner.py` wraps the existing six-step `learning_pipeline.py`; it does not duplicate formatting behavior. It records an execution fingerprint derived from the source, prompts, provider identity, and runtime options. Matching fingerprints may reuse validated generated processors already supported by the pipeline. A mismatch removes only generated reusable processors from that work directory before running again.

## Result Contract

Every run writes `<work-dir>/result-summary.json`. Success contains `status: passed`, deterministic source/preservation checks, candidate and report paths, `safe_to_approve: true`, and no error artifact. Failure contains `status: failed`, `failed_stage`, one `error_artifact`, errors, and `safe_to_approve: false`. The CLI prints only this digest and returns nonzero on failure.

## Recovery

The runner writes `automation-checkpoint.json` with the execution fingerprint. On a retry with the same fingerprint, existing validated `heading_processor.py` and `content_processor.py` may be reused by the existing step modules. Provider-dependent validation still runs fail-closed. A changed fingerprint invalidates reusable processors so stale generated code cannot cross source or configuration boundaries.

## Self-Check

Python verifies that the source bytes did not change, the candidate and report exist, Stage 1 passed, the candidate is plausibly sized, headings remain present, and protected-region counts satisfy existing preservation gates. These checks determine `safe_to_approve`; Codex does not inspect the full candidate during normal success.

## Failure Routing

The runner maps each `failed_stage` to one most relevant saved artifact. When no stage artifact exists, it points to `run-state.json`. This gives Codex exactly one diagnostic file to read.

## Compatibility

Existing `inspect`, `learn-from-provider`, `candidate-from-artifacts`, `approve`, and `apply-approved` commands remain unchanged. The source Markdown is never replaced.
