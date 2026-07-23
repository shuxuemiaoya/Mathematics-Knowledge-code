# Pipeline State Schema

Use schema version `1` for `<folder>\tmp\organizer\<run-id>\pipeline-state.json`.

## Required top-level fields

```json
{
  "schema_version": 1,
  "run_id": "YYYYMMDDTHHMMSS",
  "folder": "C:\\absolute\\exam-folder",
  "stage_order": [
    "order",
    "convert",
    "question_only_bootstrap",
    "reformat",
    "supplement",
    "batch_clean_images",
    "pre_publish_audit",
    "render"
  ],
  "stages": {},
  "artifacts": [],
  "papers": [],
  "image_cleaning": {},
  "eligible_to_render": false,
  "publishing_complete": false
}
```

Use only `pending`, `in_progress`, `completed`, `not_applicable`, `failed`, `blocked`, `stale`, or `failed_visual_qa` for stage statuses.

## Reusable artifacts

Record every artifact required to reuse a completed stage:

```json
{
  "stage": "convert",
  "role": "markdown",
  "path": "C:\\absolute\\exam-folder\\paper.md",
  "sha256": "64 lowercase hexadecimal characters"
}
```

Keep artifact paths absolute and inside the resolved exam folder. A completed stage is reusable only when all of its required artifacts remain present with matching hashes.

## Question-only bootstrap

For each applicable paper, record:

- `answer_source_kind: "generated_bootstrap"`;
- generator model, temporary path, SHA-256 hash, question count, covered question IDs, and unresolved question IDs;
- `completed` only when every inventoried question is covered.

The bootstrap file belongs under the run directory and is provisional. It is an input to reformatting, not an authoritative user-supplied answer source.

## Image cleaning

When Batch Clean Images runs, record:

```json
{
  "image_replacement_status": "completed",
  "image_quality_status": "unverified",
  "backup_folder": "C:\\absolute\\exam-folder\\images\\original-images-backup-...",
  "replacements": [
    {
      "path": "C:\\absolute\\exam-folder\\images\\figure.png",
      "source_sha256": "original hash",
      "replacement_sha256": "current in-place hash"
    }
  ],
  "failed_paths": []
}
```

The backup must contain every original at its original relative path. `completed` proves the backup and writes succeeded. It does not prove image quality. Only rendered-page visual QA may change `image_quality_status` from `unverified` to `passed` or `failed`.

## Resume decision

Run `scripts/validate_pipeline_state.py` before reuse. Resume at the first stage that is absent, nonterminal, failed, blocked, stale, or whose required artifact no longer validates. Never combine run IDs or rerun a validated completed image-cleaning stage.

Set `eligible_to_render: true` only after all pre-publish dependencies pass. Set `publishing_complete: true` only after every selected final PDF passes page-by-page visual QA.
