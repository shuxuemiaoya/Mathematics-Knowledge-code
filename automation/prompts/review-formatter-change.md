# Review Formatter Change

Use this prompt when a regex or formatter behavior changes.

1. Read the changed files in `src/math_knowledge_tools/md_formatter`.
2. Add or update focused tests in `tests/`.
3. Run:

```powershell
python -m pytest
```

4. Run a small `--dry-run` against a representative knowledge-base folder.
5. Summarize behavior changes, test coverage, and any files that would be modified.
