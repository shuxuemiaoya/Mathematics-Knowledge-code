# MathOS Heading Expected Result Artifact Design

## Goal

Add one human-readable DeepSeek artifact to Step 3 that shows the expected heading result derived from the same `toc_and_headings.md` input used to generate the executable heading processor.

## Scope

The existing Step 3 artifacts and execution flow remain unchanged:

- `heading_processor_prompt.md`
- `heading_processor_response.py`
- `heading_processor.py`
- `stage1_heading_report.md`

Step 3 adds exactly one work artifact:

- `heading_expected_result.md`

A new repo prompt may be added under `skills/mathos-formatting/agents/`, but no additional prompt or raw-response file is written into the work directory.

## Provider Calls

Step 3 performs two focused DeepSeek calls using the exact same `heading_payload`, whose persisted form is `toc_and_headings.md`:

1. The existing call generates the Python heading processor.
2. A new call generates the human-readable expected result Markdown.

The calls are separate so each response has one output format and one responsibility. The expected-result call does not consume the generated Python, candidate Markdown, or Stage 1 report.

## Expected Result Contract

DeepSeek returns Markdown directly. The runtime saves the response unchanged as `heading_expected_result.md` after basic nonempty and structure validation.

The document must contain these top-level sections in this order:

```markdown
# 修改后的目录

# 标题修改明细

# 预期效果
```

Content requirements:

- `修改后的目录` presents the complete expected hierarchy as a bullet list of literal Markdown heading lines, such as ``- `## 1.1 集合` ``. This avoids confusing the artifact's own three H1 sections with the proposed book hierarchy.
- `标题修改明细` records each proposed change as `原标题 -> 预期标题`, including level-only changes and high-confidence OCR corrections.
- `预期效果` summarizes hierarchy normalization, TOC alignment, OCR corrections, and non-TOC heading demotions.
- The document must not contain executable Python, JSON, Markdown fences, or rewritten educational body content.
- TOC authority and the existing no-invented-parent-context rule remain binding.

## Runtime Behavior

When `heading_processor.py` does not exist, Step 3 keeps the current Python generation path and then performs the expected-result call.

When `heading_processor.py` is reused:

- reuse an existing nonempty, structurally valid `heading_expected_result.md`;
- if the expected-result file is missing or invalid, call DeepSeek only for that Markdown artifact;
- do not regenerate the existing Python processor solely because the Markdown artifact is missing.

The new artifact is explanatory and auditable. It does not modify the candidate, replace the local sandbox report, weaken Step 5 validation, or become an approval gate beyond being present and structurally valid.

## Failure Handling

Step 3 fails closed when the expected-result response is empty, contains forbidden formats, or lacks any required section. The raw invalid response is still written to `heading_expected_result.md`. Failure routing must point to this file when the second call fails, while Python-generation failures continue to route to `heading_processor_response.py`.

Provider failures propagate through the existing Step 3 failure path. The original source and candidate safety rules remain unchanged.

## Tests

Focused tests will prove:

- both provider calls receive the identical `heading_payload`;
- the Python call retains its existing prompt and output contract;
- the Markdown call writes `heading_expected_result.md` with all required sections;
- no extra work-directory prompt or response artifact is created for the Markdown call;
- an existing valid expected-result file is reused;
- a missing expected-result file is regenerated without regenerating `heading_processor.py`;
- empty, malformed, fenced, JSON, or Python-like Markdown responses fail closed;
- the full guarded formatter suite continues to pass.

## Acceptance

The change is accepted when a real Step 3 run produces the original four files plus `heading_expected_result.md`, both provider calls use the same `toc_and_headings.md` payload, the expected-result file satisfies the three-section contract, all guarded tests pass, and the source Markdown remains unchanged.
