---
name: question-type-canvas
description: Compile a validated structural Obsidian Canvas from passed Question Type Graph manifests while excluding atomic questions. Use after hierarchy, content, and Markdown stages pass.
---

# Question Type Canvas

Read `references/canvas-contract.md`, then run `scripts/build_canvas.py` with
passed hierarchy and content manifests. Include structural and functional nodes
only. Reject atomic-question cards, invalid endpoints, and unresolved links.
