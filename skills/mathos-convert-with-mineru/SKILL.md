---
name: mathos-convert-with-mineru
description: Convert PDF and DOCX source documents into Markdown for the user's mathematics knowledge base using the MinerU batch pipeline. Use when the user asks to convert a folder or document path to Markdown, ingest new textbooks, exercise books, scanned PDFs, or Word files into the knowledge-base directory.
---

# Convert With MinerU

## Workflow

1. Work from `C:\mygithub\Mathematics-Knowledge-code`.
2. Read `AGENTS.md` for repository safety rules.
3. Confirm `MINERU_API_KEY` is configured in `C:\mygithub\.env`, repo `.env`, `MATH_KNOWLEDGE_ENV`, or the shell environment.
4. When the user asks to convert a folder (e.g., `C:\code\BaiduSyncdisk\数学妙呀资料\高中\...`), calculate and tell the user what the final mapped output path will be. Note: The tool automatically preserves the relative folder structure from the base source dir (e.g., `高中\...`), and appends it to `-OutDir`.
5. Explicitly ASK the user to confirm the mapped output directory, or if they want to modify it. Wait for their response before proceeding.
6. CRITICAL WARNING: When running the script, `-OutDir` MUST be the **root** of the knowledge base (i.e., `C:\mygithub\Secondary-School-Mathematics-Knowledge-Map`). Do NOT append the subdirectories (like `\高中\...`) to `-OutDir`, because the script automatically appends the relative path from the source. Doing so will result in duplicated paths (e.g. `...\高中\专题\高中\专题`).
7. Run the installed CLI using the root output directory: `mk-mineru "<source-root>" --out-dir "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map" --format "<mode>"`.
8. After starting the task, set up a recurring schedule (using the `schedule` tool with cron `*/10 * * * *`) to check the task log every 10 minutes.
9. On each 10-minute check, report the success/failure progress to the user. If there are major problems (e.g., a high failure rate, continuous critical API/network errors stopping progress), immediately kill the background task using `manage_task` and alert the user.
10. Once the process completes normally, report final success, skipped, failed, and formatter mode from the logs, and cancel the schedule.

## Commands

Use the installed CLI:

```powershell
mk-mineru "C:\path\to\source-documents" --format textbook
```

Or run the module directly without console-script installation:

```powershell
python -m mathos.ingestion.mineru.cli "C:\path\to\source-documents" --format textbook
```

## References

Read `references/mineru-workflow.md` before changing ingestion path logic, batching, retries, or post-processing.
