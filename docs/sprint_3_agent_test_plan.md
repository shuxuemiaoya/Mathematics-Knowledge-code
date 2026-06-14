# sprint_3_agent_test Implementation Plan

This plan coordinates a complete run and re-test of the MathOS knowledge graph agent pipeline on the test files.

## Goal
1. Delete the existing output test directory `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test`.
2. Run PDF-to-Markdown conversion on the test PDFs.
3. Apply the adaptive formatting pipeline using DeepSeek.
4. Segment the formatted Markdown files into Obsidian sandbox packages.
5. Record the execution flowchart and analyze potential areas of optimization and improvement.

## User Review Required
> [!IMPORTANT]
> - This test run will overwrite and recreate the content inside `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test`.
> - The adaptive formatting stage queries the DeepSeek API using the API key located in the local `.env` file.

## Open Questions
- None.

## Proposed Steps

### Step 1: Cleanup Existing Output Directory
Delete the `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test` directory to ensure a clean slate for the test.

### Step 2: PDF-to-MD Conversion (`pdf-to-md`)
Execute the PDF-to-MD conversion tool on the source directory:
```powershell
python .\skills\mathos-pdf-to-md\scripts\mathos_pdf_to_md.py convert "C:\code\BaiduSyncdisk\数学妙呀资料\test" --yes
```

### Step 3: Adaptive Markdown Formatting (`mathos-formatting`)
Run `learn-from-provider` on each generated Markdown file to generate heading rules, TOC stripping, and python content cleaner via DeepSeek:
```powershell
# For High School selective book 2
python skills/mathos-formatting/scripts/mathos_formatting.py learn-from-provider "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【人教版】高中选择性必修 第二册数学电子课本.md" --env "C:\Mathematics-Knowledge\.env"

# For Grade 7 Second Volume
python skills/mathos-formatting/scripts/mathos_formatting.py learn-from-provider "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【2024版】【人教版】七年级下册数学.md" --env "C:\Mathematics-Knowledge\.env"
```

Apply the generated candidates to the test files:
```powershell
# Apply High School Selective Book 2 candidate
Copy-Item -Path "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\【人教版】高中选择性必修 第二册数学电子课本\candidate.md" -Destination "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【人教版】高中选择性必修 第二册数学电子课本.md" -Force

# Apply Grade 7 Second Volume candidate
Copy-Item -Path "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\【2024版】【人教版】七年级下册数学\candidate.md" -Destination "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【2024版】【人教版】七年级下册数学.md" -Force

# Cleanup formatting temp work directories
Remove-Item -Path "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting" -Recurse -Force
```

### Step 4: Deterministic Segmentation (`segmentation-stage1`)
Segment the formatted Markdown files into Obsidian folders:
```powershell
# Segment High School Selective Book 2
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【人教版】高中选择性必修 第二册数学电子课本.md" --vault-root "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map" --yes

# Segment Grade 7 Second Volume
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【2024版】【人教版】七年级下册数学.md" --vault-root "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map" --yes
```

### Step 5: Recording and Optimization Analysis
- Build and record a flowchart of the execution process.
- Analyze the output files and propose recommendations for optimizing performance, token usage, and segmentation logic.

## Verification Plan
### Automated Verification
- Run `pytest` to make sure all existing regression tests are still passing.
### Manual Verification
- Verify the physical existence of segment files in:
  - `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【人教版】高中选择性必修 第二册数学电子课本\`
  - `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【2024版】【人教版】七年级下册数学\`
