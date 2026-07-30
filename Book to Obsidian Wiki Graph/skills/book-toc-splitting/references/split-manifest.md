# TOC-Based Split Manifest

Create `split-manifest.json` after TOC heading formatting. The TOC defines the parent hierarchy; the LLM may add nested semantic child ranges inside each TOC section.

For textbooks, the split manifest is not sufficient by itself. After its
ranges stabilize, create and pass the source-ordered
`lesson-flow-manifest.json` defined in `lesson-flow-manifest.md`. If lesson-flow
review changes a boundary, update the split manifest first and regenerate the
lesson-flow draft so its frozen digest remains valid.

For textbooks, create the first draft with
`scripts/plan_split_manifest.py`. Its `review_required` output is a deliberate
review gate, not a failure. Review any low-confidence item and any proposed
unnumbered independent teaching arc before running the splitter.

```json
{
  "schema_version": 1,
  "profile": "C:/.../book-profile.json",
  "source_sha256": "<frozen book digest>",
  "input_markdown_sha256": "<formatted Markdown digest>",
  "semantic_review": {
    "headings": [
      {
        "line": 230,
        "title": "1.1.1 集合的含义",
        "decision": "split",
        "node_key": "topic-set-meaning",
        "confidence": 0.98
      },
      {
        "line": 260,
        "title": "思考",
        "decision": "retain",
        "reason": "Presentation block handled by Markdown standardization.",
        "confidence": 0.99
      },
      {
        "line": 390,
        "title": "习题1.1",
        "decision": "split",
        "node_key": "exercise-1-1",
        "confidence": 0.99
      }
    ],
    "sections": [
      {
        "node_key": "lesson-1-1",
        "title": "1.1 集合的概念",
        "start_line": 200,
        "end_line": 410,
        "decision": "split",
        "child_node_keys": ["topic-set"],
        "reason": "The definition and its examples form an independent teaching arc.",
        "confidence": 0.97,
        "reviewed_entire_section": true
      }
    ],
    "ranges": [
      {
        "node_key": "topic-set",
        "title": "集合",
        "start_line": 215,
        "end_line": 252,
        "decision": "split",
        "reason": "Complete definition, notation, and examples are reusable together.",
        "independent_teaching_arc": true,
        "confidence": 0.97
      }
    ]
  },
  "nodes": [
    {
      "key": "book-root",
      "title": "书名",
      "parent_key": null,
      "category": "root",
      "filename": "书名.md",
      "start_line": 1,
      "end_line": 8000,
      "toc_key": null
    },
    {
      "key": "lesson-1-1",
      "title": "1.1 集合的概念",
      "parent_key": "chapter-1",
      "category": "knowledge",
      "filename": "1.1 集合的概念.md",
      "start_line": 200,
      "end_line": 410,
      "toc_key": "lesson-1-1"
    },
    {
      "key": "topic-set",
      "title": "集合",
      "parent_key": "lesson-1-1",
      "category": "knowledge",
      "filename": "集合.md",
      "start_line": 215,
      "end_line": 280,
      "toc_key": null
    }
  ]
}
```

## Planning rules

- Include exactly one parentless `root` node covering the complete formatted
  Markdown.
- Additional child nodes may use category `root` only for book-wide standalone
  back matter such as an index or glossary; write them at book root and retain
  their own TOC heading.
- Assign every TOC key to exactly one split node.
- Keep child ranges inside their parent range.
- Keep sibling ranges disjoint and in source order.
- Retain unnumbered non-TOC child ranges in the nearest TOC note by default.
  Split one only when it is a complete, independently reusable teaching arc.
- Review every H4-H6 content heading exactly once and record confidence. A
  split decision names its node; an unnumbered split also records a specific
  independence reason and `independent_teaching_arc: true`. A retain decision
  records why the block belongs in its parent.
- The deterministic draft marks every sufficiently long generated knowledge
  node `review_required` in `semantic_review.sections`, including numbered
  H4-H6 subsection nodes. Read the complete body and replace that state with
  `split` or `retain`,
  `reviewed_entire_section: true`, a specific reason, and confidence.
- Independent teaching arcs without source headings are valid child nodes.
  Record each one in `semantic_review.ranges`; its title and exact bounds must
  match the node, and the splitter adds an H3 entry heading while preserving
  the complete original range.
- A same-edition reference-range proposal records
  `matched_reference_ratio`. Require at least `0.85` before treating it as a
  review candidate; otherwise retain `incomplete-reference-body-match` and
  inspect the missing tail before approving exact bounds.
- Route decisions below
  `decomposition.semantic_split_confidence_threshold` through the coordinator
  review queue and mark them `reviewed: true` only after resolution.
- Numbered textbook subsections (`6.1.1`, `8.4.2`, and so on) are mandatory `knowledge` nodes.
- Section exercises (`习题6.1`, `习题8.4`, and so on) are mandatory `exercise` nodes.
- Leave introductions, transitions, and ordinary lesson practice in the parent unless intentionally split.
- The splitter replaces every direct child range with a Markdown link in the parent at that exact source position.
- Parent navigation links are bullet items. A reviewed H4-H6 range that becomes
  its own note is promoted to an H3 entry heading.
- Disambiguate repeated generic chapter children with the chapter name:
  `<章名> 小结` and a chapter-qualified `复习参考题`, including in the filename.
- Flatten source namespaces such as `images/<book>/part-001/<hash>.jpg` to the
  owning category's `images/<hash>.jpg`; fail on unequal same-name assets.
- Preserve complete source blocks; do not summarize them.

## Categories

For textbooks, always enable and use:

- `knowledge` → `知识点`
- `concept` → `概念`
- `exercise` → `习题`

Enable only source-supported auxiliary roles:

- `reading` → `趣味阅读`
- `history` → `数学历史`
- `method` → `思维或方法`
- `tool` → `工具`

Do not create an auxiliary directory when no node owns that role.

Use `concept` only for a range that appears to contain a complete formal definition. Such files are candidates until the following concept-extraction stage validates them; categorization alone is not proof.

For non-textbooks, let the LLM propose semantic categories, then record those roles and directories in `book-profile.json` before creating the split manifest.

## Example behavior

A lesson parent should retain its heading, introduction, transition text, ordinary practice, and exercise links. A moved topic body becomes a child note, while the parent contains a link such as:

```markdown
- [集合](集合.md)
```

or the profile-equivalent vault-root target. The link must appear where that child block originally occurred.
