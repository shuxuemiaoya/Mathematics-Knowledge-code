# Canvas Manifest And Logic Grammar

## Contents

1. Manifest schema
2. Node grammar
3. Edge grammar
4. Link rules
5. Layout rules
6. Compilation and validation

## 1. Manifest Schema

Create a UTF-8 JSON manifest in task-scoped staging:

```json
{
  "version": 1,
  "profile": "C:/.../book-profile.json",
  "source_sha256": "<same digest as the profile>",
  "nodes": [
    {
      "key": "chapter-1",
      "type": "group",
      "label": "第一章 集合与常用逻辑用语",
      "x": 0,
      "y": 0,
      "width": 2200,
      "height": 1800
    },
    {
      "key": "knowledge-set",
      "type": "text",
      "text": "[集合](课本/示例/知识点/集合.md)",
      "x": 320,
      "y": 240,
      "width": 260,
      "height": 70,
      "color": "2"
    }
  ],
  "edges": [
    {
      "key": "chapter-1-to-set",
      "from": "chapter-1",
      "to": "knowledge-set",
      "fromSide": "right",
      "toSide": "left"
    }
  ]
}
```

Use stable, meaningful `key` values. The compiler derives 16-character SHA-256 IDs from keys. Do not reuse a key.

Supported node types:

- `group`
- `text`

Required group fields:

- `key`, `type`, `x`, `y`, `width`, `height`
- optional `label`, `color`

Required text fields:

- `key`, `type`, `text`, `x`, `y`, `width`, `height`
- optional `color`

Required edge fields:

- `from`, `to`
- optional `key`, `label`, `color`, `fromSide`, `toSide`, `fromEnd`, `toEnd`

## 2. Node Grammar

Use groups for:

- whole chapters;
- coherent lesson/topic clusters;
- larger mathematical domains when useful.

Use text cards for:

- lesson entry notes;
- substantial knowledge topics;
- formal concepts;
- exercises;
- methods and thinking;
- readings/history;
- tools;
- selected formulas or source-supported annotations.

Default mathematics-textbook color meanings:

| Color | Node class |
| --- | --- |
| `1` | super-core knowledge |
| `2` | knowledge point or concept |
| `3` | interdisciplinary/outside-chapter knowledge |
| `4` | thinking method or technique |
| `5` | story/history/reading |
| `6` | question type |
| `#c800ff` | mathematical tool |
| absent | organizational/neutral |

Read actual allowed colors from `book-profile.json`. The table above is the default profile, not a compiler constant. Do not color every node.

## 3. Edge Grammar

Use an unlabeled, uncolored edge for:

- containment;
- chapter or lesson order;
- lesson entry to split topic;
- lesson entry to exercise;
- local grouping.

Use named edges sparingly for genuine mathematical relationships supported by the source:

- definition or generalization;
- necessary/sufficient implication;
- inverse operation;
- transformation;
- method transfer;
- parameter effect;
- application.

Default mathematics-textbook edge colors:

| Color | Relation |
| --- | --- |
| `2` | reasoning/inference |
| `4` | inspiration/method transfer |
| `5` | calculation |
| `6` | application |
| absent | containment/classification/sequence |

Read actual allowed colors from `book-profile.json`. Do not use a semantic color without a source-supported relationship.

## 4. Link Rules

Inside canvas text, use standard Markdown links with a vault-root path:

```markdown
[集合](课本/【人教版】高中必修%20第一册数学电子课本/知识点/集合.md)
```

Requirements:

- include `.md`;
- encode spaces as `%20` when the vault convention requires it;
- keep Chinese filename text unchanged;
- resolve every decoded path against `vault_root`;
- do not copy source-file-relative links into a canvas card without rebasing them.

## 5. Layout Rules

Treat the canvas as a knowledge logic map:

- place chapters by mathematical domain, not just book order;
- keep geometry, algebra, functions, statistics, and practice regions coherent;
- place prerequisite topics before or near dependent topics;
- keep a chapter group large enough to contain its topic clusters;
- place side material near the knowledge it supports;
- avoid isolated book-wide rectangles;
- avoid exact card overlap;
- keep edge directions visually meaningful.

The manifest is reviewable semantic planning. Do not use the compiler to invent placement or mathematical relations.

## 6. Compilation And Validation

Compile:

```powershell
python scripts\build_canvas.py `
  "<staging>\graph-manifest.json" `
  "<book-root>\<book>.canvas" `
  --vault-root "<vault-root>" `
  --profile "<staging>\book-profile.json"
```

The compiler validates:

- manifest version;
- supported node types;
- required fields and positive dimensions;
- unique keys and generated IDs;
- allowed node and edge colors;
- edge endpoints;
- Markdown links in node text;
- output-exists gate.

Then run `audit_obsidian_graph.py --require-canvas` for a fresh final check.
