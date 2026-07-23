---
name: order-exam-images-to-pdf
description: Infer the semantic reading order of an unordered collection of raster exam-page images and merge every image into one verified PDF without relying on filenames or visible page numbers alone. Use as the mandatory first Exam Paper Organizer stage when a selected folder contains screenshots or scans of exam questions, answer keys, worked solutions, or question-only pages; run it before reformatting, solution supplementation, image cleaning, or LaTeX/PDF publishing.
---

# Order Exam Images to PDF

Turn unordered exam screenshots or scans into one source-preserving PDF. Determine order from document structure and content continuity, record the evidence, then use the bundled script for deterministic inventory, merging, and integrity checks.

## Gate every downstream stage

Run this skill to a terminal state before invoking any other Exam Paper Organizer component.

- Continue downstream only after this stage is `completed`, or `not_applicable` because the selected folder contains no exam-page image collection.
- Block every downstream stage when page order remains ambiguous, an image cannot be decoded, a source changes during the run, or PDF verification fails.
- Treat `<folder>\images` as Markdown attachments rather than page scans when top-level Markdown files reference those images. Use it as page input only when the user identifies it as the scan collection or no Markdown source references it.
- Prefer images directly in the selected folder, then explicit `page-images` or `exam-images` subfolders. Do not combine separate candidate collections without user direction.

## 1. Inventory without assuming order

Use the Codex bundled Python runtime so Pillow, ReportLab, and pypdf are available.

```powershell
$env:PYTHONUTF8='1'
python <skill-dir>\scripts\exam_images_to_pdf.py inventory <image-folder> `
  --work-dir <folder>\tmp\organizer\<run-id>\image-ordering
```

Add `--recursive` only when nested folders are part of the same paper. The command writes `inventory.json`, contact sheets, and `order-manifest.template.json`. Treat contact-sheet order, filenames, filesystem timestamps, EXIF times, and visible page numbers only as clues; none establishes final order by itself.

Inspect every image. Open full-resolution images when contact-sheet text is too small. Record:

- title, instructions, section headings, question numbers, and answer/solution headings;
- incomplete sentences, formulas, tables, choices, or diagrams at page boundaries;
- matching bottom-to-top text, repeated overlap, and continuation indentation;
- question-range and answer-range progression;
- likely first and last pages;
- exact duplicates or unrelated captures.

## 2. Infer one semantic sequence

Build the sequence from content relationships.

1. Place title, directions, and the start of the first question section before later question pages.
2. Keep every split question, choice group, table, and figure with its continuation. Prefer a direct bottom-to-top continuation over page-number or filename evidence.
3. Follow section and question-number progression while accounting for a question that begins on one image and ends on the next.
4. Detect answer boundaries such as `答案`, `参考答案`, `解析`, `Answer`, or `Solutions`. When the source has a separate answer section, place it after the question section and order it by matching question coverage.
5. Preserve an evidently interleaved question-and-solution layout instead of forcing all answers to the end.
6. Use visible page numbers, filename numbers, capture times, dimensions, and lexical sorting only to corroborate the content-derived order.

For every adjacency, require a content-based reason. If two sequences remain plausible after full-resolution inspection, keep the stage `blocked`; do not guess or create the PDF.

## 3. Write the order manifest

Copy `order-manifest.template.json` to `order-manifest.json` and fill it only after inspection:

```json
{
  "schema_version": 1,
  "status": "ready",
  "document_pattern": "questions-then-separate-answers",
  "content_evidence": [
    "Question numbering and split-stem continuity establish every adjacency",
    "The answer heading begins only after the final question"
  ],
  "ambiguities": [],
  "ordered_images": [
    {
      "image_id": "IMG-0003",
      "confidence": "high",
      "reason": "Title and directions lead into question 1"
    },
    {
      "image_id": "IMG-0001",
      "confidence": "high",
      "reason": "Completes question 1 and begins question 2"
    }
  ]
}
```

List every inventory ID exactly once. Use only `high` or `medium` confidence in a ready manifest. Keep `ambiguities` empty. Do not silently drop duplicates; include them unless the user explicitly authorizes deduplication. If an image is not part of the same paper, stop at an input-scope gate rather than omitting or merging it without user direction.

## 4. Merge deterministically

Use the neutral default output name `<folder-name>（图片整理版）.pdf` in the selected folder unless the user specifies another path.

```powershell
python <skill-dir>\scripts\exam_images_to_pdf.py merge `
  --inventory <run-dir>\inventory.json `
  --order <run-dir>\order-manifest.json `
  --output <folder>\<folder-name>（图片整理版）.pdf
```

Do not overwrite an existing PDF without explicit user approval. The script rejects incomplete or ambiguous manifests, changed sources, duplicate IDs, missing IDs, low-confidence entries, and page-count mismatches. It writes `merge-report.json` and ordered preview sheets beside the manifest.

## 5. Verify before release

1. Confirm the script reports `page_count == ordered_image_count`.
2. Render the PDF pages to PNG with Poppler and inspect every page.
3. Compare the rendered sequence with the ordered preview and recheck every section transition, split question, and question-to-answer boundary.
4. Confirm all inventory SHA-256 values still match and the source images remain unchanged.
5. Report the image folder, ordered PDF, manifest, page count, ordering evidence, confidence, duplicate findings, and any warning.

Mark the stage `completed` only after visual verification shows the expected order, readable pages, no clipping, and no missing or duplicated image.
