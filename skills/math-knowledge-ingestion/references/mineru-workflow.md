# MinerU Workflow Reference

## Package Paths

- CLI: `src/math_knowledge_tools/mineru/cli.py`
- API client: `src/math_knowledge_tools/mineru/core/client.py`
- Endpoints: `src/math_knowledge_tools/mineru/core/endpoints.py`
- Batch processor: `src/math_knowledge_tools/mineru/batch_parser/processor.py`
- Path and merge utilities: `src/math_knowledge_tools/mineru/batch_parser/file_utils.py`

## Environment

Expected private variables:

- `MINERU_API_KEY`
- `BASE_URL`
- `KNOWLEDGE_BASE_DIR`
- `SOURCE_MATERIALS_DIR`
- `MAX_PARALLEL_TASKS`
- `MAX_PAGES_PER_CHUNK`
- `POLL_INTERVAL`
- `MAX_RETRIES`

The loader checks `MATH_KNOWLEDGE_ENV`, repo `.env`, `C:\mygithub\.env`, then the shell environment.

## Behavior Notes

- PDF files are split into chunks when pages exceed `MAX_PAGES_PER_CHUNK`.
- DOCX files are uploaded without OCR.
- Existing non-empty Markdown output files are skipped for resumable runs.
- Output paths are checked so bad relative paths cannot escape `--out-dir`.
- MinerU ZIP downloads are extracted with path checks instead of raw `extractall`.
- Optional post-processing runs the same formatter modes as `mk-format`.
