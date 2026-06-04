---
name: mathos-build-canvas
description: Use when building a hybrid Tree-to-Web Canvas (Left-to-Right layout) in Obsidian and materializing virtual concepts into physical Markdown hub files.
---

# Generating Concept Canvas (Phase 3D)

## Overview
Use this skill when generating the ultimate Obsidian visualization: a Left-To-Right JSON Canvas that connects the physical tree topology of the textbook with the web topology of the concepts, and generates the physical Markdown files for those concepts.

## When to Use
- To visualize the full knowledge map in Obsidian.
- To instantiate "dead" links (virtual concepts) into real `.md` files.

## Core Process & Code Links
1. **Concept Hub Generation**: Materialize all entities in `global_ontology.json` into a single folder containing hundreds of `.md` files. **CRITICAL**: You MUST use the `concept-hub-naming` skill to ask the user what to name this folder!
   - Script: implementation not currently present in `src/mathos`.
2. **Tree-to-Web Canvas**: Use `src/mathos/projection/canvas_builder.py` to generate the `.canvas` file.
   - **Level 0 (x=-380)**: Chapter headings.
   - **Level 1 (x=-20)**: Physical document files.
   - **Level 2 (x=440)**: Materialized concepts (linked to documents).
   - **Level 3 (x=880)**: Prerequisites (linked to concepts).

## Command Reference
There is no dedicated CLI for this module yet. Use `mathos.projection.canvas_builder.HybridCanvasBuilder` from Python, or add a small CLI before documenting a command.

## Common Mistakes / Red Flags
- ❌ **Hardcoding the Concept Folder Name**: Never hardcode the folder name (e.g., `概念库`). Always ask the user.
- ❌ **Using `type: file` for large documents**: In the Canvas, always use small text cards containing wikilinks (`{"type": "text", "text": "[[Filename]]"}`) rather than embedding the entire file (`{"type": "file"}`), which clutters the UI.
