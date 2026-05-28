# Format Knowledge Base

Use the local project at `C:\mygithub\Mathematics-Knowledge-code`.

1. Read `AGENTS.md` and `skills/math-knowledge-formatting/SKILL.md`.
2. Identify the target Markdown directory and formatting mode.
3. Run a dry-run first:

```powershell
mk-format --dir "<target-dir>" --mode "<mode>" --dry-run
```

4. If the dry-run is sensible, run with `--backup` unless the user explicitly says not to.
5. Summarize processed and changed file counts, and note any warnings.
