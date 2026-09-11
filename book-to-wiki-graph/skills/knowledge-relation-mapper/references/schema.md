# Dual-layer graph contract

## Canonical concepts

`concepts[]` contains stable `key`, `preferred_label`, unique aliases,
definition, `kind`, source evidence, source chapters, first source order, and the
proposal IDs merged into it. Kinds are:

`concept`, `definition`, `property`, `theorem`, `rule`, `procedure`,
`representation`, `method`.

Merge only when meanings match in the book context. A name match or embedding
score is insufficient. Merge confidence must be at least `0.97`; homonyms,
definition conflicts, or alias collisions remain separate and enter review.

## Atom-concept links

`atom_concept_links[]` uses roles:

`introduces`, `explains`, `derives`, `triggered_by`, `motivates`, `illustrates`,
`applies`, `practices`, `assumes`.

Each link contains exact evidence ranges inside its atom and a confidence. The
link explains the atom's instructional function; it is not a vague topical tag.
A `section-introduction` has at least one `motivates` link and atom-projection
edge to the first knowledge unit answering its framing question. It needs no
incoming edge; unlike `knowledge-motivation`, it frames a section rather than
bridging two already distinct knowledge units.

## Concept relations

`concept_relations[]` uses only:

`prerequisite`, `develops`, `derives`, `broader`, `part_of`, `contrasts`,
`analogous`.

No `related` relation exists. `contrasts` and `analogous` are canonicalized as
unordered pairs; other relations are directed. Each edge records `tier`,
`evidence_kind`, exact two-end evidence, rationale, confidence, and candidate
source IDs.

## Atom projection

`relations[]` remains compatible with Canvas. It projects reviewed teaching
logic onto atoms and stores `basis_keys` for the canonical concept relations
that justify it. Projection types remain `prerequisite`, `develops`, `derives`,
`motivates`, `illustrates`, `applies`, `practices`, `contrasts`, `analogous`,
and `synthesizes`.

JSON is authoritative. Atom Markdown remains link-free and unchanged.

## Boundary feedback

`relation-final.json.boundary_feedback[]` contains `feedback_id`, `action`,
`atom_keys`, their resolved `atom_ids`, a complete `proposed_ranges` partition,
exact evidence, rationale, and confidence. Feedback is valid only for virtual
atoms bound through `atomization_final_sha256`; it blocks materialization.
