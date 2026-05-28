# Codex Compatibility Audit

## Summary

The original logic was useful but folder-run oriented. The migration makes it safer for Codex and AI CLI workflows by adding an installable package, stable commands, dry-run support, tests, skills, and automation prompts.

## md_formatter

Status: compatible after packaging changes.

Changes:

- Moved into `src/math_knowledge_tools/md_formatter`.
- Added `mk-format` and `math-knowledge format` console commands.
- Added `--dry-run` so agents can inspect planned edits before modifying notes.
- Preserved existing modes: `textbook`, `exercise`, `yishu`, `bishua`, `all_exercises`.

Agent guidance:

- Use `--dry-run` first for large directories.
- Use `--backup` when writing to the knowledge-base repo after regex changes.
- Add regression tests for any new replacement rule.

## mineru

Status: compatible after import and safety fixes.

Changes:

- Moved into `src/math_knowledge_tools/mineru`.
- Replaced `sys.path` mutation with package-relative imports.
- Added `mk-mineru` and `math-knowledge mineru` console commands.
- Kept private `.env` loading from `C:\mygithub\.env`, while allowing `MATH_KNOWLEDGE_ENV`.
- Added output path containment checks so a bad `--base-src-dir` cannot write outside `--out-dir`.
- Replaced unsafe `ZipFile.extractall` with checked extraction.

Agent guidance:

- Confirm `MINERU_API_KEY` is configured before conversion.
- Keep `--base-src-dir` as the stable source root when preserving folder structure matters.
- Use a narrow source folder for first-run smoke checks.

## Codex Scaffolding

Added:

- `AGENTS.md` for future Codex sessions.
- `skills/` with project-specific formatting and ingestion skills.
- `automation/prompts/` for repeatable AI CLI jobs.
- `tools/` PowerShell wrappers for common local commands.
- `tests/` for formatter and path handling behavior.
