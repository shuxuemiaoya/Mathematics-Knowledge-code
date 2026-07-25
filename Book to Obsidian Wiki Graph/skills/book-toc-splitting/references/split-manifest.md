# TOC-Based Split Manifest

Create `split-manifest.json` after TOC heading formatting. The TOC defines the parent hierarchy; the LLM may add nested semantic child ranges inside each TOC section.

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
        "node_key": "topic-set-meaning"
      },
      {
        "line": 260,
        "title": "思考",
        "decision": "retain",
        "reason": "Presentation block handled by Markdown standardization."
      },
      {
        "line": 390,
        "title": "习题1.1",
        "decision": "split",
        "node_key": "exercise-1-1"
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

- Include exactly one `root` node covering the complete formatted Markdown.
- Assign every TOC key to exactly one split node.
- Keep child ranges inside their parent range.
- Keep sibling ranges disjoint and in source order.
- Use additional non-TOC child ranges for coherent topics, formal-definition blocks, and standalone exercises.
- Review every H4-H6 content heading exactly once. A split decision names its node; a retain decision records why the block belongs in its parent.
- Numbered textbook subsections (`6.1.1`, `8.4.2`, and so on) are mandatory `knowledge` nodes.
- Section exercises (`习题6.1`, `习题8.4`, and so on) are mandatory `exercise` nodes.
- Leave introductions, transitions, and ordinary lesson practice in the parent unless intentionally split.
- The splitter replaces every direct child range with a Markdown link in the parent at that exact source position.
- Preserve complete source blocks; do not summarize them.

## Categories

For textbooks, enable and use only:

- `knowledge` → `知识点`
- `concept` → `概念`
- `exercise` → `习题`

Use `concept` only for a range that appears to contain a complete formal definition. Such files are candidates until the following concept-extraction stage validates them; categorization alone is not proof.

For non-textbooks, let the LLM propose semantic categories, then record those roles and directories in `book-profile.json` before creating the split manifest.

## Example behavior

A lesson parent should retain its heading, introduction, transition text, ordinary practice, and exercise links. A moved topic body becomes a child note, while the parent contains a link such as:

```markdown
[集合](集合.md)
```

or the profile-equivalent vault-root target. The link must appear where that child block originally occurred.
