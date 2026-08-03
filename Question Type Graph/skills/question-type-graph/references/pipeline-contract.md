# Pipeline Contract

| Stage | Required input | Output | Gate |
| --- | --- | --- | --- |
| Intake | typed sources and paths | `question-type-profile.json` | immutable source hashes and valid source arrangement |
| PDF conversion | profile PDF role | raw Markdown, assets, report | forced OCR and complete ordered coverage |
| Format inventory | registered raw Markdown | `format-inventory.json` | review all uncertain hierarchy, parsed TOC references, wrapped entries, labels, numbering, layout, and answer regions |
| Hierarchy | passed adapter | hierarchy and coverage manifests, entry notes | every primary-authority ledger entry is represented exactly once and every source line has one owner |
| Content | hierarchy corpus | functional nodes, atomic question notes, manifest | no output collisions or unresolved label review |
| Answers | atomic questions and optional answer source | answer-match manifest and appended exact answer blocks | one exact match per enabled question; fuzzy evidence never auto-passes |
| Markdown | complete notes | standardization report | lexical signature unchanged |
| Canvas | passed manifests | graph manifest and `.canvas` | no atomic question cards or invalid endpoints |
| Audit | complete corpus | final report | source hashes, content hashes, links, answers, and Canvas pass |

The coordinator may stop with `review_required`. Resume only after updating the
identity-bound adapter or review artifact; do not bypass the owning stage.
