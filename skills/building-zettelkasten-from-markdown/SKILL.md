---
name: building-zettelkasten-from-markdown
description: Use when converting large markdown files into Zettelkasten knowledge graphs, building Vault Builders, or chunking markdown. Enforces RKDT strict hierarchy, Root MOC preservation, and selective callout splitting.
---

# Building Zettelkasten from Markdown

When extracting knowledge from a monolithic Markdown file into a physical Obsidian Vault (Zettelkasten), agents often fail by trusting OCR-corrupted heading depths (`#`) and over-fragmenting content. This skill enforces the **Strict RKDT (Recursive Knowledge Decomposition Tree)** rules.

## Core Rules

### 1. Hierarchy Override (Do NOT Trust `#`)
OCR often incorrectly labels bold text as `# H1`. Trusting the raw `#` count will pollute the Root MOC with fake top-level chapters.
*   **Rule**: Use Regex to enforce hierarchical levels based on semantic numbering.
*   **Implementation Example**:
    *   `^第[一二三四五六七八九十百]+章` -> Force Level 1
    *   `^\d+\.\d+\s` (e.g., `1.1 `) -> Force Level 2
    *   `^\d+\.\d+\.\d+\s` (e.g., `1.1.1 `) -> Force Level 3
    *   **Demotion**: If a heading lacks a standard numbering prefix, it **MUST NOT** jump higher than the current context depth. Force its level to `current_depth + 1` so it remains a child node.

### 2. Strict RKDT MOC Linkage
The goal is to preserve the exact skeleton of the original file without grandfather-grandson links.
*   **Root MOC**: The master document must become a Root MOC (e.g., `【人教版】高中必修第一册.md`) which ONLY contains links to Level 1 nodes (`hierarchy[0]`).
*   **Strict Parents**: A parent node ONLY generates links to its direct children.

### 3. Strict TOC Extraction (No-Split Mechanism)
Do NOT extract ANY Callout into its own physical `.md` file. Over-fragmentation destroys the natural structure of the book.
*   **Rule**: ALL callouts (including `[!example]`, `[!explore]`, `[!observe]`, `[!think]`) MUST remain embedded in their parent section.
*   **Action**: Append their raw text to the parent node's `content` property. Physical file creation is strictly limited to the native TOC heading structure (Chapters, Sections, Subsections).

## Red Flags
🚩 Relying exclusively on `#` count for hierarchy detection.
🚩 Root MOCs displaying granular sections or random bolded words.
🚩 Splitting ANY callout (e.g., `[!example]`, `[!explore]`) into separate physical files.

## Workflow Integration
When building a VaultBuilder or MarkdownChunker:
1. Initialize the `MarkdownChunker` with the **Hierarchy Override** logic.
2. Initialize the `VaultBuilder` with a root file name parameter.
3. Apply the **No-Split** rule unconditionally when processing `callout` types.

