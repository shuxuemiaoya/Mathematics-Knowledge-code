# Standalone Modular Pipeline

| Stage | Owner | Input | Output | Gate |
| --- | --- | --- | --- | --- |
| Intake | `book-graph-intake` | source and target | inventory, profile | frozen source identity |
| PDF conversion | `book-pdf-to-markdown` | PDF and profile | raw Markdown and assets | forced OCR, complete pages/assets |
| TOC formatting | `book-toc-formatting` | raw Markdown and printed TOC | TOC manifest, formatted Markdown, report | every TOC entry matched; other headings below H3 |
| TOC splitting | `book-toc-splitting` | formatted Markdown, TOC, split, same-book reference evidence when configured, and lesson-flow manifests | categorized notes, parent links, coverage | same-book reference ranges are reviewed before lesson flow; every lesson line receives one reviewed logical role; no block crosses a functional/definition/example/practice boundary; context and transitions remain in the entry; independent topics and exercises are routed; all targets resolve |
| Split audit | `book-graph-audit --stage split` | split corpus and coverage | audit report | identity, coverage, links, and assets pass |
| Concepts | `book-graph-concepts` | split notes and coverage | concept notes and manifest | formal definitions complete and linked |
| Concept audit | `book-graph-audit --stage concepts` | concept-linked corpus | audit report | concept manifest and links pass |
| Standardization | `book-graph-markdown` | concept-linked notes | standardized notes | protected fields unchanged; functional blocks become continuous quoted-body callouts, with nested analysis/solution callouts inside examples |
| Formatting audit | `book-graph-audit --stage formatting` | standardized corpus | audit report | Markdown rules, links, assets, callout continuity, and callout semantic ownership pass |
| Pre-audit | `book-graph-audit --stage pre-canvas` | complete note corpus | audit report | `status: passed` |
| Canvas | `book-graph-canvas` | passed notes, graph plan, approved same-book reference review, and frozen same-series style reference when configured | `.canvas`, graph manifest, and `canvas-style-report.json` when configured | compiler passes; retained same-book topology is preserved; same-series visual metrics pass |
| Final audit | `book-graph-audit --stage final` | final corpus | final report | `status: passed` |

TOC formatting and TOC splitting are one uninterrupted transition: a passed formatting report triggers splitting immediately.

JSON artifacts carry `schema_version`, absolute profile path, and frozen source digest. Formatting and splitting additionally carry the digest of their immediate Markdown input.

For textbook profiles with `decomposition.require_lesson_flow_manifest: true`,
`lesson-flow-manifest.json` is a required split-stage artifact. It freezes the
formatted source and split-manifest digests, covers every numbered lesson with
contiguous ordered blocks, and must report `status: passed`. The same artifact
is required by Markdown standardization and progressive audits.

The coordinator runtime owns stage state, schema and identity validation,
same-run resume, review queues, safe note workplans, and telemetry. It never
reuses outputs across books. Its optional test-checkpoint mode may restore a
completed stage across repeated tests only when the checkpoint still matches
the exact frozen source, profile, staging, and output identities. Component
skills own behavior, scripts, prompts, and validation.

If an intended corpus was named, also write `reference-parity-report.json` in
staging. It compares normalized heading grammar, navigation list form,
contextual filenames, asset depth, concept structure, OCR artifacts, and
per-chapter decomposition ratios. For common same-book notes it also compares
the source-ordered functional topology: callout type, label, quote depth, and
parent callout. Raw totals from different books are evidence only, not a parity
criterion.
The report must be bound to the frozen profile/source/reference identities and
must have `status: passed`; `content_review_required`,
`architecture_only_required`, or `failed` cannot complete the final stage.

If the intended corpus is the same book and edition, the report additionally
compares normalized body content. It must identify reference notes aggregated
inside larger current notes, rank same-path differences by bidirectional
containment, identify missing formal-concept titles, and report genuinely
unmatched text. A same-path `content_divergent` pair is blocking. Same-book
content parity cannot pass solely because source-line coverage, links, and
assets pass.
Normalization excludes complete Markdown heading lines so a shared filename
or title cannot inflate the evidence for short notes with different bodies.
After source-backed review, exact blocker keys may be accepted through an
identity-bound review-decisions artifact. Every decision requires a specific
reason, and the comparator must reject stale source/reference hashes. Missing
or unreviewed blocker keys remain blocking.

The same-book reference is also an upstream decomposition input. Immediately
after the deterministic split draft, generate the reference semantic proposal,
review its exact source ranges, adopt confirmed candidates, and freeze that
reference path/digest plus the proposal-report digest inside
`semantic_review.reference`. Physical splitting must reject missing or stale
same-book reference evidence.

A same-series sibling Canvas is a separate visual input frozen under
`canvas.style_reference`. It does not trigger cross-book content comparison.
After compilation, write `canvas-style-report.json` and iterate the manifest
until scale-independent grouping, nesting, aspect, card rhythm, annotation,
and edge styling metrics pass. Raw counts, sibling content, and legacy link
syntax are not parity criteria.

Use `scripts/compare_reference_content.py` to write
`reference-content-parity-report.json`; merge its blocking summary into the
normalized `reference-parity-report.json`.
