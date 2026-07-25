---
name: book-graph-audit
description: Audit a Book to Obsidian Wiki Graph corpus against its per-book profile, frozen source digest, coverage and concept manifests, Markdown/link/asset rules, and optional canvas contract. Use as the mandatory pre-canvas and final gate, or to diagnose and resume an existing book conversion.
---

# Book Graph Audit

Own deterministic pass/fail reporting. Do not repair content or weaken a profile to make failures disappear.

## Inputs

Read `references/audit-contract.md`. Require the profile and frozen source identity. Accept coverage and concept manifests when those stages apply.

## Pre-Canvas Gate

```powershell
python scripts\audit_obsidian_graph.py "<book_root>" `
  --vault-root "<vault_root>" `
  --profile "<staging>\book-profile.json" `
  --coverage-manifest "<staging>\coverage-manifest.json" `
  --concept-manifest "<staging>\concept-manifest.json" `
  --source "<source>" `
  --expected-source-sha256 "<sha256>"
```

Require `status: passed` before canvas work.

## Final Gate

Add `--require-canvas` when the profile enables canvas:

```powershell
python scripts\audit_obsidian_graph.py "<book_root>" `
  --vault-root "<vault_root>" `
  --profile "<staging>\book-profile.json" `
  --coverage-manifest "<staging>\coverage-manifest.json" `
  --concept-manifest "<staging>\concept-manifest.json" `
  --source "<source>" `
  --expected-source-sha256 "<sha256>" `
  --require-canvas
```

## Report

Return one JSON report containing stage, status, errors, warnings, note/asset/category counts, coverage totals, concept-link counts, Markdown/Wikilink/image/callout counts, residual functional-block counts, canvas counts, and source-integrity status.

Treat skipped profile-disabled roles as valid; treat enabled roles and artifacts as required. Do not report overall completion unless the final required audit passes.
