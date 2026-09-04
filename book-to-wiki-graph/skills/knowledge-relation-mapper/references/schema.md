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
`motivates`, `illustrates`, `applies`, `practices`, `contrasts`, and `analogous`.

JSON is authoritative. Atom Markdown remains link-free and unchanged.
