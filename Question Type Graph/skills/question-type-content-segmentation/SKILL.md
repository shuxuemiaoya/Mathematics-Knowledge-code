---
name: question-type-content-segmentation
description: Split immutable hierarchy content into functional nodes and stable-ID atomic question notes without changing source content. Use after reviewed hierarchy coverage passes and before answer matching.
---

# Question Type Content Segmentation

Read `references/content-manifest.md`. Plan from the immutable hierarchy corpus,
then apply the passed manifest with `scripts/segment_content.py`. Map literal
labels only through reviewed adapter roles, keep each top-level question and its
subparts together, preserve source content, and emit standalone direct-child
Obsidian embeds without list prefixes or generated question headings.
