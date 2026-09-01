# Runtime Contract

Use `scripts/pipeline_runtime.py` as the durable control plane for one book
conversion. Component skills still perform the work.

## One-Run State

Initialize after intake:

```powershell
python scripts/pipeline_runtime.py init <book-profile.json>
```

The default state is `<staging_root>/pipeline-state.json`. It records the frozen
profile and source digests, stage status, attempts, input/output hashes,
durations, failures, review counts, and the next valid stage.

Without a test-options file, this state supports same-run recovery only. It
must not discover, reuse, or cache artifacts from another book.

## Optional Test Checkpoints

For repeated tests of the same frozen source, place
`book-graph-test-options.json` at `paths.vault_root`:

```json
{
  "schema_version": 1,
  "preserve_stage_artifacts": true
}
```

`init` auto-discovers this file. You may instead pass
`--test-options <path>`. When `preserve_stage_artifacts` is `false`, or when
the file is absent, checkpoint behavior is disabled and the existing
final-result-only cleanup policy remains unchanged.

When enabled, `init` freezes the intake checkpoint and every successful
`complete` freezes another checkpoint under:

```text
<vault_root>/.book-graph-checkpoints/<book-title>/
  <run-id>/
    01-intake/attempt-01/
    02-pdf-conversion/attempt-01/
    03-toc-formatting/attempt-01/
    ...
```

Every test initialization receives a new `<run-id>`, so repeated tests never
overwrite earlier checkpoints. Each stage folder is self-contained: it stores
the corpus tree as it existed at that stage, all completed handoff artifacts
required to reach that stage, `pipeline-state.json`, and
`checkpoint-manifest.json`. Directory artifacts are stored as ZIP snapshots
with short checkpoint names so deep textbook asset paths remain portable on
Windows. A configured
`checkpoint_root` may be absolute or relative to the options file, but must
remain outside both staging and the final book tree.

To resume after ordinary test cleanup removed staging or the current output:

```powershell
python scripts/pipeline_runtime.py restore-checkpoint `
  "<checkpoint>\checkpoint-manifest.json"
```

The restore refuses changed existing targets. Use `--overwrite` only after
checking those exact frozen staging/book targets. After restoration, read
`next_stage` from stdout and continue with the ordinary `begin` / `complete`
lifecycle.

A checkpoint is not a general cache. Restore validates the original source
path and SHA-256, the options-file digest, every stored artifact, the stored
state, and the frozen staging/book roots. It cannot be applied to a different
book, source revision, profile, or output location.

If stage work completed but checkpoint persistence was interrupted, retry only
the checkpoint without rerunning the component:

```powershell
python scripts/pipeline_runtime.py checkpoint <state> <completed-stage>
```

## Stage Lifecycle

Before a stage:

```powershell
python scripts/pipeline_runtime.py begin <state> <stage> --input <kind>=<path>
```

For a permanent apply wrapper that also records launch/exit failures:

```powershell
python scripts/pipeline_runtime.py apply <state> <stage> `
  --input <kind>=<path> --command python <component-script> <arguments>
```

`apply` runs the component without a shell, captures its UTF-8 stdout/stderr,
and leaves a successful stage in `running` until its outputs are validated by
`complete`.

After a successful component and its checks:

```powershell
python scripts/pipeline_runtime.py complete <state> <stage> `
  --artifact <kind>=<path> --report <kind>=<path> `
  --review-queue <review-queue.json>
```

On failure:

```powershell
python scripts/pipeline_runtime.py fail <state> <stage> `
  --message "<short cause>" --error-artifact <path>
```

Use `plan` for the next stage and `resume` after interruption. Both re-hash
recorded artifacts. A changed output invalidates that stage and all downstream
stages, without discarding earlier valid work.

## Strict Handoffs

`validate <kind> <path>` supports:

- `book-profile`, `toc-manifest`, `toc-format-report`;
- `split-manifest`, `lesson-flow-manifest`, `coverage-manifest`,
  `concept-manifest`;
- `markdown-report`, `graph-manifest`, `audit-report`,
  `reference-parity-report`, `canvas-style-report`;
- `review-queue`, `note-workplan`, `note-results`;
- generic `file`, mutable `directory`, and immutable `tree`.

Structured artifacts must have their required fields, a resolving absolute
profile path, and the frozen source digest. Status reports must pass. The
runtime rejects malformed concept entries, duplicate targets or source keys,
bad coverage states, invalid graph references, unresolved review queues, and
identity mismatches.

For a same-book reference, split-manifest validation also requires a passed,
reviewer-confirmed `semantic_review.reference` bound to the profile path/tree
digest and to an existing proposal report with the recorded SHA-256. Adding or
changing that reference after splitting is input drift: initialize the revised
profile and resume from the split draft, not from the prior lesson flow or any
downstream checkpoint.

For a textbook profile with
`decomposition.require_textbook_node_architecture: true`, split-manifest
validation additionally requires a passed whole-book `node_architecture`
review, source-content/name preservation, recursive source-order expansion,
physical owner-folder hierarchy, and reviewed `node_type`/`organizer_type`
fields. A draft marked
`review_required` cannot complete the split stage.

Stage completion also requires the artifact set owned by that stage:

| Stage | Required output kinds |
| --- | --- |
| PDF conversion / Markdown registration | `file` |
| TOC formatting | `file`, `toc-manifest`, `toc-format-report` |
| TOC splitting | `directory`, `split-manifest`, `lesson-flow-manifest` when enabled, `coverage-manifest`, split `audit-report` |
| Concepts | `concept-manifest` when enabled, concepts `audit-report` |
| Markdown standardization | `markdown-report`, formatting `audit-report` |
| Pre-canvas audit | pre-canvas `audit-report` |
| Canvas | `file`, `graph-manifest`, plus `canvas-style-report` when `canvas.style_reference` is configured |
| Final audit | final `audit-report`, final corpus `tree`, plus `reference-parity-report` when the profile freezes a reference |

Passing a failed report as a generic output does not bypass the gate.
The reference report must resolve to the exact profile-bound reference path
and digest. A style or content review status other than `passed` blocks
completion.
The Canvas style report must resolve to the exact profile-bound sibling Canvas
path and digest, and its candidate path/digest must match the declared Canvas
file output. `style_review_required` blocks Canvas-stage completion.
`directory` verifies that a shared corpus exists but permits expected downstream
edits. `tree` records a complete directory digest and is reserved for the final
corpus snapshot so resume detects post-completion drift.

## Confidence Review

Build a queue from a JSON candidate list:

```powershell
python scripts/pipeline_runtime.py make-review-queue <candidates.json> `
  --profile <book-profile.json> --output <review-queue.json>
```

Each candidate needs `id`, `stage`, `kind`, `source`, `proposal`, and
`confidence`. Candidates below the threshold, or marked ambiguous, unresolved,
or conflicting, receive `route: needs_review`; the rest receive
`route: auto_ready`.

A reviewed item must have `decision: accepted`, `revised`, or `rejected`;
`revised` also needs `resolution`. `complete --review-queue` blocks while any
`needs_review` item remains undecided.

Record a decision without hand-editing queue counters:

```powershell
python scripts/pipeline_runtime.py decide-review <review-queue.json> `
  <item-id> accepted

python scripts/pipeline_runtime.py decide-review <review-queue.json> `
  <item-id> revised --resolution "<corrected decision>"
```

## Safe Note-Level Work

Create a frozen, balanced workplan:

```powershell
python scripts/pipeline_runtime.py partition-notes <book-profile.json> `
  --workers 4 --roles knowledge,exercise `
  --tasks concept-extraction,markdown-standardization `
  --output <note-workplan.json>
```

Every note is hashed and assigned to one lane and one owner. A result file must
name its `job_id`, repeat that note digest as `source_sha256`, declare
`status`, and list owned `outputs`. Merge only after every expected result is
present:

```powershell
python scripts/pipeline_runtime.py merge-note-results <workplan> <result-dir> `
  --output <note-results.json>
```

Merge fails on changed source notes, missing or duplicate jobs, unknown jobs,
or duplicate output ownership.

## Progressive Gates

Run `book-graph-audit` with:

- `--stage split` after splitting;
- `--stage concepts` after concept extraction;
- `--stage formatting` after Markdown standardization;
- `--stage pre-canvas` before canvas planning;
- `--stage final` after the optional canvas.

The early gates permit transformations that belong to later stages but still
enforce all invariants already due. The final gate requires a canvas when the
profile enables one.
