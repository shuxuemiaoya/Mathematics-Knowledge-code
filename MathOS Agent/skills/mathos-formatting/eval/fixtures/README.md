# Eval Fixtures

This directory holds test fixtures for the Promptfoo evaluation suite.  
Each subdirectory (`book1/`, `book2/`, …) represents one textbook's test data.

## Directory Structure

```
fixtures/
├── README.md              ← this file
├── populate_fixtures.py   ← helper script (optional)
├── book1/
│   ├── input_step1.md     ← numbered first-20-page Markdown (TOC detection input)
│   ├── golden_step1.md    ← expected TOC output (golden reference)
│   ├── input_step3.md     ← toc_and_headings.md (heading processor input)
│   ├── golden_step3.py    ← expected heading_processor.py (optional golden)
│   ├── input_step3_expected.md  ← TOC text for heading expected-result prompt
│   ├── golden_step3_expected.md ← expected heading list output
│   ├── input_step5.md     ← heading_check_input.md (validation input)
│   └── golden_step5.json  ← expected heading_check_response.json
└── book2/
    └── ...
```

## File Descriptions

| Fixture File              | Source Artifact              | Pipeline Step | Description |
|---------------------------|-----------------------------|---------------|-------------|
| `input_step1.md`         | `toc_detection_sample.md`   | Step 1        | First 20 pages, each line prepended with `<line_number>: <content>` |
| `golden_step1.md`        | `toc.md`                    | Step 1        | Clean extracted TOC (golden reference for similarity scoring) |
| `input_step3.md`         | `toc_and_headings.md`       | Step 3        | TOC block + full heading list (heading processor input) |
| `golden_step3.py`        | `heading_processor.py`      | Step 3        | Expected Python script output (optional) |
| `input_step3_expected.md`| TOC portion of the input    | Step 3 expect | Raw TOC for heading expected-result prompt |
| `golden_step3_expected.md`| `heading_expected_result.md`| Step 3 expect | Expected heading list (# / ## / ### lines) |
| `input_step5.md`         | `heading_check_input.md`    | Step 5        | TOC + processed headings for validation |
| `golden_step5.json`      | `heading_check_response.json`| Step 5       | Expected JSON: `{valid, checked_heading_count, errors}` |

## How to Create Fixtures Manually

1. **Create a directory**: `fixtures/book1/`
2. **Copy the relevant artifacts** from a successful mathos-formatting run:
   - `toc_detection_sample.md` → `input_step1.md`
   - `toc.md` → `golden_step1.md`
   - `toc_and_headings.md` → `input_step3.md`
   - `heading_expected_result.md` → `golden_step3_expected.md`
   - `heading_check_input.md` → `input_step5.md`
   - `heading_check_response.json` → `golden_step5.json`
   - `heading_processor.py` → `golden_step3.py`

3. **Minimum required for the core tests**:
   - `input_step1.md`
   - `golden_step1.md`
   - `input_step3.md`
   - `golden_step3.py`

## Using the Helper Script

```powershell
python fixtures/populate_fixtures.py `
  --work-dir "C:\path\to\mathos-formatting\【book-name】" `
  --book book1
```

This copies and renames the relevant files automatically.

## Adding More Test Cases

To evaluate with multiple books, create `book2/`, `book3/`, etc. and add
corresponding test entries in `promptfooconfig.yaml` referencing the new
fixture paths.
