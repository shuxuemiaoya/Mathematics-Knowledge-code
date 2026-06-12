# mathos-formatting

Status: operational.

This repo-local skill manages adaptive Markdown formatting for MathOS.

The workflow uses the LLM to dynamically generate reusable formatting artifacts from samples:

1. `inspect` reads a Markdown file and reports headings, table-of-contents signals, H1 sections, and protected blocks.
2. `learn-from-provider` performs the four-stage DeepSeek learning workflow (using temperature `0.0` and `json_object` format where appropriate):
   - **Stage 1 (Heading Rules)**: Extracts the TOC sample and queries the LLM to standardize TOC headings (Chapter to H1, Section to H2, etc.) and demote any non-TOC headings to levels not used by the TOC (H4+).
   - **Stage 2 (TOC Detection & Stripping)**: Extracts the first 20 pages of the document (using metadata-based page estimation or a heuristic fallback), sends them with prepended line numbers to the LLM, and selectively strips only the detected Table of Contents block (between the detected TOC start and the main text start), preserving preceding pages/prefaces.
   - **Stage 3 (H1 Extraction)**: Extracts the first complete H1 section from the stripped candidate for content cleaner generation.
   - **Stage 4 (Content Cleaner)**: Sends the H1 section sample to the LLM to generate a Python content cleaner plugin for image/text formatting.
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
Run the automated four-stage learning flow:
- Stage 1: Extracts TOC sample -> heading rules generation (heading standardization & non-TOC heading demotion) -> candidate modification.
- Stage 2: Extracts first 20 pages -> LLM TOC boundary detection -> strip only the TOC block.
- Stage 3: Extracts first H1 section from stripped candidate.
- Stage 4: H1 sample -> python plugin generation -> candidate modification with heading line protection.
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
