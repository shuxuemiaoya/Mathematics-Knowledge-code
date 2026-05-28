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

## Safety Rules

- Run `--dry-run` before broad formatting changes.
- Use `--backup` when running a changed formatter over important notes.
- Keep secrets in `C:\mygithub\.env` or another private path set by `MATH_KNOWLEDGE_ENV`.
- Never commit generated `.bak`, temporary MinerU extracts, or API keys.
- When changing regex behavior, add a focused test in `tests/`.

## Codex Skills

Repo-local skills live in `skills/`:

- `skills/math-knowledge-formatting`: use for Markdown cleanup and formatter changes.
- `skills/convert-with-mineru`: use for PDF/DOCX to Markdown conversion with MinerU.

Install them into Codex discovery with:

```powershell
.\tools\install_codex_skills.ps1 -SkillName convert-with-mineru -Force
```
