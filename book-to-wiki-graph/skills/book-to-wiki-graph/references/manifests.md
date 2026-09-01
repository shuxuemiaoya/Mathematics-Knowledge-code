# Manifest Contracts

## `book-profile.json`

`scripts/init_book.py` creates the frozen run profile:

```json
{
  "schema_version": 1,
  "source": {
    "path": "/absolute/book.pdf",
    "sha256": "<sha256>",
    "kind": "pdf"
  },
  "paths": {
    "staging_root": "/absolute/staging",
    "book_root": "/absolute/vault/book"
  },
  "atom_categories": {
    "knowledge": "原子层/知识点",
    "worked-example": "原子层/例题",
    "exercise": "原子层/习题",
    "scenario": "原子层/情景引入"
  },
  "organizer_root": "组织层",
  "canvas": {"enabled": true}
}
```

## `book-graph.json`

Create this reviewed manifest after TOC extraction and complete atomization:

```json
{
  "schema_version": 1,
  "profile": "/absolute/staging/book-profile.json",
  "source_sha256": "<same source digest>",
  "source_markdown": "/absolute/staging/book.raw.md",
  "source_markdown_sha256": "<markdown digest>",
  "review": {
    "status": "passed",
    "reviewed_entire_book": true,
    "toc_hierarchy": "passed",
    "source_coverage": "passed",
    "atom_link_free": "passed"
  },
  "excluded_ranges": [
    {"start": 1, "end": 20, "reason": "Printed table of contents"}
  ],
  "nodes": [
    {
      "key": "book",
      "title": "Book title",
      "layer": "organizer",
      "parent_key": null,
      "organizer_level": 1,
      "filename": "组织层/Book title/Book title.md",
      "heading_ranges": [[21, 21]],
      "children": ["chapter-1"]
    },
    {
      "key": "atom-1",
      "title": "First idea",
      "layer": "atom",
      "parent_key": "chapter-1",
      "category": "knowledge",
      "filename": "原子层/知识点/First idea.md",
      "source_range": [30, 45]
    }
  ],
  "source_order": ["atom-1"],
  "relations": [
    {
      "key": "atom-1-supports-atom-2",
      "from_key": "atom-1",
      "to_key": "atom-2",
      "label": "supports",
      "evidence": "Source lines 42-45 explicitly introduce the later method."
    }
  ]
}
```

## Field rules

- Paths are absolute for profile/source fields and book-relative POSIX paths
  for node `filename`.
- Keys are unique stable strings. Filenames are unique case-insensitively.
- There is exactly one parentless node and it is an organizer at level 1.
- Organizer `children` is nonempty and lists every direct child exactly once.
- Atom `source_range` is `[start, end]`, inclusive and one-based.
- Organizer `heading_ranges` contains only source lines retained by that
  organizer rather than an atom.
- Exclusion ranges need a concrete reason; generic reasons such as `unused`
  are invalid.
- Relations are optional. Every endpoint must exist and `evidence` must be
  specific enough for review. They compile only into `semantics.canvas`, never
  into organization Canvas files.
- Every organizer's `children` order must agree with child source positions.
  An organizer's first heading range is its normal source anchor; when it has
  no heading range, the validator uses its earliest descendant.
- `review.status` remains `review_required` until the whole manifest and
  rendered corpus satisfy the architecture contract.
