---
name: supplement-question-type-solutions
description: Add substantive reviewer-confirmed AI solutions only where authoritative answer matching remains unresolved. Use after the answer-review gate emits a supplemental-solutions manifest.
---

# Supplement Question Type Solutions

Run `python -m question_type_graph.supplement plan <profile>` after authoritative
matching identifies unmatched questions. Populate each selected manifest item
with a substantive `solution` and `reviewer_confirmed: true`, then apply it.
Never modify authoritative matches or create placeholder answers. Mark accepted
notes `ai-generated-reviewed`, record their hashes and provenance, and embed
them only in the owning unmatched question.
