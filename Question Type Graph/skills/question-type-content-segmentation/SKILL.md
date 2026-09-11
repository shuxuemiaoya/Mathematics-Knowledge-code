---
name: question-type-content-segmentation
description: Split immutable hierarchy content into functional nodes and stable-ID atomic question notes without changing source content. Use after reviewed hierarchy coverage passes and before answer matching.
---

# Question Type Content Segmentation

Read `references/content-manifest.md`. Plan from the immutable hierarchy corpus,
then apply the passed manifest with `scripts/segment_content.py`. Map literal
labels only through reviewed adapter roles, keep each top-level question and its
subparts together, preserve source content, and emit standalone direct-child
Obsidian embeds without list prefixes or generated question headings. For synchronized
lecture workbooks, enforce dual-scope isolation via `question_scopes`: bind worked-examples
(`variant-example`) exclusively to question-type sections, bind exercises (`numbered-exercise`)
exclusively to training sections, and strictly exclude theory/knowledge outline sections. Emit
atomic questions and answers directly into the respective type's subfolder (`{folder}/questions/`,
`{folder}/answers/`).
