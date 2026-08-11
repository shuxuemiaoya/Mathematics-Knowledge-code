# Pipeline Contract

| Stage | Required input | Output | Gate |
| --- | --- | --- | --- |
| Intake | typed sources and paths | `question-type-profile.json` | immutable source hashes and valid source arrangement |
| PDF conversion | profile PDF role | raw Markdown, assets, report | forced OCR and complete ordered coverage |
| Format inventory | registered raw Markdown and optional frozen preset hints | `format-inventory.json` | review all uncertain hierarchy, parsed TOC references, wrapped entries, labels, numbering, layout, and answer regions; no built-in publisher vocabulary |
| Hierarchy | passed adapter | hierarchy and coverage manifests, entry notes | every primary-authority ledger entry is represented exactly once, every source line has one owner, and each direct child is embedded once with a standalone `![[...]]` |
| Content | hierarchy corpus and schema-valid adapter patterns | functional nodes, headingless atomic question notes, manifest | no output collisions, unresolved label review, list-prefixed embeds, or generated atomic-question headings; virtual-line provenance remains raw-addressable |
| Title cleanup | generated content titles and filenames | cleaned titles and corresponding filenames | only Unicode letters, digits, and `_` remain; every other character, including whitespace, `：`, punctuation, symbols, and emoji, is replaced with `_`; immutable OCR text and question bodies remain unchanged |
| Answers | atomic questions, optional answer source, and schema-valid adapter patterns | answer-match manifest and standalone answer notes containing both `【答案】` and `【解析】` | every accepted match is exact and uniquely owned; every note has both fields; choice answers are exact; unresolved questions require explicit review before supplementation; fuzzy evidence never auto-passes |
| Solution supplement | reviewed unmatched questions | provenance-marked AI solution notes and application report | substantive solution text and `reviewer_confirmed: true`; placeholders never apply |
| Markdown | complete notes | standardization report | lexical signature unchanged |
| Canvas | passed manifests | graph manifest and `.canvas` | no atomic question cards or invalid endpoints |
| Audit | complete corpus | final report | source hashes, content hashes, links, answers, and Canvas pass |

The coordinator may stop with `review_required`. Resume only after updating the
identity-bound adapter or review artifact; do not bypass the owning stage. When
an authoritative answer is genuinely absent, explicitly approve that answer
review result, resume to generate `supplemental-solutions-manifest.json`, add and
review the worked solution, apply it, then resume the coordinator.
Persist reviewer-authored reusable solutions in
`reviewed-supplement-overrides.json`, keyed by question identity and body
digest, so safe pipeline replays do not erase reviewed work.
