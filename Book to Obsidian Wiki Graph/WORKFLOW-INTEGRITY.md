# Workflow integrity and recovery

Install the agent's Python dependency in the environment that runs its scripts:

```sh
python3 -m pip install -r requirements.txt
```

PyYAML is required for typed frontmatter. Existing list, mapping, boolean and
multiline values are parsed and round-tripped; malformed or duplicate keys are
rejected. Metadata preparation validates the whole batch before writing each
file atomically. General books receive source/type fields rather than inferred
high-school grades. Textbook heuristic estimates carry `元数据估算` provenance.
The final audit parses and validates the actual frontmatter again.

Formatting and metadata stages resolve owned notes from the profile-bound
coverage and concept manifests before writing. Missing or unmanaged Markdown
files block the batch. A mixed existing vault requires a reviewed scope; it is
not automatically treated as a fresh agent output tree.

## Content evidence

The splitter checks that the root spans all formatted source lines and that
every node reaches the root. It checks owned source content against each
rendered note before moving asset paths. `coverage-manifest.json` records:

- `integrity.algorithm: book-content-v1`;
- the frozen formatted source path, SHA-256 and line count;
- expected node keys and explicit printed-TOC exclusions;
- each node's non-overlapping `owned_ranges`;
- each rendered note's ordered `content_sha256` and existing link destinations.

Audits require every non-excluded source line to have exactly one owner and
all expected units to remain present. Content fingerprints ignore frontmatter,
approved Markdown wrappers, and documented running-header artifacts. They
retain ordered words, punctuation, math/code literals and table data. Concept
link insertion may add a destination, but existing destinations must remain.
Concept manifests separately freeze their generated definition note content.

The fingerprint is evidence of preservation, not a mathematical correctness
proof. TOC/source selection and semantic decomposition still require the
existing reviews. OCR page inventory evidence likewise establishes enumerated
output pages, not recognition accuracy on every page.

## Approved content changes

Presentation formatting does not repair formula digits automatically. Use
`apply_reviewed_content_repairs.py` for explicit reviewed corrections. Each
operation must include its exact `before_sha256`, `reason`, and source
`evidence`. Its report binds the review recipe and before/after content hashes.
Pass reports in order through `audit_obsidian_graph.py --content-repair-report`.
The original coverage/concept baselines remain unchanged; an audit follows the
reviewed transformation chain. Arbitrary corpus edits still fail.

## Reports and recovery

Use a separate staging directory for each run and retain it until completion.
The runtime binds reports to current files, not just to `status: passed`.
TOC completion checks source input, manifest and candidate hashes; corpus
reports include whole-tree snapshots. Audits also freeze input evidence files.
PDF completion requires the persisted conversion report and actual returned
page indices, Markdown digest and asset snapshot.

Split publication keeps a staged tree and coverage record before the directory
rename. Concept and reviewed-repair writes use a roll-forward journal with
before/after hashes for the complete write set. Repeat the same command to
finish an interrupted publication. A changed input or unexpected target edit
blocks recovery instead of overwriting user work. These journals belong to one
run; they are not cross-book or cross-run caches. They are not a filesystem-wide
atomic transaction, so do not read a corpus as complete before its stage passes.

Publishers keep original read hashes, guard reused files as well as write
targets, and acquire an OS-backed journal lock. Each file is checked again
before replacement. Formatting and metadata use the same original-input guard
for their prepared batches. These checks detect intervening edits; they do not
lock external editors or provide filesystem-wide isolation.

Legacy coverage/manifests and reports without this evidence do not qualify for
a new passed gate. Regenerate them from the frozen source in a new staging and
output location, or explicitly review a migration. Do not fill in hashes from
an already edited corpus merely to silence a failure, and do not delete an
existing target to make a retry proceed.

## Regression checks

Run each skill's unittest discovery with that skill's `scripts` on `PYTHONPATH`,
then run `python3 -m unittest discover -s tests`. Cross-component regressions
cover lost conditions/formulas/table cells, partial source coverage, stale
reports, interrupted publications, reviewed repair chains, nested YAML, missing
OCR output pages, and every coordinator stage for a general book without
concepts or Canvas. No live OCR request is part of these tests.
