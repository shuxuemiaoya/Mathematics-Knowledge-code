---
name: question-type-pdf-to-markdown
description: Convert profile-registered supplementary PDFs through forced MinerU OCR with complete page, asset, formula, and table coverage. Use for questions, answers, or combined PDF sources before format inventory.
---

# Question Type PDF To Markdown

Read `references/mineru-api.md` before live conversion. Run
`scripts/question_type_pdf_to_markdown.py` for each registered PDF role. Force
OCR with the VLM model and formula/table extraction, split above API limits,
preserve ordered page provenance and assets, and resume active remote batches
without exposing credentials or signed URLs. Resolve credentials from the
explicit option, process environment, or deterministic profile/project-root
search rather than the launch directory. Build the normalized page/bbox
provenance index after all registered PDF roles finish.
