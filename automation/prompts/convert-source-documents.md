# Convert Source Documents

Use the local project at `C:\mygithub\Mathematics-Knowledge-code`.

1. Read `AGENTS.md` and `skills/math-knowledge-ingestion/SKILL.md`.
2. Confirm the source root contains only the PDF/DOCX batch intended for conversion.
3. Confirm `MINERU_API_KEY` is available through `.env` or the environment.
4. Run:

```powershell
mk-mineru "<source-root>" --format "<none|textbook|exercise|yishu|bishua|all_exercises>"
```

5. Report success, skipped, and failed counts from the log output.
6. If formatting was enabled, mention the formatter mode used.
