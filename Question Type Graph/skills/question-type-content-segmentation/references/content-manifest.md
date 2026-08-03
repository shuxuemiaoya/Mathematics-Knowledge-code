# Content Manifest

Adapter role regexes map source labels to semantic roles. A numeric `depth`
expresses containment: a later block is a child of the nearest active block
with lower depth. Question regexes require a named `number` capture.

Hierarchy ownership is established before this stage. Functional labels such
as training bands are children of the current TOC note and cannot redefine or
flatten the primary hierarchy.

When numbering restarts inside repeated training bands, mark that functional
role as an answer-context owner. Questions inherit the nearest owning context;
otherwise they retain their hierarchy context. Numeric question `0` is rejected
by default so decimal prose such as `0.618` cannot become an atomic question.

The plan records for each functional node and question:

- stable identity and semantic role;
- exact source note and line range;
- nearest frozen PDF-part/page-range marker plus preserved MinerU block artifacts;
- parent identity and answer context;
- collision-free output path;
- source-body SHA-256 for every atomic question.

Application writes folder notes for functional nodes and one leaf per
top-level question. Subparts remain inside their owning question. Exact source
blocks are wrapped in provenance markers; parent notes receive ordered links.
Never duplicate a moved body.

Application records every generated functional/question leaf and prunes only
previously recorded leaves that are no longer in the new manifest. The final
audit treats any unmanifested Markdown note in the dedicated graph root as a
stale-output error.
