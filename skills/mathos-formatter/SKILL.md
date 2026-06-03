---
name: mathos-formatter
description: Format and review Markdown in the user's secondary-school mathematics knowledge base. Use when cleaning OCR or MinerU Markdown, applying textbook or exercise formatting modes, editing formatter rules, running dry-run and backup workflows, or preparing Codex automation for Markdown cleanup.
---

# Math Knowledge Formatting

## Workflow

1. Work from `C:\mygithub\Mathematics-Knowledge-code`.
2. Read `AGENTS.md` for repository safety rules.
3. Choose the formatter mode:
   - `textbook` for textbooks, captions, callouts, examples, figure tables.
   - `exercise` for general exercise parsing, answers, analysis, options.
   - `yishu` for exercise formatting plus Yi Shu special handling.
   - `bishua` for exercise formatting plus Bi Shua Ti special handling.
   - `all_exercises` for combined exercise handling.
4. Run `mk-format --dir "<target-dir>" --mode "<mode>" --dry-run` before broad edits.
5. If the dry-run is expected, run with `--backup` when changing real knowledge-base files.
6. If formatter code changes, add a focused regression test and run `python -m pytest`.

## Commands

Use the installed CLI:

```powershell
mk-format --dir "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map\高中\课本" --mode textbook --dry-run
```

Or the repo wrapper without installation:

```powershell
.\tools\format_knowledge_base.ps1 -Dir "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map\高中\课本" -Mode textbook -DryRun
```

## References

Read `references/formatting-rules.md` when choosing a mode or modifying formatting behavior.
