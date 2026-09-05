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
  "organization": {
    "mode": "toc-plus-reviewed-topics",
    "activity_heading_policy": "atom-content",
    "knowledge_topic_policy": "source-supported-reviewed"
  },
  "atom_categories": {
    "knowledge": "原子层/知识点",
    "worked-example": "原子层/例题",
    "exercise": "原子层/习题",
    "scenario": "原子层/情景引入"
  },
  "atomization": {
    "mode": "llm-two-pass",
    "knowledge_granularity": "complete-teaching-unit",
    "scenario_policy": "substantial-only",
    "confidence_threshold": 0.90,
    "short_atom_confidence_threshold": 0.95,
    "teaching_role_audit": "required-before-materialization",
    "role_correction_confidence_threshold": 0.95
  },
  "relation_analysis": {
    "mode": "llm-three-pass",
    "graph_model": "atom-concept-dual-layer",
    "concept_scope": "book",
    "explicit_confidence_threshold": 0.90,
    "inferred_confidence_threshold": 0.95,
    "concept_merge_threshold": 0.97,
    "cross_chapter": true,
    "candidate_retrieval": {
      "source_window": 2,
      "lexical_top_k": 8,
      "embedding": "optional",
      "embedding_top_k": 8,
      "graph_hops": 2,
      "max_ranked_candidates_per_atom": 12
    },
    "community_analysis": "wcc-required-leiden-optional"
  },
  "markdown_rendering": {
    "atom_heading_policy": "omit",
    "atom_filename_policy": "sequence-category-code",
    "leaf_organizer_policy": "flat-note",
    "organizer_self_heading_policy": "omit",
    "organizer_child_heading": "relative-depth"
  },
  "organizer_root": "组织层",
  "canvas": {
    "enabled": true,
    "mode": "three-level-constellation",
    "theme": "adaptive",
    "overview_granularity": "chapter",
    "chapter_granularity": "core-atom",
    "section_granularity": "atom-and-exercise-entry"
  }
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
  "organizer_review": {
    "status": "passed",
    "path": "/absolute/staging/organizer-review.json",
    "sha256": "<sealed artifact digest>",
    "demoted_organizer_keys": ["draft-observe-heading"],
    "synthesized_organizer_keys": ["topic-one"]
  },
  "atomization_review": {
    "status": "passed",
    "mode": "llm-two-pass",
    "final_artifact": {
      "path": "/absolute/staging/atomization-final.json",
      "sha256": "<sealed artifact digest>"
    },
    "bindings": {
      "jobs": {"path": "/absolute/staging/atomization-jobs.json", "sha256": "<digest>"},
      "round_1_decisions": {"path": "/absolute/staging/round-1-decisions.json", "sha256": "<digest>"},
      "round_2_jobs": {"path": "/absolute/staging/round-2-jobs.json", "sha256": "<digest>"},
      "round_2_decisions": {"path": "/absolute/staging/round-2-decisions.json", "sha256": "<digest>"},
      "atom_role_jobs": {"path": "/absolute/staging/atom-role-jobs.json", "sha256": "<digest>"},
      "atom_role_decisions": {"path": "/absolute/staging/atom-role-decisions.json", "sha256": "<digest>"}
    },
    "reviewer": {
      "round_1": {"type": "codex-agent", "model": "current-agent"},
      "round_2": {"type": "codex-agent", "model": "current-agent"}
    },
    "role_review": {
      "status": "passed",
      "reviewed_flagged_atoms": 12,
      "replaced_atoms": 5,
      "result_atoms": 240,
      "unresolved_count": 0
    },
    "unresolved_count": 0
  },
  "relation_review": {
    "status": "passed",
    "mode": "llm-three-pass",
    "graph_model": "atom-concept-dual-layer",
    "final_artifact": {
      "path": "/absolute/staging/relation-final.json",
      "sha256": "<sealed artifact digest>"
    },
    "bindings": {
      "concept_jobs": {"path": "/absolute/staging/concept-jobs.json", "sha256": "<digest>"},
      "round_1_concepts": {"path": "/absolute/staging/round-1-concepts.json", "sha256": "<digest>"},
      "relation_jobs": {"path": "/absolute/staging/relation-jobs.json", "sha256": "<digest>"},
      "round_2_relations": {"path": "/absolute/staging/round-2-relations.json", "sha256": "<digest>"},
      "graph_audit_jobs": {"path": "/absolute/staging/graph-audit-jobs.json", "sha256": "<digest>"},
      "round_3_audit": {"path": "/absolute/staging/round-3-audit.json", "sha256": "<digest>"}
    },
    "featured_example_keys": ["atom-method-example"],
    "unresolved_count": 0
  },
  "concepts": [
    {
      "key": "concept-0123456789abcdef",
      "preferred_label": "Canonical concept",
      "aliases": ["Source alias"],
      "definition": "A source-grounded reusable mathematical meaning.",
      "kind": "concept",
      "evidence": [{"atom_key": "atom-1", "source_range": [30, 35]}],
      "first_source_order": 30
    }
  ],
  "atom_concept_links": [
    {
      "key": "atom-concept-0123456789abcdef",
      "atom_key": "atom-1",
      "concept_key": "concept-0123456789abcdef",
      "role": "introduces",
      "evidence_ranges": [[30, 35]],
      "confidence": 0.99
    }
  ],
  "concept_relations": [],
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
      "filename": "原子层/知识点/0001-K.md",
      "source_range": [30, 45]
    }
  ],
  "source_order": ["atom-1"],
  "relations": [
    {
      "key": "relation-0123456789abcdef",
      "from_key": "atom-1",
      "to_key": "atom-2",
      "type": "prerequisite",
      "tier": "backbone",
      "evidence_kind": "pedagogical-inference",
      "evidence_ranges": [
        {"node_key": "atom-1", "source_range": [42, 45]},
        {"node_key": "atom-2", "source_range": [50, 52]}
      ],
      "rationale": "The second unit uses the first unit's definition and notation.",
      "confidence": 0.97,
      "basis_keys": []
    }
  ]
}
```

`featured_example_keys` is derived only from sealed relation concept signatures
whose role is `bridge` and whose atom category is `worked-example`. Canvas uses
it as an allow-list; it does not alter Markdown or relation endpoints.

## Field rules

- Paths are absolute for profile/source fields and book-relative POSIX paths
  for node `filename`.
- Keys are unique stable strings. Filenames are unique case-insensitively.
- Atom filenames contain no prose title. They use a global source-order number
  plus category code: `K` knowledge, `W` worked example, `E` exercise, or `S`
  scenario.
- A leaf organizer with only atom children is a numbered `.md` file in its
  parent's directory. Only organizers that own organizer children retain their
  own directory. Organizer notes omit their own title. Every organizer-child
  embed in a parent note is immediately preceded by its root-relative heading:
  top-level `#`, second-level `##`, third-level `###`, capped at `H6`.
- Atom notes omit all Markdown heading lines from their audited source ranges;
  their human-readable `title` remains metadata and an organizer/Canvas label.
- There is exactly one parentless node and it is an organizer at level 1.
- Organizer `children` is nonempty and lists every direct child exactly once.
- Atom `source_range` is `[start, end]`, inclusive and one-based.
- Organizer `heading_ranges` contains only source lines retained by that
  organizer rather than an atom.
- Exclusion ranges need a concrete reason; generic reasons such as `unused`
  are invalid.
- Relations are optional until relation review completes. New graphs carry
  source-grounded canonical `concepts`, `atom_concept_links`, reviewed
  `concept_relations`, and a compatible atom `relations` projection with
  `basis_keys`. They compile into chapter constellations and aggregate
  cross-chapter routes; they never modify atom Markdown.
- Every organizer's `children` order must agree with child source positions.
  An organizer's first heading range is its normal source anchor; when it has
  no heading range, the validator uses its earliest descendant.
- `review.status` remains `review_required` until the whole manifest and
  rendered corpus satisfy the architecture contract.
- `atomization` is optional for legacy profiles. New profiles default to the
  two-pass configuration shown above.
- When `profile.atomization.mode` is `llm-two-pass`, `atomization_review` is
  required. Every bound artifact must exist and match its sealed digest; the
  final artifact must be `passed`, have zero unresolved items, bind the same
  source Markdown digest, and match every materialized atom by owner, range,
  category, and title.
- Review artifacts use a canonical JSON digest stored as `artifact_sha256`.
  Editing an upstream packet invalidates downstream decisions.
- `organizer_review` is optional for legacy manifests. When present, its
  artifact digest and source Markdown digest must resolve; every demoted key
  must be absent and every synthesized topic key must be present in the final
  graph.
- `relation_analysis` is optional for legacy profiles. New profiles use the
  three-pass dual-layer defaults shown above. Legacy two-pass artifacts remain
  readable. Missing or unresolved relation review leaves
  the Markdown graph valid but permits only a relation-free book atlas.
- When `relation_review` is present, its final artifact and all bindings must
  exist, match their sealed digests and source Markdown, contain zero
  unresolved items, and exactly match manifest `concepts`,
  `atom_concept_links`, `concept_relations`, and `relations` in three-pass mode.
