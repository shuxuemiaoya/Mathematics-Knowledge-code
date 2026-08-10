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
  --format-preset "<optional-path-free-series-preset.json>" `
  --canvas --output "<staging>/question-type-profile.json"

python skills/question-type-graph/scripts/question_type_graph.py run "<profile>"
python skills/question-type-graph/scripts/question_type_graph.py resume "<profile>"
python skills/question-type-graph/scripts/question_type_graph.py status "<profile>"
python skills/question-type-graph/scripts/question_type_graph.py audit "<profile>" --overwrite
```

Unknown formats always stop after `format-inventory.json` and receive an
unapproved `format-adapter.draft.json`. Physical splitting begins only after
`format-adapter.json` is explicitly marked `passed` and
`reviewer_confirmed: true`. Missing, duplicate, weak, or conflicting answer
evidence remains a blocking review queue; fuzzy similarity is advisory only.
After a reviewer confirms that an authoritative answer is genuinely absent,
set the answer manifest to `status: passed` and `reviewer_confirmed: true`.
The coordinator then emits `supplemental-solutions-manifest.json`; only substantive
reviewer-confirmed supplemental solutions can satisfy the strict explanation
audit.

For books with a printed TOC, `hierarchy.primary_authority.entries` is a
complete source-ordered ledger. Every chapter, section, subsection, lesson,
topic, comprehensive drill, assessment, and reinforcement entry must appear
once before splitting can pass. Repeated labels such as training bands remain
children of those entries. If OCR omits a body heading, a reviewed source-bound
anchor may emit the exact TOC title as Markdown structure without rewriting the
source body.

Knowledge-point links are intentionally absent in this phase. Profiles,
manifests, Canvas output, and audits report `knowledge_linking: deferred`.

`resume` is idempotent: stages are reused using input fingerprints, and a
rebuilt upstream stage invalidates its descendants. Question IDs are persisted
in the vault-level `.question-type-graph/question-id-registry.json` under a
cross-process lock so unchanged questions are not renumbered.
Set `content.question_repository_root` in the reviewed adapter, or the
`QUESTION_TYPE_REPOSITORY_ROOT` environment variable, when the initial registry
must seed its numeric floor from an additional central question repository.

CLI commands return exit code `2` for `review_required`, `1` for failure, and
`0` for completed or passed results.

## Development verification

Use Python 3.10 or newer:

```bash
python -m pip install -e '.[test]'
python -m pytest
```
