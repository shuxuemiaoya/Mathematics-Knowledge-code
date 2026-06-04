---
name: mathos-extract-candidate
description: Use when you need to extract micro-concepts, definitions, and prerequisites from parsed textbook chunks using an LLM batch processor.
---

# Extracting Ontology with LLM (Phase 3B)

## Overview
Use this skill to invoke the DeepSeek/LLM batch processing script that reads the parsed vault (from Phase 3A) and extracts structured JSON ontologies (concepts, prerequisites) for every single markdown file.

## When to Use
- After a vault has been successfully parsed and physically nested.
- When generating the raw data needed for the Global Graph (GraphRAG) or Obsidian Web.

## Core Process
The batch runner (`mathos.extraction.batch_runner`) will traverse the parsed vault and generate `*.candidates.json` files. 
These JSON files are stored in a parallel physical directory structure (usually suffixed with `_candidates` or placed alongside the source files), perfectly mirroring the nested hierarchy of the vault.

## Command Reference
There is no dedicated CLI for this module yet. Use `mathos.extraction.batch_runner.OntologyBatchRunner` from Python, or add a small CLI before documenting a command.

## Common Mistakes / Red Flags
- ❌ **Loss of Source Linkage**: If the output JSONs do not contain the correct `_source_file` path (including the nested directories), they will be orphaned during the global merge.
- ❌ **Sequential Execution**: Do not try to write a loop to call the LLM one by one yourself; always rely on the `batch_runner` for asynchronous/concurrent API calls to save time.
