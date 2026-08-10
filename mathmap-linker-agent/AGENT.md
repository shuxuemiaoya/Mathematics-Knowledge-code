---
name: mathmap-linker-agent
description: Safely integrate audited Book-to-Obsidian and Question Type Graph outputs into an existing, human-edited MathMap Obsidian vault.
---

# MathMap Linker Agent

Build a unified mathematics graph while treating the Obsidian vault as a mixed human-and-machine workspace.

## Operational contract

1. Preserve manual Obsidian edits. Update an existing file only when it still matches its bootstrapped or last-applied content hash.
2. Leave conflicted notes in place. Write proposals under `.mathmap-linker/review/<run-id>/`.
3. Use stable source provenance and the QID registry for identity. Do not derive identity from Git tracking state.
4. Run read-only by default. Require explicit `--apply` for vault mutations.
5. Back up every changed existing file before applying.
6. Rewrite only current-run assets and audit the changed subgraph before publication.
7. Keep Canvas updates separate, additive, and opt-in. Preserve all existing layout coordinates.

## Graph topology

- Tier 1: `mathmap/习题/questions/` embeds answers from `mathmap/习题/answers/`.
- Tier 2: `mathmap/习题/题型整理/` embeds questions or subordinate Tier-2 notes.
- Unresolved Tier 2: `mathmap/习题/题型整理/未链接题型/` holds new question-type nodes whose knowledge point requires review. These nodes remain valid Tier 2 but are never mounted automatically.
- Tier 3: `mathmap/习题/题集/` embeds Tier-2 notes and remains isolated by source/book.
- Formula hierarchy: `独立公式 → 公式整理 → 公式合集`.
- Knowledge points mount Tier-2/Tier-3 nodes under `# 题型` and formula nodes under `# 公式与结论`, grouped by `## 来源：<book_short>`.

## First-time migration

Inventory the legacy vault without modifying notes:

```bash
python3 scripts/bootstrap_registry.py <vault_root>
```

After reviewing the anomaly report, write only registry state:

```bash
python3 scripts/bootstrap_registry.py <vault_root> --write-registry --report bootstrap-report.json
```

Bootstrap records legacy baselines but never renames, moves, merges, or repairs notes automatically.

## Normal linking

Preview first:

```bash
python3 scripts/link_to_mathmap.py <vault_root> <source_book_dir> <book_short> \
  --dry-run --plan-out link-plan.json
```

Resolve conflicts and audit errors, then apply:

```bash
python3 scripts/link_to_mathmap.py <vault_root> <source_book_dir> <book_short> --apply
```

Unmatched knowledge points enter review by default. Use `--allow-create-knowledge-points` only after explicit user approval.
The dry-run summary reports `unlinked_question_types`, and apply creates the supported `未链接题型/` directory. Existing legacy notes are not moved automatically because that would invalidate human-authored Obsidian paths.

## Auditing and Canvas

```bash
python3 scripts/audit_mathmap.py <vault_root> --plan link-plan.json --fail-on-errors
python3 scripts/audit_mathmap.py <vault_root> --full --out full-audit.json
python3 scripts/update_canvas_additive.py <canvas> <additions.json>          # dry-run
python3 scripts/update_canvas_additive.py <canvas> <additions.json> --apply
```

Never globally reflow or delete Canvas nodes by default.
