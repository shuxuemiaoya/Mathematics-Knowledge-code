---
name: math-knowledge-ingestion
description: Convert PDF and DOCX source documents into Markdown for the user's mathematics knowledge base using the MinerU batch pipeline. Use when ingesting new textbooks, exercise books, scanned PDFs, Word files, or when preparing Codex automation that maps source folders into the knowledge-base directory.
---

# Math Knowledge Ingestion

## Workflow

1. Work from `C:\mygithub\Mathematics-Knowledge-code`.
2. Read `AGENTS.md` for repository safety rules.
3. Confirm `MINERU_API_KEY` is configured in `C:\mygithub\.env`, repo `.env`, `MATH_KNOWLEDGE_ENV`, or the shell environment.
4. Choose a source root containing the intended PDF/DOCX batch.
5. Preserve folder structure by setting `--base-src-dir` to the stable source-materials root when needed.
6. Run `mk-mineru "<source-root>" --format "<mode>"`.
7. Report success, skipped, failed, and formatter mode from the logs.

## Commands

Use the installed CLI:

```powershell
mk-mineru "C:\path\to\source-documents" --format textbook
```

Or the repo wrapper without installation:

```powershell
.\tools\convert_with_mineru.ps1 -RootDir "C:\path\to\source-documents" -Format textbook
```

## References

Read `references/mineru-workflow.md` before changing ingestion path logic, batching, retries, or post-processing.
