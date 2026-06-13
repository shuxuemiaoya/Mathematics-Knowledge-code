# Skill Registry

This registry names repo-local skill slots for the MathOS Knowledge-Graph Implementation Operator.

## Active Skills

### `skills/mathos-pdf-to-md`

Status: active first-version skill.

Purpose: coordinate and monitor PDF to Markdown conversion tasks.

First-version behavior:

- Identify the conversion command or Python workflow.
- Run the task only against an explicit user-provided target.
- Monitor crashes, non-zero exits, repeated conversion failures, stalled runs, and missing outputs.
- Stop the task when failure volume crosses the active skill threshold.
- Preserve logs and output locations.
- Report a required output summary.

The skill does not judge whether generated Markdown content is correct.

### `skills/mathos-formatting`

Status: active.

Purpose: MathOS adaptive Markdown formatting workflow.

Behavior:

- Use candidate backup learning for unknown Markdown types, require user approval before saving reusable programs, and store approved manual-only programs under `plugins/approved/`.
- Calling mathos-formatting for learning:
  - Call the `learn-from-provider` CLI command with `--env`, `--work-dir`, and `--h1-index`.
  - It executes the four-stage learning flow:
    1. TOC sample extraction -> call DeepSeek for heading rules (heading standardization and non-TOC heading demotion) -> apply rules to create a stage 1 text and stage 1 report.
    2. Extract first 20 pages of the stage 1 text -> call DeepSeek for TOC end line detection -> strip all content before the detected main text start line.
    3. H1 sample extraction from stripped text.
    4. Call DeepSeek for image/text content cleaner -> run content cleaner protecting heading lines.
  - It fails closed, restoring the stripped text if heading protection fails in stage 4.

Approved manual-only programs:

- `rj6_heading_levels`: approved after successful user review for `Secondary-School-Mathematics-Knowledge-Map/小学/人教版数学/六年级上册` heading hierarchy normalization. Reuse with `apply-approved` only on matching 人教版数学六年级上册 / 一遍过 RJ6 Markdown family unless the user asks for a new candidate review.

### `skills/mathos-segmentation-stage1`

Status: active.

Purpose: deterministic post-formatting segmentation into Obsidian sandbox packages.

Behavior:

- Consumes one formatted Markdown file after `mathos-formatting`.
- Builds a layered Obsidian package from formatted Markdown body headings.
- Writes a master directory that links only to top-level chapter notes.
- Writes non-leaf notes as pure directory notes with immediate-child links only.
- Writes raw source slices only to leaf notes.
- Merges conservative special heading pairs such as `阅读与思考` plus its following specific subheading.
- Leaves the original source Markdown untouched.
- Writes run records under `agent-memory/records/<date>-segmentation-stage1-<slug>/`.

## Reserved Future Skill Slots

### `skills/mathos-word-to-md`

Status: reserved, inactive.

Purpose: future Word/DOCX to Markdown workflow.

This slot must not contain a `SKILL.md` until its detailed behavior is designed and approved.
