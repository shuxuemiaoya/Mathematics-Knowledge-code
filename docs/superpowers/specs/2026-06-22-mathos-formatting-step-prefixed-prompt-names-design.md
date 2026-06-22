# MathOS Step-Prefixed Prompt Names Design

## Goal

Rename every MathOS formatter prompt file so its filename identifies the owning workflow step. Apply the same naming convention to prompt copies written into new run directories.

## Naming Convention

Use `stepN_<purpose>_prompt.md` for prompts owned by the current six-step workflow. Use `legacy_<purpose>_prompt.md` for compatibility-only prompts that are not owned by a current step.

## Source Prompt Renames

| Current name | New name | Owner |
| --- | --- | --- |
| `toc_detection_prompt.md` | `step1_toc_detection_prompt.md` | Step 1 TOC extraction |
| `heading_rules_prompt.md` | `step3_heading_processor_prompt.md` | Step 3 heading processor generation |
| `heading_expected_result_prompt.md` | `step3_heading_expected_result_prompt.md` | Step 3 explanatory expected result |
| `heading_check_prompt.md` | `step5_heading_validation_prompt.md` | Step 5 heading validation |
| `content_cleaner_prompt.md` | `step6_content_processor_prompt.md` | Step 6 content processor generation |
| `heading_optimization_prompt.md` | `legacy_heading_optimization_prompt.md` | Legacy compatibility |

## Run Artifact Renames

New formatter runs write these prompt copies:

- `step1_toc_detection_prompt.md`
- `step3_heading_processor_prompt.md`
- `step5_heading_validation_prompt.md`
- `step6_content_processor_prompt.md`

Step 3's second DeepSeek call continues to write only `heading_expected_result.md`. It does not add a prompt-copy or raw-response artifact.

Response and executable artifact names remain unchanged, including:

- `toc_detection_response.md`
- `heading_processor_response.py`
- `heading_processor.py`
- `heading_expected_result.md`
- `heading_check_response.json`
- `content_processor_response.py`
- `content_processor.py`

## Runtime Changes

- Update every prompt lookup under `skills/mathos-formatting/scripts/` to the new source filename.
- Update prompt artifact paths written by Steps 1, 3, 5, and 6.
- Keep artifact dictionary keys stable so run-state consumers do not require a schema migration.
- Keep failure routing unchanged because error artifacts are provider responses, not prompt copies.
- The execution fingerprint continues to hash prompt contents; prompt renaming alone does not change its schema.

## Existing Run Directories

Do not rename or delete prompt copies in existing run directories. Historical runs remain readable with their original artifact paths. New or rerun stages write the new prompt filenames; an old and new prompt copy may coexist in a reused work directory.

## Documentation and Tests

- Update `SKILL.md` Artifact Layout to list the new prompt names.
- Update tests that read prompt source files or assert work-directory prompt artifacts.
- Add a focused test that the six source prompt filenames exist and the superseded names do not.
- Verify that a provider-backed mock run writes the new Step 1, Step 3, Step 5, and Step 6 prompt copies and does not write their superseded names.
- Run the complete guarded formatter test suite, syntax compilation, CLI help, and `git diff --check`.

## Non-Goals

- Do not change prompt text or provider behavior.
- Do not rename response, processor, candidate, report, state, digest, or checkpoint artifacts.
- Do not add prompt copies for calls that intentionally have none.
- Do not migrate historical work directories.
