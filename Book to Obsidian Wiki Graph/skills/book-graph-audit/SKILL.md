---
name: book-graph-audit
description: Audit a Book to Obsidian Wiki Graph corpus against its per-book profile, frozen source digest, coverage and concept manifests, Markdown/link/asset rules, and optional canvas contract. Use for progressive split, concept, formatting, pre-canvas, and final gates, or to diagnose and resume an existing book conversion.
---

# Book Graph Audit

Own deterministic pass/fail reporting. Do not repair content or weaken a profile to make failures disappear.

## Inputs

Read `references/audit-contract.md`. Require the profile and frozen source identity. Accept coverage and concept manifests when those stages apply.

## Progressive Gates

Run the earliest applicable gate and stop immediately on failure:

```powershell
python scripts\audit_obsidian_graph.py "<book_root>" `
  --vault-root "<vault_root>" `
  --profile "<staging>\book-profile.json" `
  --coverage-manifest "<staging>\coverage-manifest.json" `
  --lesson-flow-manifest "<staging>\lesson-flow-manifest.json" `
  --source "<source>" `
  --expected-source-sha256 "<sha256>" `
  --stage split
```

After concept extraction, add the concept manifest and use `--stage concepts`.
After Markdown standardization, use `--stage formatting`.

## Pre-Canvas Gate

```powershell
python scripts\audit_obsidian_graph.py "<book_root>" `
  --vault-root "<vault_root>" `
  --profile "<staging>\book-profile.json" `
  --coverage-manifest "<staging>\coverage-manifest.json" `
  --concept-manifest "<staging>\concept-manifest.json" `
  --source "<source>" `
  --expected-source-sha256 "<sha256>" `
  --stage pre-canvas
```

Require `status: passed` before canvas work.

At every gate, require each non-concept note to begin with one valid H1-H3
entry heading. From the concept gate onward, require every concept note to
begin with `# <filename stem>` and contain `## 定义`. When
`links.note_mode` is `vault-root`, require internal Markdown note links to use
leading-slash vault-root destinations.

## Final Gate

The final stage automatically requires a canvas when the profile enables one:

```powershell
python scripts\audit_obsidian_graph.py "<book_root>" `
  --vault-root "<vault_root>" `
  --profile "<staging>\book-profile.json" `
  --coverage-manifest "<staging>\coverage-manifest.json" `
  --concept-manifest "<staging>\concept-manifest.json" `
  --source "<source>" `
  --expected-source-sha256 "<sha256>" `
  --stage final
```

## Report

Return one JSON report containing schema version, stage, status, profile and
source identity, errors, warnings, note/asset/category counts, coverage totals,
concept-link counts, Markdown/Wikilink/image/callout counts, residual
functional-block counts, quoted-body callout continuity violations, callout
semantic-scope violations, canvas counts, and source-integrity status.
For new textbook profiles, validate the same lesson-flow manifest at every
gate. Reject missing lessons, unclassified or discontinuous ranges, moved
context/transitions, uncovered direct children, link-only lesson entries, and
oversized retained teaching blocks.
From the formatting gate onward, also report and reject plain running chapter
headers, OCR-split digit groups inside TeX spans, and HTML tables with
unbalanced tags, TeX delimiters, or braces. These are review blockers; the
audit must not guess mathematical corrections.
Also reject unbalanced parentheses in formal definitions, numbered solution
subparts absent from their example stem, and explicit reasoning labels
flattened at the parent callout depth. Review the frozen source or approved
reference instead of inventing missing mathematics.
From the formatting gate onward, reconstruct every top-level callout's quoted
body and reject functional headings, duplicate source labels, or practice
blocks inside it. Reject formal definitions inside situation callouts, worked
examples inside non-example callouts, and a later example nested under an
earlier example.

Treat skipped profile-disabled roles as valid; treat enabled roles and artifacts as required. Do not report overall completion unless the final required audit passes.
