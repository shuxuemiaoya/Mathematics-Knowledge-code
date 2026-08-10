---
name: mathmap-dedup
description: Analyze and safely deduplicate MathMap questions and problem-type notes. Use when previewing duplicate question stems, reusing canonical QIDs, merging Tier-2 question links within the same knowledge-point context, isolating Tier-3 sets, or investigating deduplication anomalies in an existing MathMap vault.
---

# MathMap Deduplication

Apply different identity rules by tier:

| Tier | Rule |
| --- | --- |
| Question | Reuse only when the normalized stem hash is identical. Preserve any textual, numeric, or symbolic difference. |
| Answer | Preserve source provenance and attach additional answers to the canonical question. |
| Tier 2 | Compare within the mapped knowledge-point context, select the highest score, and merge only missing embeds. |
| Tier 3 | Never semantically merge; preserve source/book isolation. |

Use the bootstrapped QID registry as the primary exact-question index. Fall back to scanning canonical `Q\d+.md` files only when no registry exists. Do not index answer-shaped or legacy-named files as questions.

Preview standalone deduplication analysis with:

```bash
python3 scripts/mathmap_dedup.py <vault_root> <source_book_dir> <book_short> --out dedup-plan.json
```

Treat fuzzy Tier-2 matches as proposals. The integrated linker protects the destination baseline and audits the resulting tier links before apply.
