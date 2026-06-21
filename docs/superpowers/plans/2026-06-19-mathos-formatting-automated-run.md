# MathOS Formatting Automated Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single fail-closed `run` command that writes one compact success or failure digest.

**Architecture:** A focused automation runner wraps the existing learning pipeline, fingerprints resumable inputs, performs deterministic post-run checks, and routes failures to one artifact. The CLI only loads provider settings, invokes the runner, and prints its digest.

**Tech Stack:** Python 3, argparse, dataclasses, JSON, SHA-256, pytest

---

### Task 1: Define and test the automation result contract

**Files:**
- Create: `skills/mathos-formatting/scripts/automation_runner.py`
- Modify: `tests/test_mathos_formatting_guarded.py`

- [ ] Write failing tests for a successful digest, unchanged source, deterministic self-checks, and a failed digest with one stage-specific artifact.
- [ ] Run the focused tests and confirm they fail because `automation_runner.py` is absent.
- [ ] Implement result serialization, fingerprinting, self-checking, recovery invalidation, and failure routing.
- [ ] Run focused tests and confirm they pass.

### Task 2: Add and test the CLI command

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Modify: `tests/test_mathos_formatting_guarded.py`

- [ ] Write a failing parser/CLI test for `run <markdown> --env <env>` and compact JSON output.
- [ ] Run the test and confirm `run` is not recognized.
- [ ] Add `command_run` and parser arguments without changing existing commands.
- [ ] Run the focused CLI tests and confirm they pass.

### Task 3: Align the operator contract and verify

**Files:**
- Modify: `skills/mathos-formatting/SKILL.md`

- [ ] Document the `run` command, `result-summary.json`, recovery fingerprint, and failure-directed inspection contract.
- [ ] Run `python -m pytest tests/test_mathos_formatting_guarded.py -q`.
- [ ] Run `python skills/mathos-formatting/scripts/mathos_formatting.py --help` and `run --help`.
- [ ] Run `python -m py_compile` on the new and modified scripts.
