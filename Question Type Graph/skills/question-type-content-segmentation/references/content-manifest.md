# Content Manifest

Adapter role regexes map source labels to semantic roles. A numeric `depth`
expresses containment: a later block is a child of the nearest active block
with lower depth. Question regexes require a named `number` capture.

When numeric syntax also appears in theory or instructions, configure
`content.question_scopes`. A candidate must lie inside at least one reviewed
role, hierarchy context, or local source range. Record excluded numeric
candidates in the manifest for auditability; do not hide false positives in an
ever-growing global regex when a semantic section boundary exists.

When OCR omits a printed training-band label and exercise roles would otherwise
become children of a theory block, use `content.detached_role_folders`. Each
reviewed rule names `from_ancestor_role`, a non-empty list of exercise `roles`,
and the independent `folder`. Matching roots become siblings of the theory
block, the theory range ends before the first detached root, and descendants
remain attached to their exercise root. Folder labels belong in the adapter,
not reusable compiler vocabulary.

Hierarchy ownership is established before this stage. Functional labels such
as training bands are children of the current TOC note and cannot redefine or
flatten the primary hierarchy. Existing hierarchy embeds are hard range
boundaries and must survive content splitting. A source line accepted by a
question-number rule cannot also be classified as a functional node, even when
an adapter contains a catch-all neutral-context rule.

When numbering restarts inside repeated training bands, mark that functional
role as an answer-context owner. Questions inherit the nearest owning context;
otherwise they retain their hierarchy context. Numeric question `0` is rejected
by default so decimal prose such as `0.618` cannot become an atomic question.

The plan records for each functional node and question:

- stable identity and semantic role;
- exact source note and line range;
- original raw Markdown line and exact PDF page/bbox when the MinerU evidence
  index resolves it, otherwise every retained candidate or nearest part range;
- parent identity and answer context;
- collision-free output path;
- source-body SHA-256 for every atomic question.

Application writes folder notes for functional nodes and one leaf per
top-level question. Subparts remain inside their owning question. Exact source
blocks are wrapped in provenance markers; parent notes receive one standalone,
vault-relative `![[path/to/note.md]]` embed at the moved block's original
position. Generated embeds are never list items. Atomic question leaves do not
receive a generated question-title heading. Never duplicate a moved body.

Application records every generated functional/question leaf and prunes only
previously recorded leaves that are no longer in the new manifest. The final
audit treats any unmanifested Markdown note in the dedicated graph root as a
stale-output error.
