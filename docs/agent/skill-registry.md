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

## Reserved Future Skill Slots

### `skills/mathos-word-to-md`

Status: reserved, inactive.

Purpose: future Word/DOCX to Markdown workflow.

This slot must not contain a `SKILL.md` until its detailed behavior is designed and approved.

### `skills/mathos-formatting`

Status: operational.

Purpose: MathOS adaptive Markdown formatting workflow.

Use candidate backup learning for unknown Markdown types, require user approval before saving reusable programs, and store approved manual-only programs under `plugins/approved/`.
