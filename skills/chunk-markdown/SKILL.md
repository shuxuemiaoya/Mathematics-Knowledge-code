---
name: chunk-markdown
description: Use when breaking down a clean markdown document into smaller Chunk structures based on regular expressions.
---

# Chunk Markdown (Phase 2)

## Overview
Use this skill to invoke the chunker module which splits large markdown files into logical `Chunk` schemas containing title and content.

## Command Reference
```powershell
python -m src.mathos.cli chunk --input "path/to/clean.md" --output "path/to/chunks"
```
