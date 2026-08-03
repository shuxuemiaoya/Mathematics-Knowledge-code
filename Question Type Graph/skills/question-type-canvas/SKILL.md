---
name: question-type-canvas
description: Compile a validated structural Obsidian Canvas from reviewed Question Type Graph hierarchy and content manifests, including chapters, sections, functional blocks, question types, and subtypes while excluding atomic questions and deferred knowledge-point links. Use after Markdown validation.
---

# Question Type Canvas

Read `references/canvas-contract.md`.

```powershell
python scripts/build_canvas.py `
  "<profile>" "<hierarchy-manifest>" "<question-type-manifest>" `
  "<staging>/graph-manifest.json" "<graph>/<title>.canvas"
```

Derive every card, group, link, and edge from manifests. Use color `6` for `question-type` and `subtype` roles unless the profile overrides it. Emit containment and source-order structure only. Reject unresolved note links, bad endpoints, duplicate IDs, atomic-question cards, and existing output without explicit overwrite.
