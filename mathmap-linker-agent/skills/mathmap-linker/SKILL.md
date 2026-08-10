---
name: mathmap-linker
description: Safely link Question Type Graph or Book-to-Obsidian outputs into an existing MathMap Obsidian vault. Use when bootstrapping legacy MathMap identity registries, previewing or applying question/answer/type-set imports, protecting manual Obsidian edits, auditing MathMap tier topology, or additively updating the master Canvas.
---

# MathMap Linker

Treat the Obsidian vault as a mixed human-and-machine workspace. Preserve existing notes and user-arranged Canvas positions.

## Required workflow

1. Confirm that the input is an audited, immutable graph output rather than a temporary compilation directory.
2. If the vault has no `question-qid-registry.json` or `.mathmap-linker/provenance-manifest.json`, run the bootstrap scanner read-only:

   ```bash
   python3 scripts/bootstrap_registry.py <vault_root>
   ```

3. Review duplicate stems, QID collisions, misplaced answers, and legacy names. Write registry state only when the inventory is acceptable:

   ```bash
   python3 scripts/bootstrap_registry.py <vault_root> --write-registry --report bootstrap-report.json
   ```

   Bootstrap must never rename, merge, move, or edit existing notes.

4. Generate a dry-run plan. Dry-run is the default:

   ```bash
   python3 scripts/link_to_mathmap.py <vault_root> <source_book_dir> <book_short> \
     --dry-run --plan-out link-plan.json
   ```

5. Do not apply while the plan reports conflicts or audit errors. Review knowledge-point warnings rather than creating nodes automatically.
6. Apply only after reviewing the plan:

   ```bash
   python3 scripts/link_to_mathmap.py <vault_root> <source_book_dir> <book_short> --apply
   ```

7. Run a scoped or full audit as appropriate:

   ```bash
   python3 scripts/audit_mathmap.py <vault_root> --plan link-plan.json --fail-on-errors
   python3 scripts/audit_mathmap.py <vault_root> --full --out full-audit.json
   ```

## Safety rules

- Classify every source Markdown once. Give `answers`/`答案` precedence over an ancestor `questions` directory.
- Resolve identities through provenance records, not Git tracking state or basename alone.
- Preserve destination files that differ from their stored baseline. Leave the original in place and use `.mathmap-linker/review/<run-id>/` for the proposal.
- Rewrite only current-run assets. Never sweep and rewrite all historical destination notes.
- Enforce `question → answer`, `Tier 2 → question/Tier 2`, and `Tier 3 → Tier 2` in the changed subgraph.
- Keep knowledge-point mounts append-only and bounded to the correct Markdown heading.
- Do not create unmatched knowledge points unless the user explicitly authorizes `--allow-create-knowledge-points` after reviewing the mapping warning.
- Route new unmatched question-type nodes to `mathmap/习题/题型整理/未链接题型/`. Keep them as auditable Tier-2 nodes, preserve nested link paths, and do not mount them to a knowledge point until mapping is resolved.
- Never auto-move pre-existing Tier-2 notes into the unlinked folder. Report their legacy location and use a separate link-preserving migration when explicitly requested.
- Keep formula extraction virtual during planning; write it only through the same protected apply path.

## Canvas

Run `scripts/update_canvas_additive.py` only when the user explicitly requests Canvas changes. Dry-run first. Preserve all existing nodes, positions, dimensions, colors, and edges; add missing nodes into a collision-free local column. Never globally reflow or delete nodes by default.

Read [operations.md](references/operations.md) when resolving bootstrap anomalies, manual-edit conflicts, performance questions, or Canvas addition schemas.
