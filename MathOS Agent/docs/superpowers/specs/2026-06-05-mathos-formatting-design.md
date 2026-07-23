# MathOS Adaptive Markdown Formatting Design

Date: 2026-06-05

## Purpose

Create the design for `skills/mathos-formatting`, the next repo-local stage in the MathOS knowledge-graph build pipeline:

```text
PDF / Word -> Markdown -> Formatting -> Future graph stages
```

The formatting skill must handle unknown Markdown sources, including textbooks, novels, exercise banks, test sets, newspapers, and other converted documents. It must not ask the LLM to manually edit thousands of files. Instead, it uses the LLM as a senior engineer that generates reusable Python cleaning plugins from representative samples.

Unknown document types are handled through a backup-only learning loop. The original Markdown file remains unchanged until the user approves a candidate result and the generated program is saved as an approved reusable cleaner.

## Repo Role And Boundaries

The code/content split remains:

```text
C:\Mathematics-Knowledge\Mathematics-Knowledge-code
  Repo-local skills, scripts, prompts, tests, reports, and approved formatting programs.

C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map
  Markdown content and generated knowledge-base artifacts.
```

The formatting skill may create candidate backup files and reports near target Markdown files during a user-approved formatting workflow. It must not modify original content during unknown-type learning.

The skill must read provider settings from:

```text
C:\Mathematics-Knowledge\.env
```

It must never print, copy, or save secret values from `.env`.

## Skill Layout

The skill should use the standard local skill structure:

```text
skills/mathos-formatting/
  assets/
  agents/
  plugins/
    approved/
    candidates/
  reports/
  references/
  scripts/
    mathos_formatting.py
  LICENSE.txt
  NOTICE.txt
  SKILL.md
```

`assets/` may hold static examples, JSON templates, and test fixtures.

`agents/` may hold provider prompts, DeepSeek instructions, and generation templates.

`plugins/approved/` stores only user-approved reusable cleaners.

`plugins/candidates/` may hold temporary candidate plugin files for the active trial, but these are not reusable programs.

`reports/` stores formatting review reports, approval records, and run summaries when they are not stored in a per-run memory folder.

`references/` stores formatting policy notes and provider documentation.

`scripts/mathos_formatting.py` is the deterministic local operator.

`LICENSE.txt`, `NOTICE.txt`, and `SKILL.md` are mandatory skill files.

## Core Architecture

The formatting operator manages a two-step LLM-assisted lifecycle:

```text
Original Markdown
  -> extract headings and table of contents
  -> ask LLM for regex heading rules
  -> apply heading rules to a fresh candidate backup
  -> extract one aligned h1 section
  -> ask LLM for a Python content cleaner
  -> apply content cleaner to a fresh candidate backup
  -> generate diff and issue report
  -> user feedback loop
  -> user approval
  -> save approved reusable plugin
```

The LLM proposes rules and code. The local operator owns extraction, validation, backup creation, execution, reporting, approval gating, and reuse.

## Step 1: TOC And Heading Alignment

The first learning step prepares a compact structural payload:

```text
- existing Markdown headings: #, ##, ###, ####, and deeper
- extracted table-of-contents block
- nearby page numbers, dotted leaders, and chapter-section numbering
- heading-like plain text lines
- current heading level distribution
- source file label or path
```

The operator sends this payload to the local management provider, initially DeepSeek, and asks for regex-based heading normalization rules. The goal is to align body headings with the table-of-contents structure.

For example, a source may need rules that turn chapter lines into `#`, section lines into `##`, subsection lines into `###`, and local exercise or reading labels into `####`.

The LLM output for this step should be structured, such as:

```text
heading_rules.json
```

The operator must validate the rules before applying them:

```text
- all regexes compile
- replacements are valid strings or approved replacement templates
- rule order is explicit
- protected blocks are not targeted unless explicitly allowed
- a small dry-run can complete
```

Heading rules apply only to a candidate backup during unknown-type learning.

## Step 2: H1 Content Formatting Strategy

After heading alignment, the operator extracts one complete `#` section from the candidate backup and prepares a second compact payload:

```text
- heading-rule summary
- one complete h1 section
- protected-block inventory for math, code fences, images, and tables
- known warnings from heading alignment
- requested output: Python content cleaner plugin
```

The LLM writes a candidate Python cleaner plugin for content-level formatting. Typical responsibilities may include:

```text
- broken paragraph merging
- exercise and question formatting
- math expression preservation or repair
- table cleanup
- image placement cleanup
- repeated header or footer removal
- list and numbering normalization
```

The plugin must expose a stable interface:

```python
PLUGIN_ID = "auto_generated_family_id"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    ...

def clean(markdown: str) -> str:
    ...
```

The plugin receives Markdown text and returns Markdown text. It must not receive file paths, provider credentials, environment variables, shell access, or direct network access.

## Backup And Feedback Loop

Unknown Markdown types always use backup-only learning. The original file is read-only.

Candidate paths should be deterministic and easy to inspect, such as:

```text
original:
Secondary-School-Mathematics-Knowledge-Map/.../book.md

candidate:
Secondary-School-Mathematics-Knowledge-Map/.../.mathos-formatting/book.candidate.md
```

Each feedback iteration must start from the original file:

```text
1. delete the previous candidate backup if it exists
2. copy the original Markdown file to a fresh candidate backup
3. apply the current heading regex rules to the candidate
4. extract one h1 section from the candidate
5. apply the candidate content plugin to the candidate
6. generate a review report
7. ask for user feedback or approval
```

If the user reports problems, the operator must not patch the already-modified candidate. It deletes the candidate backup, recreates it from the original, revises the rules or plugin, and reruns the full candidate process.

Only after explicit user approval can the tool save the generated program as approved.

## Provider Interface

The first provider target is DeepSeek through the local management provider settings in the parent `.env` file. The design should keep the provider adapter generic so later providers can be added without changing the formatting lifecycle.

The operator should not send an entire book by default. It should send compact extraction payloads for the two steps:

```text
Step 1:
  headings, TOC block, heading-like lines, level distribution, requested regex output

Step 2:
  heading-rule summary, one h1 section, protected-block inventory, requested Python plugin output
```

LLM outputs should be parsed as structured artifacts, not free prose:

```text
heading_rules.json
content_cleaner.py
metadata.json
```

## Plugin Safety

The Python plugin path is powerful and must be guarded.

Before running a candidate plugin, the operator must verify:

```text
- the required interface exists
- the plugin can run on a tiny test string
- imports are either absent or from an allowlist
- the plugin does not call filesystem, shell, environment, process, or network APIs
- the plugin returns text
- the plugin does not mutate global state required by the runner
```

The first implementation can use static checks plus a restricted runner. If the runner cannot confidently restrict a plugin, it must stop and report the issue instead of running the plugin.

Candidate plugins are not approved programs. They may be kept only for the active run or deleted after the review loop.

## Saved Programs And Reuse

An approved formatting program contains both heading rules and content cleaning logic:

```text
plugins/approved/<plugin-id>/
  heading_rules.json
  content_cleaner.py
  metadata.json
  approval.md
  sample_before.md
  sample_after.md
```

`metadata.json` should include:

```text
- plugin id
- version
- approval timestamp
- source file family evidence
- heading signature used for matching
- TOC signature used for matching
- h1 sample hash
- operations summary
- original approving file path
- allowed scope: manual-only or batch-eligible
```

Reusable programs are saved only after the user approves the backup result. Intermediate drafts are not saved as reusable programs.

The skill supports three reuse modes:

```text
manual:
  user names an approved plugin and target files

suggest:
  operator scans unknown files and suggests likely plugins

batch:
  operator applies only approved, batch-eligible plugins to matching files
```

A newly approved plugin starts as `manual-only`. It can become `batch-eligible` only after succeeding on several reviewed files.

## Reports And User Review

Each candidate run should generate a report with:

```text
- source file path
- candidate file path
- heading rules summary
- content plugin summary
- headings before and after
- changed-line diff against the original
- warnings and detected risks
- files touched
- next action options: approve, revise, discard
```

The report should make it easy for the user to identify problems and give correction feedback. The LLM is never the approval authority.

## Testing And Verification

Tests should focus on safety and repeatability:

```text
- extraction finds headings and TOC blocks without changing files
- heading regex rules compile before use
- heading regex rules apply only to candidate backups
- previous candidate backup is deleted before each retry
- candidate backup is recreated from the original every iteration
- original Markdown is unchanged during unknown-type learning
- plugin must expose the required interface
- plugin runner rejects filesystem, shell, environment, network, and unsafe imports
- approved plugin folder is created only after explicit approval
- approved plugin can be reused without calling the LLM
- reports include diff, warnings, touched files, and rule/plugin summary
```

Expected verification command:

```powershell
python -m pytest tests/test_mathos_formatting.py
```

## Success Criteria

The design is successful when `skills/mathos-formatting` can be implemented as an adaptive Markdown formatting stage that:

```text
- learns unknown Markdown formatting patterns from samples
- uses the LLM to generate heading regex rules and Python cleaner plugins
- modifies only fresh candidate backups during unknown-type learning
- reruns every feedback iteration from the original file
- saves reusable programs only after user approval
- reuses approved programs without calling the LLM
- protects secrets and avoids printing provider keys
- keeps original content safe until explicit approval
```
