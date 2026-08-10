# Book To Obsidian Wiki Graph Agent Contract

This directory is a standalone multi-skill agent. It does not use MathOS Agent for PDF conversion, heading formatting, or splitting.

## Components

| Skill | Ownership |
| --- | --- |
| `book-to-obsidian-wiki-graph` | sequence, strict handoffs, same-run recovery, review queues, note workplans, telemetry, and completion |
| `book-graph-intake` | source inventory and per-book profile |
| `book-pdf-to-markdown` | forced-OCR book PDF conversion |
| `book-toc-formatting` | TOC-authoritative H1-H3 and automatic demotion |
| `book-toc-splitting` | TOC hierarchy, lesson-flow review, categorized notes, and parent links |
| `book-graph-concepts` | formal definitions and concept links |
| `book-graph-markdown` | post-split Markdown standardization |
| `book-graph-audit` | pre-canvas and final validation |
| `book-graph-canvas` | optional graph manifest and canvas compilation |
| `book-graph-metadata` | batch Frontmatter metadata tagging and validation |

Each stage skill is authoritative for its own rules. Do not copy its implementation into the coordinator.

## Required Sequence

```text
source and profile
  -> book PDF conversion when needed
  -> TOC heading formatting
  -> split-manifest, same-book reference-range review when configured, and lesson-flow review
  -> TOC splitting immediately after both pass
  -> split audit
  -> concept extraction
  -> concept audit
  -> Markdown standardization
  -> formatting audit
  -> pre-canvas audit
  -> optional canvas and same-series style-parity gate
  -> metadata tagging (book-graph-metadata)
  -> final audit
```

Do not insert `mathos-pdf-to-md`, `mathos-formatting`, or `mathos-segmentation`.

## Artifact Interfaces

- `source-inventory.json`
- `book-profile.json`
- raw Markdown and extracted assets
- `toc-manifest.json`
- TOC-formatted Markdown and `toc-format-report.json`
- `split-manifest.json`
- `lesson-flow-manifest.json` for new textbook profiles
- categorized notes and `coverage-manifest.json`
- `concept-manifest.json`
- audit reports
- `pipeline-state.json`, optional `review-queue.json`, `note-workplan.json`, and `note-results.json`
- optional `graph-manifest.json`, `.canvas`, and `canvas-style-report.json`
- `metadata-report.json`

Every machine-readable handoff carries the same absolute profile path and frozen source digest. Markdown-derived stages also carry their immediate input digest.

The coordinator runtime validates these interfaces before stage completion.
Resume is limited to the current conversion state: never reuse or cache output
from another book or an older run.

## TOC Rules

- Treat the printed TOC as the sole authority for H1-H3.
- Demote every content heading absent from the TOC to H4-H6 automatically.
- Match every TOC entry once and in printed order.
- Continue directly from a passed formatting report into splitting.
- Use the TOC as the parent hierarchy; allow reviewed nested semantic ranges within each TOC section.
- Reject a TOC-only textbook manifest: review every H4-H6 heading with
  confidence, split all numbered subsections and section exercises, retain
  unnumbered non-TOC blocks by default, and require an explicit independent
  teaching arc for any exception.
- Review the complete content of every long generated knowledge node,
  including H2-H3 lessons and H4-H6 numbered subsections. The review must find
  independent teaching arcs even when their source range has no explicit
  heading; a deterministic heading inventory is only the draft.
- When the profile freezes a `same-book-content-and-style` reference, run the
  reference semantic proposal immediately after the deterministic split draft,
  review every candidate and ambiguity, and adopt the confirmed ranges before
  lesson-flow planning. The physical splitter must reject a same-book profile
  whose split manifest lacks identity-bound reference-review evidence.
- Review every numbered lesson and numbered in-lesson subsection as contiguous
  source-ordered logical blocks before splitting. Resolve every automatic
  lesson-flow finding. Keep situation introductions and transitions in the
  lesson entry, move independent topics to child notes, route exercises
  intentionally, and give every retained worked example its own logical
  block. Treat functional headings or labels, worked-example labels, formal
  definition/exposition cues, and practice headings as hard boundaries: one
  reviewed block may not cross the next boundary.
- Reject lesson entries that contain only links or that retain an oversized
  independent teaching block. Require the same passed lesson-flow manifest in
  splitting, Markdown standardization, and progressive audits.
- Replace each moved child range with a resolving Markdown link at that same source position in the parent.
- Ensure generic nodes receive contextual titles and filenames: `小结` → `<章名> 小结`, `复习参考题` → `<章名> 复习参考题`, `习题` → `习题<编号> <对应小节标题>` (例如: `习题10.1 随机事件与概率`).

## Categories

For textbooks, always enable:

- `knowledge` → `知识点`;
- `concept` → `概念`;
- `exercise` → `习题`.

Enable `reading` → `趣味阅读`, `history` → `数学历史`, `method` →
`思维或方法`, or `tool` → `工具` only when supported by the printed TOC/source
and recorded in the profile. Never create empty auxiliary directories.

For non-textbooks, inspect the book and let the LLM propose useful categories. Record them in `book-profile.json` before splitting.

## Preservation And Safety

- Default output root (`vault_root`) to `/Users/oven/Documents/ovenmathmap`.
- Preserve the relative input directory structure when deriving `book_root` under `vault_root` (e.g. `/Users/oven/Documents/ovenmathmap/<input_relative_path>/<book_folder>`).
- Treat the source PDF or source Markdown as immutable.
- Keep staging outside the final book directory.
- Preserve complete content, source order, formulas, tables, links, images, examples, proofs, and exercises.
- For textbooks, default note links to vault-root form and materialize image links from `links.asset_mode`.
- Do not let pre-canvas audit pass while functional headings or raw worked-example markers remain unstandardized.
- For textbook callouts, use quoted-body containers. Every body line, formula,
  image, HTML row, caption, and blank line inside a callout must retain its
  `>` prefix. Example analysis and solutions use nested `> >` callouts.
- Reconstruct callout ownership during formatting audit. Reject a situation or
  question callout that swallows a new functional heading, formal definition,
  worked example, or practice block; reject a second example or practice block
  nested under an earlier example solution.
- Never infer replacement of an existing target.
- Under a no-backup policy, use staging and atomic writes rather than backup directories.
- Route low-confidence or ambiguous decisions to a blocking review queue.
- Parallelize only independent notes from a frozen workplan with one owner per note and output path.
- Require the final applicable audit to pass before completion.
- Before a Canvas-enabled series build, freeze an explicitly named or
  deterministically discovered same-series sibling Canvas in the profile.
  When configured, require the identity-bound style report to pass; iterate
  layout instead of completing with `style_review_required`.
- When the same-book reference contains a canvas, use its reviewed domain
  groups and placement as the first canvas plan, rebase only resolving current
  notes, then add current-only source-supported nodes. Do not replace the
  reference layout with a chapter-only grid.
- If a same-book reference is introduced after splitting, invalidate the old
  split, lesson flow, notes, concepts, formatting, and canvas. Rebind intake and
  rerun from the deterministic split draft; never treat final parity or canvas
  comparison as retroactive approval of the old decomposition.

## Global Discovery

Keep canonical skills here and expose each through a junction under:

```text
C:\Users\Oven\.codex\skills
```

Do not maintain copied duplicates.
