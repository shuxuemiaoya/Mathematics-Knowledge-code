# Question Type Graph

A standalone, profile-driven agent for converting supplementary exercise books
into an Obsidian network of functional blocks and atomic top-level questions.
Publisher labels, page ranges, numbering rules, answer layouts, and folder
templates belong in a reviewed per-book `format-adapter.json`; reusable Python
contains no book-specific catalogue.

Generated parent-child navigation uses standalone vault-relative Obsidian
embeds (`![[path/to/note.md]]`) without list prefixes. Each parent embeds only
its direct children. Atomic question notes contain provenance and exact source
content but no generated question-title heading.

## Source arrangements

- `questions=<path>` plus `answers=<path>` for separate sources.
- `combined=<path>` with reviewed, non-overlapping regions.
- `questions=<path>` alone for deliberately unavailable answers.

PDF sources use forced MinerU OCR with `vlm`, formulas, and tables enabled.
Files above 200 pages or 200 MB are split into complete ordered ranges, and an
active remote batch can be resumed after a transient disconnect.

## Coordinator

```powershell
python skills/question-type-graph/scripts/question_type_graph.py init `
  --source "questions=<questions.pdf>" `
  --source "answers=<answers.pdf>" `
  --title "<book>" --staging-root "<staging>" `
  --vault-root "<vault>" --graph-root "<graph>" `
  --canvas --output "<staging>/question-type-profile.json"

python skills/question-type-graph/scripts/question_type_graph.py run "<profile>"
python skills/question-type-graph/scripts/question_type_graph.py resume "<profile>"
python skills/question-type-graph/scripts/question_type_graph.py status "<profile>"
python skills/question-type-graph/scripts/question_type_graph.py audit "<profile>" --overwrite
```

Unknown formats always stop after `format-inventory.json`. Physical splitting
begins only after `format-adapter.json` is explicitly marked `passed` and
`reviewer_confirmed: true`. Missing, duplicate, weak, or conflicting answer
evidence remains a blocking review queue; fuzzy similarity is advisory only.

For books with a printed TOC, `hierarchy.primary_authority.entries` is a
complete source-ordered ledger. Every chapter, section, subsection, lesson,
topic, comprehensive drill, assessment, and reinforcement entry must appear
once before splitting can pass. Repeated labels such as training bands remain
children of those entries. If OCR omits a body heading, a reviewed source-bound
anchor may emit the exact TOC title as Markdown structure without rewriting the
source body.

Knowledge-point links are intentionally absent in this phase. Profiles,
manifests, Canvas output, and audits report `knowledge_linking: deferred`.
