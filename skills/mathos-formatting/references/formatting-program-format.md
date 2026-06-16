# Approved Formatting Program Format

Approved programs live under `plugins/approved/<plugin-id>/`.

Required files:

- `heading_rules.json`
- `content_rules.json`
- `metadata.json`
- `approval.md`
- `sample_before.md`
- `sample_after.md`

`heading_rules.json` stores the validated regex rules used before plugin cleanup.

`content_rules.json` stores the validated JSON chapter-inner formatting rule package generated for Stage 4. It must include `plugin_id`, `plugin_version`, `schema_version`, `stage`, `safety`, `execution_contract`, `protected_blocks`, `analyze.checks`, `rules`, `warnings`, and `summary`.

The JSON executor supports safe enabled v1 rule types: `literal_replace`, `regex_replace`, `line_regex_replace`, `blank_line_normalize`, `choice_option_split`, `callout_spacing_fix`, and `formula_whitelist_fix`. `report_only` rules are analysis-only. Enabled mutating `image_caption_fix` rules are rejected in v1 unless disabled or represented as report-only guidance.

The executor always preserves heading lines, fenced code blocks, math blocks, HTML details blocks, YAML frontmatter, and markdown table blocks. It also fails closed if image count decreases, details count decreases, math delimiter count changes, table-like line count decreases, or heading lines change.

Legacy approved directories may contain `content_cleaner.py` instead of `content_rules.json`. Those Python cleaners remain readable for backward compatibility, but new approved templates should store `content_rules.json`.

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

Newly approved programs start with `"allowed_scope": "self-check-only"` in `metadata.json`.

Reuse must still create a fresh candidate backup and self-check report. It must not modify the original Markdown file without a separate user approval step outside this skill.
