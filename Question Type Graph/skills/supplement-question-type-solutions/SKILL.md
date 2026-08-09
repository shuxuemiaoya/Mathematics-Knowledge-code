---
name: supplement-question-type-solutions
description: Scan Question Type Graph for unmatched atomic question notes (answer_status unmatched), invoke AI solution generation for missing material, format collapsable solution callouts (Q*A1.md) with header AI生成解析, and embed solution links in question notes. Use after question-answer-matching when authoritative textbook OCR has gaps.
---

# Supplement Question Type Solutions

Scan Question Type Graph for atomic question notes whose `answer_status` is `unmatched`, generate AI worked solutions for missing material, and embed solution callouts.

```bash
# 1. Plan unmatched questions manifest
python3 -m question_type_graph.supplement plan "<profile_path>"

# 2. Generate AI solutions and embed solution callouts (Q*A1.md)
python3 -m question_type_graph.supplement apply "<profile_path>" "<staging>/supplemental-solutions-manifest.json" --callout-title "AI生成解析"
```

## Hard Rules

1. **Isolation of Authoritative Matching**: Never modify or overwrite source-exact authoritative answer matching results. Only process question notes with `answer_status: unmatched`.
2. **Callout Header Distinction**: Mark AI-generated solutions clearly with callout title `> [!faq]- AI生成解析` (or custom `--callout-title`) to distinguish them from textbook OCR answers (`全练一本通解析`).
3. **Embed Link Preservation**: Save generated solution callout notes in the `questions/answers/` folder as `Q*A1.md`, update frontmatter `answer_status: ai-generated`, and append `![[Q*A1]]` to the question note.
