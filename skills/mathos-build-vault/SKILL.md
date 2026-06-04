---
name: mathos-build-vault
description: Use when converting a large hierarchical Markdown document (like a textbook) into a parsed Obsidian vault while strictly preserving the physical folder hierarchy (H1/H2/H3).
---

# Parsing Markdown to Vault (Phase 3A)

## Overview
Use this skill when you need to split a large, flat Markdown document (such as a textbook) into a physical Obsidian Vault containing hundreds of micro-cards, while **strictly preserving the tree topology (H1/H2/H3) as physical nested directories on the disk**.

## When to Use
- When running `mk-vault parse`.
- When you need to prepare the raw textbook data for GraphRAG or LLM extraction.

## Core Rule: Preserve Physical Hierarchy
**NEVER** flatten the markdown files into a single directory. The command utilizes `vault_builder.py` which must read the `parent_hierarchy` of each chunk and create actual nested directories (e.g., `知识点/第六章/6.1/6.1.1.md`).

## Command Reference
There is no working CLI for this stage yet. `mathos.vault.vault_builder` currently needs import cleanup before it can be used as a command.

## Common Mistakes / Red Flags
- ❌ **Flattening directories**: If the output vault only contains files at the root level, the parser is broken and the tree topology is lost.
- ❌ **Splitting Callouts**: Obsidian callouts (`> [!info]`) must be preserved as atomic chunks, they should not be split across multiple files.
