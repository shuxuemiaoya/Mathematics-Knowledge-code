# MathOS Formatting Provider Learning Design

## Goal

Extend `skills/mathos-formatting` with a provider-driven learning command that generates and applies formatting programs from representative Markdown samples.

The workflow has two required stages:

1. Extract a Markdown sample that contains a detected table of contents, send it with the heading prompt to DeepSeek, save returned heading rules, and apply those rules to a fresh backup candidate.
2. Extract one complete H1 section from the updated candidate, send it with the image/text cleanup prompt to DeepSeek, save returned Python cleaner code, and apply that cleaner to the same candidate.

Original Markdown files must never be modified during learning.

## Existing Context

`skills/mathos-formatting` already provides:

- `inspect`
- `candidate-from-artifacts`
- `approve`
- `apply-approved`
- heading-rule validation and protected-block handling
- text-only plugin safety validation
- provider settings and DeepSeek-compatible chat calls
- approved manual-only program reuse

The new work should add an automated learning path while preserving the existing artifact-based and approved-program paths.

## Command

Add a new CLI command:

```powershell
python skills/mathos-formatting/scripts/mathos_formatting.py learn-from-provider <markdown> --env C:\Mathematics-Knowledge\.env
```

Optional arguments may include:

- `--work-dir <path>`: override the default learning artifact directory.
- `--timeout-seconds <n>`: override provider timeout.
- `--h1-index <n>`: choose which H1 section to sample, defaulting to the first complete H1 section after heading normalization.

The command prints machine-readable JSON status to stdout.

## Data Flow

1. Read the original Markdown.
2. Extract structure from the original.
3. Locate a table-of-contents block.
4. If no TOC is found, stop with status `failed` and error `TOC not found`.
5. Write `toc_sample.md`.
6. Build the heading-rule prompt payload from the TOC sample and surrounding heading context.
7. Call DeepSeek through the provider adapter.
8. Save raw heading response.
9. Parse and validate heading rules.
10. Write `heading_rules.json`.
11. Create a fresh candidate backup from the original.
12. Apply heading rules to the candidate.
13. Write a stage-1 report.
14. Re-inspect the updated candidate.
15. Extract one complete H1 section from the updated candidate.
16. If no H1 section is available, stop with status `failed`.
17. Write `h1_sample.md`.
18. Build the content-cleaner prompt payload from the H1 sample.
19. Call DeepSeek through the provider adapter.
20. Save raw Python cleaner response.
21. Parse the Python artifact.
22. Save `content_cleaner.py`.
23. Validate the cleaner with the existing safe plugin loader.
24. Apply the cleaner to the same candidate while protecting heading lines.
25. If heading lines change during stage 2, fail the run and restore the candidate to its stage-1 text.
26. Write the final candidate report.
27. Leave approval to the existing `approve` command after explicit user review.

## Artifact Layout

For a source file:

```text
<source folder>/.mathos-formatting/<source stem>/
```

write:

- `toc_sample.md`
- `heading_rules_prompt.md`
- `heading_rules_response.json`
- `heading_rules.json`
- `stage1_heading_report.md`
- `h1_sample.md`
- `content_cleaner_prompt.md`
- `content_cleaner_response.py`
- `content_cleaner.py`
- `candidate.md`
- `candidate-report.md`
- `run-state.json`

`run-state.json` records:

- source path
- candidate path
- provider base URL without secrets
- provider model
- current stage
- status
- generated artifact paths
- warnings
- errors
- whether user approval has happened

## Stage 1 Rules

Stage 1 is responsible only for heading normalization.

Requirements:

- A TOC must be detected.
- No fallback to heading-outline-only samples.
- DeepSeek must return JSON only.
- Heading rules must validate through the existing rule validator.
- Rules apply only to the candidate backup.
- Existing protected-block behavior must preserve code fences, math blocks, images, and other protected spans.

## Stage 2 Rules

Stage 2 is responsible only for image and text formatting cleanup.

Requirements:

- Stage 2 samples from the stage-1 updated candidate, not from the original.
- DeepSeek must return one Python plugin file.
- The plugin must pass the existing text-only safety loader.
- Heading lines are protected after stage 1.
- If stage 2 changes heading lines, the run fails and restores candidate content to the stage-1 version.
- Stage 2 must not approve or save a reusable program by itself.

## Error Handling

The command fails closed when:

- TOC is not found.
- provider settings cannot be loaded.
- provider call fails.
- heading response is invalid JSON.
- heading rules fail validation.
- candidate backup cannot be created.
- updated candidate has no complete H1 section.
- content cleaner response is invalid Python artifact.
- plugin safety validation fails.
- stage 2 changes heading lines.
- report or state writing fails.

On failure:

- Original Markdown remains untouched.
- `run-state.json` records the failed stage and error when the work directory exists.
- Partial candidate output remains as evidence unless failure occurred before candidate creation.
- stdout contains concise JSON status.

## Approval And Reuse

The learning command does not write into `plugins/approved/`.

After the user reviews and approves the candidate backup, the existing `approve` command saves:

- heading rules
- content cleaner
- samples
- approval note
- metadata

Approved programs remain `manual-only` until a separate human-approved change expands their scope.

## Testing

Add tests for:

- TOC missing stops before provider call and before candidate mutation.
- TOC sample extraction includes the TOC and enough heading context.
- Stage 1 saves the provider heading response and applies validated rules to the candidate.
- Stage 2 extracts H1 from the updated candidate.
- Stage 2 protects headings from cleaner modifications.
- Invalid provider artifacts fail closed with `run-state.json`.
- Successful runs write all expected artifacts and final report.
- Original Markdown remains unchanged.
- CLI stdout is valid machine-readable JSON.

## Scope Boundaries

In scope:

- One-file learning runs.
- Provider-driven generation of heading rules and content cleaner artifacts.
- Candidate backup mutation only.
- Explicit user approval through existing approval flow.

Out of scope:

- Batch approval.
- Automatic promotion beyond `manual-only`.
- Modifying original Markdown files.
- Judging mathematical correctness or content quality.
- Replacing the existing artifact-based workflow.
