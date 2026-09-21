---
name: book-graph-metadata
description: Batch derive, inject, and validate Obsidian Frontmatter File Properties (Metadata) for Obsidian Wiki Graph notes based on book profile, node types, chapter structures, and educational taxonomy rules (Source, Grade, Node Type, Chapter, Duration, Difficulty, Importance, Tier). Use after Markdown standardization and canvas compilation, as the final post-processing step before final audit.
---

# Book Graph Metadata

Batch inject and validate YAML Frontmatter File Properties (Metadata) into Obsidian Wiki Graph notes based on `book-profile.json` and note properties.

## Inputs

Require a valid `book-profile.json` in staging and an existing book note tree under `book_root`.
Also require `coverage-manifest.json` and, when concepts are enabled,
`concept-manifest.json` in staging. Their profile/source identities must match.
The actual Markdown inventory must equal their combined targets before tagging;
unmanaged existing notes block the batch rather than receiving inferred metadata.

## Metadata Injection & Tagging Rules

Each Markdown note receives a standard YAML Frontmatter header:

```yaml
---
来源: 2019 人教A 数学 必修二
年级: 高一
节点类型: 知识点
章节: 第六章 平面向量及其应用
时长: 30分钟
难度: 易
重要程度: 必须深度理解
推荐层级: B
---
```

### Metadata Fields Derivation Rules

1. **来源 (Source)**:
   - Taken from `profile["book"]["edition"]` or `profile["book"]["title"]` (or CLI `--override-source`).
2. **年级 (Grade)**:
   - Derived from book edition/title (e.g. `必修一`, `必修二` -> `高一`; `选择性必修一/二/三` -> `高二`) or CLI `--override-grade`.
3. **节点类型 (Node Type)**:
   - For an architecture-reviewed textbook, derived first from
     `split-manifest.json`; directory role is only a fallback:
     - `organizer` -> `目录` plus `组织类型` (`全书`/`章节`/`小节`/`知识主题`/`练习`/`习题`)
     - `scenario` -> `情景导入`
     - `knowledge` -> `知识点`
     - `worked-example` -> `例题`
     - question atoms -> `习题`
   - Without architecture metadata, derive from directory role or path stem:
     - `概念/` -> `概念`
     - `知识点/` -> `知识点`
     - `拓展知识点/` -> `拓展知识点`
     - `思维或方法/` -> `思维或方法`
     - `习题/` -> `习题`
     - `趣味阅读/` -> `趣味阅读`
     - `工具/` -> `工具`
     - `index.md` -> `目录`
     - `索引/` -> `索引`
4. **章节 (Chapter)**:
   - Derived from the chapter folder name (e.g., `01-第一章_集合与常用逻辑用语` -> `第一章 集合与常用逻辑用语`).
5. **时长 (Duration)**:
   - Estimated from node type and length:
     - `概念`: `15分钟`
     - `知识点`/`工具`/`方法`: `30分钟`
     - `习题`: `45分钟` ~ `60分钟`
     - `趣味阅读`: `20分钟`
     - `目录`/`索引`: `60分钟`
6. **难度 (Difficulty)**:
   - `简单` | `易` | `难`
7. **重要程度 (Importance)**:
   - `必须深度理解` | `理解` | `熟悉即可` | `知道就行` | `非必学`
8. **推荐层级 (Recommended Tier)**:
   - `D` | `C` | `B` | `A` | `A+`

## Script

Run metadata tagging:

```powershell
python scripts\tag_book_metadata.py "<book_root>" `
  --profile "<staging>\book-profile.json" `
  --split-manifest "<staging>\split-manifest.json" `
  --output "<staging>\metadata-report.json"
```

The script validates the entire owned batch, checks its original input hashes,
then replaces individual files atomically and outputs `metadata-report.json`
outside the book tree. A detected edit during preparation blocks publication.

## Gate

- All Markdown notes must contain valid YAML frontmatter delimiters (`---`).
- All 8 required metadata fields must be present and hold valid values.
- For general books, only source and node type are required; textbook grade and
  educational estimates are not synthesized.
- Every `目录` node must also carry `组织类型`; do not infer a source atom's
  type solely from its containing directory when reviewed architecture exists.
