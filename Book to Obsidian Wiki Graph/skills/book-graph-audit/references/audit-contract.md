# Audit Contract

Run progressive gates:

1. `split` after TOC splitting: require identity, coverage, links, and assets.
2. `concepts` after extraction: additionally require the concept manifest and concept integrity.
3. `formatting` after standardization: additionally reject residual functional blocks and formatting defects.
4. `pre-canvas` before semantic graph planning.
5. `final` after canvas compilation when `canvas.enabled` is true.

Require a machine-readable report with `schema_version`, `stage`, `status`,
profile/source identity, `errors`, `warnings`, and counts.

## Failure conditions

- source digest changed;
- a coverage unit is missing, duplicated, or blocked;
- a required lesson-flow manifest is missing, stale, unresolved, incomplete,
  non-contiguous, or inconsistent with split child ranges;
- a same-book reference is configured but the lesson-flow-bound split manifest
  lacks its passed reviewer-confirmed semantic review, matching reference
  identity, or matching proposal-report digest;
- a required node-architecture review is missing or unresolved, a section
  directly owns an example/question atom, a practice organizer owns a section
  exercise, a knowledge-theme mixes unrelated node types, or recursive
  expansion changes source order;
- a reviewed node is physically flattened outside its direct owner's folder,
  or an owner is not represented by a same-named folder-index note;
- a section organizer retains teaching prose, or a source atom/second-layer
  organizer begins with an artificial filename heading;
- an empty Markdown or concept note exists;
- a node with `emit_title: true` does not begin with a valid H1-H3 entry
  heading;
- a concept note lacks `# <concept name>` or `## 定义`;
- a concept definition contains a functional callout marker, H4-H6 teaching
  heading, worked-example label, or practice boundary;
- a concept has no resolving inbound definition link;
- a Markdown, image, or canvas link does not resolve;
- a configured vault-root Markdown note link lacks its leading slash;
- a forbidden Wikilink remains;
- a top-level callout is malformed or violates the profile spacing rule;
- a `quoted-body` callout has no quoted body, becomes discontinuous because a
  body/formula/image/table/caption line lost its `>` prefix, or contains a
  nested marker whose body lacks the required `> >` prefix;
- a callout's semantic scope crosses a new functional boundary: a situation
  callout contains a functional heading or formal definition, a functional
  label is duplicated in the body, a non-example callout contains a worked
  example, a worked example contains a later example, or any callout contains
  ordinary lesson practice;
- a functional textbook block remains unstandardized, including plain observation/thinking/exploration headings or worked-example lines outside callouts;
- an OCR-only ornament heading or categorized-page running publisher heading
  remains after Markdown standardization;
- a plain chapter running header, OCR-split digit group inside TeX, or
  structurally malformed HTML table remains after Markdown standardization;
- a formal definition has unbalanced parentheses, an example solution contains
  a numbered subpart missing from the example stem, or an explicit reasoning
  label remains flattened at the parent callout depth;
- canvas JSON is invalid;
- node IDs collide;
- an edge endpoint is absent;
- a node or edge color is outside the profile palette.

Only enforce a condition once its owning stage is due. For example, the split
gate does not require a concept manifest and does not reject raw functional
blocks that Markdown standardization owns. Never relax conditions already due.

Do not treat a script exit code or a successful canvas compilation as completion. Completion requires the appropriate audit report to say `status: passed`.
