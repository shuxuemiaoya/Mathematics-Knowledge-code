---
name: mathos-weave-links
description: Use when injecting inline Obsidian wikilinks into plain text based on a target ontology dictionary without modifying math formulas or existing links (Zero-Token weaving).
---

# Weaving Obsidian Wikilinks (Phase 3C Track 2)

## Overview
Use this skill when you need to turn plain textbook text into an interactive, hyperlinked Obsidian vault. It uses a purely programmatic regex engine (`weaver.py`) to inject `[[Concept]]` tags into the text.

## When to Use
- When applying the GraphRAG intelligence back into the visual frontend (Obsidian).
- When you want to hyperlink documents without spending any API Tokens.

## Core Rules
1. **Zero-Token Cost**: This operation must be performed entirely locally using the dictionary (`global_ontology.json`). NEVER send the documents to an LLM to "rewrite them with wikilinks".
2. **Safe Injection**: The weaver must strictly skip over any text wrapped in `$...$` or `$$...$$` (Math formulas) and any text already wrapped in `[[...]]`.

## Implementation Logic & Code Link
The core logic resides in `src/mathos/projection/weaver.py`.
It loads `global_ontology.json` as its target dictionary, iterates over every `.md` file in the vault, and performs a safe regex substitution.

## Command Reference
There is no dedicated CLI for this module yet. Use `mathos.projection.weaver.KnowledgeWeaver` from Python, or add a small CLI before documenting a command.

## Common Mistakes / Red Flags
- ❌ **Destroying Formulas**: If a concept name matches a variable inside a LaTeX formula (e.g., matching "A" inside `$A = B + C$`), the weaver is broken. Safe injection is mandatory.
- ❌ **Using an LLM for Weaving**: Using an LLM to inject wikilinks across hundreds of files is a catastrophic waste of money and tokens.
