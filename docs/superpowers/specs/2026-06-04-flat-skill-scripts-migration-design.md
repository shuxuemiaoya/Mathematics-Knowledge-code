# Flat Skill Scripts Migration Design

## Context

The `mathos` automation code currently lives under `src/mathos`, while Codex skills live under `skills/mathos-*`. A previous migration created skill directories such as `skills/mathos-formatter/scripts`, but did not place runnable code directly inside those `scripts` directories. This made the skills appear migrated while still depending on the central `src/mathos` package.

The desired end state is that each skill is self-contained. A skill should remain runnable even if `src/mathos` is removed later.

## Goal

Move each skill's required executable Python code directly into that skill's `scripts` directory with a flat layout. Do not create nested package folders such as `scripts/mathos/formatter`.

For the formatter skill, the target shape is:

```text
skills/mathos-formatter/
  SKILL.md
  references/
  scripts/
    cli.py
    core.py
    discovery.py
    logger.py
    textbook.py
    zhefa_mimi.py
    renjiao_highschool_textbook.py
    rule_builder.py
```

## Non-Goals

- Do not keep `scripts` as wrappers around `src/mathos`.
- Do not require editable package installation for normal skill usage.
- Do not introduce nested Python package directories inside skill `scripts`.
- Do not delete `src/mathos` during the migration. Deletion can be decided after all skills are verified as self-contained.

## Architecture

Each `skills/mathos-*` directory owns the code needed by that skill.

The `scripts` directory is treated as the import root for that skill. Code that previously used package-relative imports, such as `from .core import BaseFormatter`, must be changed to same-directory imports, such as `from core import BaseFormatter`, or the entry script must explicitly add its own directory to `sys.path`.

Prefer explicit same-directory imports for readability. Use `sys.path` setup only where an entry script must support direct execution from any current working directory.

## Formatter Migration

`skills/mathos-formatter/scripts` receives the formatter modules currently required for these modes:

- `textbook`
- `renjiao-highschool-textbook`
- `zhefa-mimi`

The formatter CLI remains file-or-directory based and supports:

- `--dir`
- `--mode`
- `--dry-run`
- `--backup`
- `--toc-lines`

`SKILL.md` is updated so its commands call the local script directly:

```powershell
python "C:\mygithub\Mathematics-Knowledge-code\skills\mathos-formatter\scripts\cli.py" --dir "<target>" --mode zhefa-mimi --dry-run
```

## Other Skill Migration Pattern

After `mathos-formatter` is proven, migrate the remaining `mathos-*` skills one at a time using the same rules:

1. Identify the modules needed by the skill's documented commands.
2. Copy those modules directly into that skill's `scripts` directory.
3. Flatten imports so scripts run without `src/mathos`.
4. Update the skill's `SKILL.md` commands.
5. Verify the documented command path.

Shared code may be duplicated between skills. This is intentional for now because portability and clarity are more important than deduplication.

## Error Handling

Each migrated CLI should fail with a clear message when required inputs are missing or invalid. Existing command behavior should be preserved where possible.

For formatter runs against knowledge-base files, the documented safe pattern remains:

1. Run with `--dry-run`.
2. Run with `--backup` before writing real files.

## Testing And Verification

For `mathos-formatter`, verification requires:

- `python skills\mathos-formatter\scripts\cli.py --help`
- A dry run against a narrow Markdown target.
- A backup write against a disposable or explicitly selected Markdown target.

For later skills, verification should follow each skill's documented command. If a skill changes parsing or formatting behavior, add or preserve focused tests near the migrated code where practical.

## Rollout

Start with `mathos-formatter` as the template because it is the skill currently in active use and has a clear CLI surface. Once it works from `skills/mathos-formatter/scripts` without relying on `src/mathos`, repeat the same migration pattern for the other `mathos-*` skills.

The migration is complete only when the documented command in each migrated `SKILL.md` works without importing from `C:\mygithub\Mathematics-Knowledge-code\src\mathos`.
