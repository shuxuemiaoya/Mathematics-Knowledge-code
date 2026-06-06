# Approved Formatting Program Format

Approved programs live under `plugins/approved/<plugin-id>/`.

Required files:

- `heading_rules.json`
- `content_cleaner.py`
- `metadata.json`
- `approval.md`
- `sample_before.md`
- `sample_after.md`

`heading_rules.json` stores the validated regex rules used before plugin cleanup.

`content_cleaner.py` must expose `PLUGIN_ID`, `PLUGIN_VERSION`, `analyze(markdown)`, and `clean(markdown)`. The loader rejects unsafe imports, unsafe builtins access, environment access, and non-text plugin outputs.

`metadata.json` records:

- `plugin_id`
- `version`
- `approval_timestamp`
- `source_file_family_evidence`
- `heading_signature`
- `toc_signature`
- `h1_sample_hash`
- `operations_summary`
- `original_approving_file_path`
- `allowed_scope`

Newly approved programs start with `"allowed_scope": "manual-only"` in `metadata.json`.

Reuse must still create a fresh candidate backup and review report. It must not modify the original Markdown file without a separate user approval step outside this skill.
