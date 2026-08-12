# MinerU Local-File Batch Contract

1. Request signed upload URLs with `POST /api/v4/file-urls/batch`.
2. Upload each local part directly with `PUT` and no content-type header.
3. Poll `GET /api/v4/extract-results/batch/{batch_id}`.
4. Download `full_zip_url`, extract `full.md`, images, and every MinerU
   `content_list` JSON artifact, then merge parts in source-page order.

Always submit:

```json
{
  "files": [{"name": "part.pdf", "data_id": "stable-id", "is_ocr": true}],
  "model_version": "vlm",
  "language": "ch",
  "enable_formula": true,
  "enable_table": true
}
```

One uploaded file may contain at most 200 pages and 200 MB. Split locally when
either threshold is exceeded. Treat missing `full.md`, missing result URLs,
failed states, incomplete parts, unsafe zip paths, unresolved assets, or source
hash drift as terminal failures. Never log bearer tokens or signed URLs.
Preserve content-list files per PDF part with their hashes in the conversion
report. These raw page indices and block records are the evidence bridge from
an atomic question back to the printed page; a conversion without them is not
eligible for final audit.
Prefer the non-v2 content list when both variants exist, because it carries an
explicit `page_idx` per block; fall back to v2 page-array position. Translate
part-local indices through the frozen split ranges, exclude running
headers/footers from text matching, and retain page, bbox, block type, and
match method in `source-provenance-index.json`.
