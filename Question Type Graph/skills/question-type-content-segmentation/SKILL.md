---
name: question-type-content-segmentation
description: Split reviewed supplementary-book hierarchy notes into profile-mapped functional nodes and one source-exact Markdown leaf per top-level question while preserving subparts, media, context, order, and parent navigation. Use after hierarchy coverage passes and before answer matching.
---

# Question Type Content Segmentation

Own functional roles and atomic questions. Read `references/content-manifest.md`.

```powershell
python scripts/segment_content.py plan `
  "<profile>" "<adapter>" "<hierarchy-coverage>" `
  "<staging>/question-type-manifest.json"

python scripts/segment_content.py apply `
  "<profile>" "<adapter>" "<staging>/question-type-manifest.json"
```

Interpret literal labels only through adapter regexes mapped to semantic roles. Keep repeated training bands inside their owning reviewed TOC entry; they must never replace section, topic, comprehensive-training, assessment, or reinforcement nodes in the parent hierarchy. Use adapter depths to nest subtypes beneath question types. Keep each top-level question and its subparts together, wrap its exact body in provenance markers, and replace the moved block with an ordered Markdown link. Block unknown labels when the adapter selects review policy.
