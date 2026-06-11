# mathos-formatting

Status: operational.

This repo-local skill manages adaptive Markdown formatting for MathOS.

The workflow uses the LLM as a senior engineer that creates reusable formatting artifacts from samples:

1. `inspect` reads a Markdown file and reports headings, table-of-contents signals, h1 sections, and protected blocks.
2. `learn-from-provider` performs the two-stage DeepSeek learning workflow: TOC sample to heading rules, then complete H1 sample to image/text cleaner. This stops when a TOC is not found and protects structural heading lines, failing closed if heading protection is violated.
3. Alternatively, manually generate or provide regex heading rules and a Python content cleaner, then run `candidate-from-artifacts` to create the candidate backup.
4. Ask the user to review the backup result and choose approve, revise, or discard.
5. Run `approve` only after explicit user approval.
6. Reuse approved programs with `apply-approved`; this still writes a fresh candidate backup and does not modify the original Markdown file.

Original Markdown files are not modified during learning or approved reuse. Approved programs start with `manual-only` scope until real-world review justifies broader automation.

## CLI Commands

### 1. inspect
Analyze a Markdown document's structural elements.
```bash
python skills/mathos-formatting/scripts/mathos_formatting.py inspect <markdown_path>
```

### 2. learn-from-provider
Run the automated two-stage learning flow:
- Stage 1: Extracts TOC sample -> deepseek-chat rules generation -> candidate modification.
- Stage 2: Extracts H1 section sample -> deepseek-chat python plugin generation -> candidate modification with heading line protection.
```bash
python skills/mathos-formatting/scripts/mathos_formatting.py learn-from-provider <markdown_path> --env <env_path> [--work-dir <work_dir>] [--h1-index <h1_index>] [--timeout-seconds <timeout>]
```

### 3. candidate-from-artifacts
Create a candidate backup by manually applying rules and cleaner plugins.
```bash
python skills/mathos-formatting/scripts/mathos_formatting.py candidate-from-artifacts <markdown_path> --heading-rules <rules_path> --plugin <plugin_path>
```

### 4. approve
Save a reviewed candidate run as an approved program under `plugins/approved/`.
```bash
python skills/mathos-formatting/scripts/mathos_formatting.py approve --approved-root <approved_root> --plugin-id <plugin_id> --heading-rules <rules_path> --plugin <plugin_path> --original <original_path> --candidate <candidate_path>
```

### 5. apply-approved
Apply an approved program directly to a target Markdown document (no LLM calls).
```bash
python skills/mathos-formatting/scripts/mathos_formatting.py apply-approved <program_dir> <markdown_path>
```
