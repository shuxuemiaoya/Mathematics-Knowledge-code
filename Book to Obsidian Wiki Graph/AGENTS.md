# Book To Obsidian Wiki Graph Agent Contract

This directory is a standalone multi-skill agent. It does not use MathOS Agent for PDF conversion, heading formatting, or splitting.

## Components

| Skill | Ownership |
| --- | --- |
| `book-to-obsidian-wiki-graph` | sequence, handoffs, and completion |
| `book-graph-intake` | source inventory and per-book profile |
| `book-pdf-to-markdown` | forced-OCR book PDF conversion |
| `book-toc-formatting` | TOC-authoritative H1-H3 and automatic demotion |
| `book-toc-splitting` | TOC hierarchy, categorized notes, and parent links |
| `book-graph-concepts` | formal definitions and concept links |
| `book-graph-markdown` | post-split Markdown standardization |
| `book-graph-audit` | pre-canvas and final validation |
| `book-graph-canvas` | optional graph manifest and canvas compilation |

Each stage skill is authoritative for its own rules. Do not copy its implementation into the coordinator.

## Required Sequence

```text
source and profile
  -> book PDF conversion when needed
  -> TOC heading formatting
  -> TOC splitting immediately
  -> concept extraction
  -> Markdown standardization
  -> pre-canvas audit
  -> optional canvas
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
- categorized notes and `coverage-manifest.json`
- `concept-manifest.json`
- audit reports
- optional `graph-manifest.json` and `.canvas`

Every machine-readable handoff carries the same absolute profile path and frozen source digest. Markdown-derived stages also carry their immediate input digest.

## TOC Rules

- Treat the printed TOC as the sole authority for H1-H3.
- Demote every content heading absent from the TOC to H4-H6 automatically.
- Match every TOC entry once and in printed order.
- Continue directly from a passed formatting report into splitting.
- Use the TOC as the parent hierarchy; allow reviewed nested semantic ranges within each TOC section.
- Reject a TOC-only textbook manifest: review every H4-H6 heading, split all numbered subsections and section exercises, and record reasons for retained headings.
- Replace each moved child range with a resolving Markdown link at that same source position in the parent.

## Categories

For textbooks, enable only:

- `knowledge` → `知识点`;
- `concept` → `概念`;
- `exercise` → `习题`.

For non-textbooks, inspect the book and let the LLM propose useful categories. Record them in `book-profile.json` before splitting.

## Preservation And Safety

- Treat the source PDF or source Markdown as immutable.
- Keep staging outside the final book directory.
- Preserve complete content, source order, formulas, tables, links, images, examples, proofs, and exercises.
- For textbooks, default note links to vault-root form and materialize image links from `links.asset_mode`.
- Do not let pre-canvas audit pass while functional headings or raw worked-example markers remain unstandardized.
- Never infer replacement of an existing target.
- Under a no-backup policy, use staging and atomic writes rather than backup directories.
- Require the final applicable audit to pass before completion.

## Global Discovery

Keep canonical skills here and expose each through a junction under:

```text
C:\Users\Oven\.codex\skills
```

Do not maintain copied duplicates.
