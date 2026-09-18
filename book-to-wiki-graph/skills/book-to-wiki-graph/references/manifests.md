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
    "scenario": "原子层/情景引入",
    "concept": "原子层/概念",
    "formula": "原子层/公式"
  },
  "atom_subcategory_paths": {
    "reflection-question": "原子层/思考题"
  },
  "atomization": {
    "mode": "llm-category-aware-graph",
    "knowledge_granularity": "complete-teaching-unit",
    "scenario_policy": "preserve-and-role-classify-activities",
    "activity_prompt_policy": "preserve-marker-and-explicit-disposition",
    "confidence_threshold": 0.90,
    "short_atom_confidence_threshold": 0.95,
    "teaching_role_audit": "integrated",
    "relation_feedback_cycles": 2,
    "knowledge_boundary_authority": "llm-exclusive",
    "provisional_atom_policy": "coverage-context-only",
    "parallel_definition_policy": "split-when-independently-reusable",
    "scoped_introduction_policy": "one-source-complete-atom-per-owner",
    "knowledge_motivation_policy": "complete-problem-or-context"
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
    "atom_filename_policy": "per-folder-sequence-category-code",
    "leaf_organizer_policy": "flat-note",
    "organizer_frontmatter_policy": "required",
    "organizer_self_heading_policy": "omit",
    "organizer_child_heading": "relative-depth",
    "organizer_filename_policy": "clear-title",
    "concept_filename_policy": "preferred-label-collision-safe"
  },
  "organizer_root": "组织层",
  "canvas": {
    "enabled": true,
    "mode": "three-level-constellation",
    "theme": "adaptive",
    "overview_granularity": "chapter",
    "chapter_granularity": "core-atom",
    "section_granularity": "atom-and-exercise-entry",
    "concept_nodes": "hidden",
    "formula_nodes": "hidden",
    "isolation_policy": "semantic-or-labelled-membership",
    "png_preview": "required-every-canvas",
    "png_width": 2400,
    "review": {
      "mode": "llm-png-two-pass",
      "scope": "every-canvas",
      "required_before_completion": true,
      "max_optimization_cycles": 2
    }
  }
}
```

Every Markdown file under `组织层/` begins with organizer frontmatter. Required
properties are `title`, `node_type: organizer`, `organizer_key`,
`parent_organizer_key`, `parent_organizer`, `parent_organizer_file`,
`source`/`source_pdf`, `source_sha256`, `organizer_level`, `organizer_role`,
`hierarchy_path`, `heading_ranges`, `source_anchor`, `children_count`,
`direct_organizer_count`, `direct_atom_count`, `descendant_atom_count`,
`updated_at`, and `review_status`. Parent fields are explicit `null` for the
book root. `organizer_role` is one of `root`, `branch`, `mixed`, or `leaf` and
describes direct-child composition rather than a subject-specific chapter
type. Generated concept/formula index notes use the same fields with a stable
`derived-index:<chapter-key>:<category>` key.

In category-aware mode each file under `原子层/` starts with frontmatter
properties. The common properties are `title`, `atom_type`, `atom_key`,
`owner_key`, `source`/`source_pdf`, `source_sha256`, `source_range`, `used_by`,
`organizers`, `updated_at`, `review_status`, `estimated_learning_minutes`,
`difficulty`, `importance`, and `learning_objectives`. Knowledge notes
additionally include `prerequisites` and
`keywords`; scenarios include `scenario_role`, worked examples
`complete_solution`, exercises `exercise_scope`, and concept/formula cards
`derived_from`. Concept cards set `is_definition_card: true` and contain only
definition-form source text (not examples or prompts); inline illustrative
clauses on the same physical line are clipped only in the derived card, never
in the parent knowledge atom.

Concept Markdown uses its canonical concept label as the filename. If two
distinct concepts normalize to the same filename, append a deterministic short
hash to both; do not fall back to a meaningless sequence number.
The canonical label is the term being defined, not an editorial phrase such as
`X 的定义` or `X 的概念、格式与约定`. A virtual graph concept without formal
definition-form evidence has no Markdown card and therefore no
`derived_atom_key`.

`scenario_role: reflection-question` uses `原子层/思考题/NNNN-T.md`. Its
primary category remains `scenario`, so relation analysis and Canvas treat it
as an inquiry that can be motivated by learned knowledge while storage and
search distinguish it from chapter/section introductions.

The full role set is `book-introduction`, `chapter-introduction`,
`section-introduction`, `knowledge-motivation`, and `reflection-question`.
Each scoped introduction (`book`, `chapter`, or `section`) occurs at most once
under one owner and is the owner's first direct child. It includes all
contiguous introductory paragraphs, questions, figures and captions before the
next structural heading. Continuation and image-only fragments are invalid.
`knowledge-motivation` instead targets one knowledge topic and preserves its
complete problem/context and final question.

`scenario_role: section-introduction` is a direct child of the section and its
first direct child. It may be short when it explicitly starts from prior
knowledge and asks a framing question answered by several following sibling
topics. It is not owned by the first topic. Inline practice atoms are owned by
the knowledge topic they exercise; only the terminal formal exercise-set
organizer remains a direct child of the section.

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
    "mode": "llm-category-aware-graph",
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
- Atom filenames contain no prose title. Primary files use a sequence that
  restarts in each destination folder plus a category code: `K` knowledge,
  `W` worked example, `E` exercise, `S` scenario, and `T` reflection question.
- A leaf organizer with only atom children is a clearly named `.md` file in its
  parent's directory. Only organizers that own organizer children retain their
  own directory. An organizer note omits its own duplicated title. Every
  organizer-child embed in a
  parent note is immediately preceded by that child's root-relative heading:
  top-level `#`, second-level `##`, third-level `###`, capped at `H6`. A terminal
  organizer that directly embeds atoms omits headings and contains only the
  ordered atom embeds.
- Atom notes omit structural Markdown heading syntax from their audited source
  ranges; printed activity markers such as `思考` and `观察` remain as plain
  source lines. Their human-readable `title` remains metadata and an
  organizer/Canvas label.
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
- Every child subtree's latest source position must precede the next sibling's
  earliest position. A printed non-exercise organizer with only exercise
  descendants is invalid. Category-aware graphs require a passed digest-bound
  `organizer_review`; its absence blocks preparation, materialization, and
  final validation.
- `review.status` remains `review_required` until the whole manifest and
  rendered corpus satisfy the architecture contract.
- `atomization` is optional for legacy profiles. New profiles default to the
  category-aware graph configuration shown above; `llm-two-pass` remains readable.
- Category-aware profiles also declare `knowledge_boundary_authority:
  llm-exclusive`, `provisional_atom_policy: coverage-context-only`, and
  `parallel_definition_policy: split-when-independently-reusable`, plus
  `scoped_introduction_policy: one-source-complete-atom-per-owner` and
  `knowledge_motivation_policy: complete-problem-or-context`. These fields
  make clear that LLM semantic judgment, not deterministic paragraph splitting,
  controls knowledge-atom boundaries.
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

## v0.7 additions

- `atomization-final.json` may contain `knowledge_signatures`,
  `local_relations`, `derived_card_candidates`, and `feedback_cycle`.
- A pre-materialization `relation-final.json` binds
  `atomization_final_sha256` and may contain `boundary_feedback`. It cannot be
  materialized until status is `passed`, feedback is empty, and unresolved
  count is zero.
- `source_order` contains primary `knowledge`, `worked-example`, `exercise`,
  and `scenario` atoms only. `derived_order` contains `concept` and `formula`
  atom keys. Every derived node has `coverage_role: derived`,
  `derived_from_key`, and a range contained by its primary source.
- `formulas[]` records the normalized expression, variables, conditions,
  evidence range, and source atom. Canonical `concepts[]` and formulas may
  expose their deterministic `derived_atom_key` after materialization.
- `derived_indexes[]` records per-chapter concept/formula index notes. These
  notes are discoverability artifacts, not organizer-tree or Canvas nodes.
