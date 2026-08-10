# MathMap Linker Operations Reference

## Contents

1. State files
2. Legacy bootstrap
3. Manual-edit policy
4. Apply and backup behavior
5. Incremental performance
6. Unlinked question types
7. Canvas additions

## State files

`<vault>/question-qid-registry.json` records canonical QIDs and normalized-stem hashes.

`<vault>/.mathmap-linker/provenance-manifest.json` records:

- canonical source identity to destination path;
- the source hash used by the last apply;
- the destination hash after the last apply or bootstrap;
- node type, source book, and optional knowledge-point mounts.

Paths are relative to the vault. JSON is the portable phase-one contract. At larger scale, use SQLite as an operational cache and continue exporting compatible JSON snapshots.

## Legacy bootstrap

Bootstrap adopts existing files without deciding ambiguous merges. It reports:

- answer-shaped files under `questions/`;
- noncanonical question filenames;
- unreadable notes;
- duplicate normalized stems.

Treat duplicate normalized stems as review candidates. Do not delete or redirect them automatically. A later migration may select a canonical QID and record aliases after human review.

## Manual-edit policy

Use destination content hashes as the authority. Use size and `mtime_ns` only to skip unnecessary rehashing.

| Destination state | Proposed state | Behavior |
| --- | --- | --- |
| Missing | New | Create |
| Matches baseline | Different | Back up and update |
| Differs from baseline | Different | Leave unchanged and create review proposal |
| Unknown legacy file | Different | Leave unchanged and require bootstrap/review |
| Any | Identical | Treat as unchanged and adopt safely |

Never move an existing conflicted note out of the vault. Moving it would break Obsidian links.

## Apply and backup behavior

Apply writes only plan-scoped files. Before updating an existing file, copy it to:

```text
<vault>/.mathmap-linker/backups/<run-id>/<vault-relative-path>
```

Each destination is replaced atomically, but the linker does not claim whole-vault transactional rollback. Restore individual files from the backup if a later operational check fails.

## Incremental performance

When registries exist, question matching uses normalized-stem hashes instead of rereading every question. Bootstrap fingerprints use `size + mtime_ns` as a fast path and SHA-256 as the identity.

Normal imports audit only the changed subgraph. Run `audit_mathmap.py --full` as an explicit maintenance operation. The full audit streams files one at a time and does not build a full Markdown AST in memory.

For 50,000+ questions or 100,000+ answers, add a SQLite cache keyed by path, size, mtime, content hash, normalized-stem hash, node type, and knowledge-point ID. Keep the JSON registry as an export format.

## Unlinked question types

The supported quarantine directory is:

```text
<vault>/mathmap/习题/题型整理/未链接题型/
```

Dry-run reports unresolved Tier-2 assets through `summary.unlinked_question_types` and a `knowledge_point_review` warning containing `quarantined` and `unlinked_question_type_folder` fields. Apply creates the directory and writes only new unmatched Tier-2 assets there. Tier-3 references must include the nested `未链接题型/` path.

Bootstrap and full audit scan this Tier-2 subtree recursively. Semantic deduplication does not treat quarantined nodes as linked candidates. If a pre-existing source identity already points to a flat Tier-2 path, retain that path and report it as unresolved; do not move it automatically.

## Canvas additions

Use an additions JSON file:

```json
{
  "nodes": [
    {
      "key": "mathmap/习题/题型整理/集合判断",
      "file": "mathmap/习题/题型整理/集合判断.md",
      "parent_key": "mathmap/知识点/集合的概念",
      "width": 400,
      "height": 240,
      "color": "6"
    }
  ],
  "edges": [
    {
      "from_key": "mathmap/知识点/集合的概念",
      "to_key": "mathmap/习题/题型整理/集合判断",
      "label": "题型"
    }
  ]
}
```

Preview and apply:

```bash
python3 scripts/update_canvas_additive.py mathmap题型.canvas additions.json
python3 scripts/update_canvas_additive.py mathmap题型.canvas additions.json --apply
```

The updater preserves existing coordinates and uses a sidecar mapping for stable node IDs. It places only new nodes and backs up the Canvas before applying.
