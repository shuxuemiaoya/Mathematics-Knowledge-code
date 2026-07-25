---
name: book-graph-concepts
description: Extract only formally defined concepts from TOC-split book notes, write complete flat concept notes with resolving source links, replace the first defining occurrence in each source note with one standard Markdown link, and produce a concept manifest. Use immediately after book-toc-splitting and before Markdown standardization, following the supplied 概念提取与Markdown排版美化 prompt's concept-extraction contract.
---

# Book Graph Concepts

Own concept extraction only. Do not standardize general Markdown, redesign split boundaries, or change TOC-aligned H1-H3 headings.

## Inputs

Require a valid profile, matching coverage manifest, and completed TOC split. Read `references/concept-extraction.md`, derived from:

```text
C:\Mathematics-Knowledge\Mathematics-Knowledge-code\Exam Paper Organizer\skills\概念提取与Markdown排版美化.md
```

If the profile disables concepts, record the stage as skipped.

## Extract

Process each non-concept note independently:

1. Validate every concept-category candidate produced by splitting.
2. Block and return an invalid candidate to the split manifest; do not silently preserve or recategorize it.
3. Identify additional concepts formally defined inside non-concept notes.
4. Reject undefined terms and concepts defined only in another note or chapter.
5. Copy the complete definition without truncation.
6. Write one flat concept file without silently overwriting a split candidate.
7. Include a resolving source-note link in the concept file.
8. Replace the first defining occurrence in the source note with one Markdown link.
9. Leave later repetitions unchanged.
10. Record accepted and rejected candidates in `concept-manifest.json`.

Compute the link path from the profile and source-note location. The root-note form is `[概念名](概念/概念名.md)`; categorized notes must use its resolving relative or vault-root equivalent.

## Gate

Require every accepted concept file to contain the complete definition and a valid source link, every definition occurrence link to resolve, each concept to be linked at most once per source file, and every rejected candidate to remain unmaterialized. Then invoke `book-graph-markdown`.
