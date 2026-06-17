# Approved Formatting Program Format

Approved programs live under `plugins/approved/<plugin-id>/`.

## New Python Artifact Format

Required files:

- `heading_processor.py`
- `content_processor.py`
- `metadata.json`
- `approval.md`
- `sample_before.md`
- `sample_after.md`

Optional file:

- `title_rewrite_map.py`

`heading_processor.py` is the Stage 1 batch processor. `content_processor.py` is the Stage 4 batch processor. Both are validated Python artifacts and are executed only against temporary sandbox copies of the candidate Markdown.

Stage 1 and Stage 4 processors must start with `import os`, import `Path` from `pathlib`, import `re`, and define `get_target_root()`, `protect_blocks()`, `restore_blocks()`, `replace_in_file()`, and `main()`.

`title_rewrite_map.py` is the Stage 5 artifact. It must define only `TITLE_REWRITE_MAP: dict[str, str]`, with Markdown heading-line keys and values.

## Metadata

`metadata.json` records:

- `plugin_id`
- `version`
- `artifact_mode`
- `approval_timestamp`
- `source_file_family_evidence`
- `heading_signature`
- `toc_signature`
- `h1_sample_hash`
- `operations_summary`
- `original_approving_file_path`
- `allowed_scope`

Newly approved programs start with `"allowed_scope": "self-check-only"` in `metadata.json`.

## Safety

Approved Python artifacts must not import or call network, subprocess, shell, deletion, move, rename, recursive copy, or arbitrary file-write APIs. Reuse must create a fresh candidate backup and self-check report. It must not modify the original Markdown file without a separate explicit user approval step outside this skill.

## Legacy Compatibility

Older approved directories may contain:

- `heading_rules.json`
- `content_rules.json`
- `content_cleaner.py`
- `heading_optimizations.json`

These legacy formats remain readable only for transition. New approved programs must use `heading_processor.py`, `content_processor.py`, and optional `title_rewrite_map.py`.
