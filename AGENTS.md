# Codex Project Guide

This repository contains automation code for the local knowledge base at:

`C:\mygithub\Secondary-School-Mathematics-Knowledge-Map`

Use this repo for code, tooling, skills, and automation. Do not edit the knowledge-base repo unless the user explicitly asks for content changes or a formatter/conversion command targets it.

## Commands

Install locally:

```powershell
python -m pip install -e .[dev]
```

Run tests:

```powershell
python -m pytest
```

Preview Markdown formatting before writing:

```powershell
mk-format --dir "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map\高中\课本" --mode textbook --dry-run
```

Convert source documents:

```powershell
mk-mineru "C:\path\to\source-documents" --format textbook
```

Build Zettelkasten Vault (Sprint 3A):

```powershell
mk-vault --input "C:\path\to\textbook.md" --output "C:\path\to\vault_dir" --mode highschool_textbook
```

Extract Ontology Candidates (Sprint 3B):

```powershell
$env:DEEPSEEK_API_KEY="sk-..."
mk-extract --vault_dir "C:\path\to\vault_dir"
```

## Safety Rules

- Run `--dry-run` before broad formatting changes.
- Use `--backup` when running a changed formatter over important notes.
- Keep secrets in `C:\mygithub\.env` or another private path set by `MATH_KNOWLEDGE_ENV`.
- Never commit generated `.bak`, temporary MinerU extracts, or API keys.
- When changing regex behavior, add a focused test in `tests/`.

## Codex Skills

Repo-local skills live in `skills/`:

- `skills/mathos-formatter`: use for Markdown cleanup and formatter changes.
- `skills/mathos-convert-with-mineru`: use for PDF/DOCX to Markdown conversion with MinerU.

Install them into Codex discovery with:

```powershell
Copy-Item -LiteralPath .\skills\mathos-convert-with-mineru -Destination "$HOME\.codex\skills" -Recurse -Force
```
