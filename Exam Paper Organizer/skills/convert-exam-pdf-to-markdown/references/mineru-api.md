# MinerU API contract used by this skill

Source: [MinerU document parsing API documentation](https://mineru.net/apiManage/docs), checked 2026-07-23.

## Local-file batch flow

1. Request upload URLs with `POST https://mineru.net/api/v4/file-urls/batch`.
2. Send `Authorization: Bearer <token>` and `Content-Type: application/json`.
3. Put each local PDF directly to its returned upload URL without a `Content-Type` header.
4. Poll `GET https://mineru.net/api/v4/extract-results/batch/{batch_id}`.
5. Treat `waiting-file`, `pending`, `running`, and `converting` as active; `done` as success; and `failed` as terminal failure.
6. Download `full_zip_url` and use `full.md` as the Markdown result.

## Fixed request settings

Use the following request shape. Keep `is_ocr` inside each `files` item:

```json
{
  "files": [
    {
      "name": "ordered-exam.pdf",
      "data_id": "stable-id",
      "is_ocr": true
    }
  ],
  "model_version": "vlm",
  "language": "ch",
  "enable_formula": true,
  "enable_table": true
}
```

MinerU documents `file.is_ocr` as optional with a default of `false`, so this skill must always send it as `true`.

## Limits and failures

- One upload-URL request accepts at most 50 files.
- Each uploaded file is limited to 200 MB and 200 pages.
- Split larger PDFs locally before requesting upload URLs.
- Reject nonzero API `code` values even when the HTTP status is 200.
- Preserve `err_msg` for a result whose state is `failed`.
- Treat a missing `full_zip_url` or missing `full.md` as conversion failure.
- Never log the bearer token or signed upload URLs.
