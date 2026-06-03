---
name: build-canvas
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
   - Script: `src/math_knowledge_tools/obsidian_integration/concept_generator.py`
2. **Tree-to-Web Canvas**: Use `src/math_knowledge_tools/obsidian_integration/canvas_builder.py` to generate the `.canvas` file.
   - **Level 0 (x=-380)**: Chapter headings.
   - **Level 1 (x=-20)**: Physical document files.
   - **Level 2 (x=440)**: Materialized concepts (linked to documents).
   - **Level 3 (x=880)**: Prerequisites (linked to concepts).

## Command Reference
To generate concepts and build the canvas:
```powershell
python -m src.math_knowledge_tools.obsidian_integration.cli generate-concepts --ontology "global_ontology.json" --output-dir "path/to/vault/<USER_NAMED_FOLDER>"
python -m src.math_knowledge_tools.obsidian_integration.cli build-canvas --vault-dir "path/to/vault" --ontology "global_ontology.json"
```

## Common Mistakes / Red Flags
- ❌ **Hardcoding the Concept Folder Name**: Never hardcode the folder name (e.g., `概念库`). Always ask the user.
- ❌ **Using `type: file` for large documents**: In the Canvas, always use small text cards containing wikilinks (`{"type": "text", "text": "[[Filename]]"}`) rather than embedding the entire file (`{"type": "file"}`), which clutters the UI.
