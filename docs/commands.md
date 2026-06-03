# Commands

## Install

```powershell
cd C:\mygithub\Mathematics-Knowledge-code
python -m pip install -e .[dev]
```

## Format Markdown

```powershell
mk-format --dir "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map\高中\课本" --mode textbook --dry-run
mk-format --dir "C:\mygithub\Secondary-School-Mathematics-Knowledge-Map\高中\课本" --mode textbook --backup
```

Modes:

- `textbook`: textbook structure, captions, callouts, examples.
- `exercise`: general exercise formatting.
- `yishu`: exercise formatting plus 一数 special handling.
- `bishua`: exercise formatting plus 必刷题 special handling.
- `all_exercises`: combined exercise handling.

## Convert Documents

```powershell
mk-mineru "C:\path\to\source-documents" --format textbook
```

## Zettelkasten Builder (Sprint 3A)

```powershell
mk-vault --input "C:\path\to\textbook.md" --output "C:\path\to\vault_dir" --mode highschool_textbook
```

## Ontology Extractor (Sprint 3B)

Ensure you set the API key before running:
```powershell
$env:DEEPSEEK_API_KEY="sk-..."
mk-extract --vault_dir "C:\path\to\vault_dir"
```

Defaults come from `.env`:

- `KNOWLEDGE_BASE_DIR`
- `SOURCE_MATERIALS_DIR`
- `MINERU_API_KEY`
- `DEEPSEEK_API_KEY`

## Unified CLI

```powershell
math-knowledge format --dir "C:\path\to\markdown" --mode exercise --dry-run
math-knowledge mineru "C:\path\to\source-documents" --format all_exercises
```
