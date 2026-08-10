---
name: book-graph-concepts
description: Extract only formally defined concepts from TOC-split book notes, write complete flat concept notes with resolving source links, replace the first defining occurrence in each source note with one standard Markdown link, and produce a concept manifest. Use immediately after book-toc-splitting and before Markdown standardization, following the supplied 概念提取与Markdown排版美化 prompt's concept-extraction contract.
---

# Book Graph Concepts

Own concept extraction only. Do not standardize general Markdown, redesign split boundaries, or change TOC-aligned H1-H3 headings.

## Inputs

Require a valid profile, matching coverage manifest, and completed TOC split. Read `references/concept-extraction.md`, derived from:

```text
C:\Users\Oven\OneDrive\桌面\新建文件夹 (3)\概念提取与Markdown排版美化.md
```

If the profile disables concepts, record the stage as skipped.

## Extract

Process each non-concept note independently:

1. Validate every concept-category candidate produced by splitting.
2. Block and return an invalid candidate to the split manifest; do not silently preserve or recategorize it.
3. Identify additional concepts formally defined inside non-concept notes.
4. Reject undefined terms and concepts defined only in another note or chapter.
5. Copy the complete definition without truncation, but do not copy surrounding
   exploration, counterexample, worked-example, or practice blocks merely
   because they occur before the naming sentence.
6. Write one flat concept file without silently overwriting a split candidate.
7. Include a resolving source-note link in the concept file.
8. Replace the first defining occurrence in the source note with one Markdown link.
9. Leave later repetitions unchanged.
10. Record accepted and rejected candidates in `concept-manifest.json`.

Every generated concept note uses the stable example structure:

```markdown
# 概念名

来源：[来源页](/课本/.../知识点/来源页.md)

## 定义

完整定义正文
```

When extraction decisions have been reviewed, record their exact source range,
anchor text, and linked term in a per-book candidate JSON, then run
`scripts/apply_concept_candidates.py`. This deterministically copies the
definition, creates the flat concept note, writes the source backlink, replaces
only the reviewed defining occurrence, and writes the manifest. Do not use the
script to decide which terms qualify as concepts. If a defining term is inside
LaTeX, retain it in the source and reject the candidate unless another complete,
linkable defining occurrence exists.

Use the smallest source-derived range that contains the complete formal
definition. A reviewed range must not cross a functional callout, H4-H6
teaching heading, worked-example label, or practice boundary. If the definition
requires separated source passages, record ordered, non-overlapping
`definition_segments` instead of widening one range across the intervening
teaching block. Each segment uses `start_line` and `end_line`; copied segments
remain verbatim and in source order. The segment containing `anchor_text`
controls the one source-link replacement.

When a human-reviewed concept directory from the same edition is available,
use it only as a reviewed term list to reduce rediscovery:

```powershell
python .\skills\book-graph-concepts\scripts\plan_concept_candidates.py `
  "<book_root>" `
  "<reviewed_same_edition_concept_directory>" `
  "<staging>\concept-candidates.json"
```

Review the resulting source ranges against the current split notes. Do not copy
old concept bodies, accept an unmatched term, or treat the planner's
`review_required` result as approval. Pass `--reject-term "<name>"` for a term
whose located current-source occurrence is only an example, label, or
incomplete definition; the rejection remains explicit in the candidate JSON.
The planner recognizes formal variants such as `称…是`, `就说`, and
`判断为`, including parallel terms in one definition sentence, but every
located candidate still requires review.
For a reviewed canonical name shaped like `X的Y`, also recognize a source
surface that inserts only a mathematical object label between `X` and `的`
(for example, `X $A$ 的Y`). Preserve that complete source surface as the
Markdown link text while keeping the canonical filename and concept name.
When one term has several matches, rank direct naming evidence such as
`叫做集合`, `称为子集`, or `定义为...` ahead of a generic noun merely
following `我们说`, `就说`, or `并且说`. Source-path order must not decide
between those evidence classes.
Also rank a general construction beginning with `一般地`, `通常`, or a
domain-and-condition statement ahead of an earlier concrete worked example.
For a concept whose name ends in `公式` or `方程`, require its reviewed
definition range or segments to contain an actual TeX equation; a naming
sentence with only a symbol reference is incomplete.

The planner writes `status: review_required` and `reviewed: false`. Before
materialization, review every exact range, resolve all `review_flags`, set each
accepted item to `reviewed: true`, and set the payload status to `approved`.
`apply_concept_candidates.py` must reject an unapproved payload.

Compute the link path from the profile and source-note location. The root-note form is `[概念名](概念/概念名.md)`; categorized notes must use its resolving relative or vault-root equivalent.

Assign confidence to extraction decisions. Route low-confidence, ambiguous,
unresolved, or conflicting candidates through the coordinator review queue.
Do not complete this stage while a routed item is undecided.

## Gate

Require every accepted concept file to contain the complete definition and a
valid source link, every definition occurrence link to resolve, each concept to
be linked at most once per source file, and every rejected candidate to remain
unmaterialized. Reject a generated definition that still contains a functional
callout marker, teaching heading, worked-example label, or practice boundary.
Require `book-graph-audit --stage concepts` to pass, then invoke
`book-graph-markdown`.
