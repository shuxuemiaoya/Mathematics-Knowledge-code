# MathOS Segmentation Stage One Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `mathos-segmentation-stage1`, a deterministic post-formatting operator that turns one formatted Markdown file into an Obsidian sandbox folder containing a master directory and raw segment notes.

**Architecture:** Implement one repo-local skill with a thin `SKILL.md` and one Python CLI/script containing testable functions for heading extraction, planning, writing, verification, and run records. Tests import the script directly with `importlib`, following the existing formatting tests.

**Tech Stack:** Python standard library, `argparse`, `dataclasses`, `hashlib`, `json`, `pathlib`, `pytest`, PowerShell command examples.

---

## File Structure

- Create `skills/mathos-segmentation-stage1/SKILL.md`: concise operator instructions, command shapes, stop conditions, output summary.
- Create `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`: CLI plus deterministic heading splitter implementation.
- Create `tests/test_mathos_segmentation_stage1.py`: unit tests for heading parsing, planning, writing, verification, and non-destructive behavior.
- Modify `docs/agent/skill-registry.md`: register `skills/mathos-segmentation-stage1` as active after implementation.
- Modify `AGENTS.md`: add segmentation stage to the pipeline and stop conditions.

The implementation should not touch content-vault files except in tests using `tmp_path`.

## Shared Test Fixture

Use this fixture in the test file unless a task provides a narrower sample:

```python
SAMPLE_MARKDOWN = """# 第一章 集合与常用逻辑用语

章导语

## 1.1 集合的概念

节导语

### 1.1.1 集合的概念

集合正文 A

### 1.1.2 集合的基本关系

集合正文 B

## 1.2 函数

### 1.2.1 函数的概念

函数正文 C
"""
```

## Task 1: Scaffold Importable Operator Module

**Files:**
- Create: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`
- Create: `tests/test_mathos_segmentation_stage1.py`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_mathos_segmentation_stage1.py`:

```python
from pathlib import Path
import importlib.util
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "mathos-segmentation-stage1" / "scripts" / "mathos_segmentation_stage1.py"

spec = importlib.util.spec_from_file_location("mathos_segmentation_stage1", SCRIPT_PATH)
seg = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["mathos_segmentation_stage1"] = seg
spec.loader.exec_module(seg)


def test_module_exposes_stage_constants():
    assert seg.STAGE_NAME == "segmentation-stage1"
    assert seg.SKILL_NAME == "skills/mathos-segmentation-stage1"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py::test_module_exposes_stage_constants -v
```

Expected: FAIL because the script file does not exist.

- [ ] **Step 3: Add the minimal script**

Create `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`:

```python
"""Deterministic stage-one Markdown segmentation for MathOS."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


STAGE_NAME = "segmentation-stage1"
SKILL_NAME = "skills/mathos-segmentation-stage1"
SCRIPT_COMMAND = r".\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py"
HEADING_RE = re.compile(r"^(#{1,6})\s+((\d+(?:\.\d+)*)\s+(.+?))\s*$")
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class SegmentationError(Exception):
    """Raised when stage-one segmentation cannot continue safely."""
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py::test_module_exposes_stage_constants -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "test: scaffold segmentation stage one operator"
```

## Task 2: Parse Numbered Markdown Headings

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing heading extraction tests**

Append to `tests/test_mathos_segmentation_stage1.py`:

```python
SAMPLE_MARKDOWN = """# 第一章 集合与常用逻辑用语

章导语

## 1.1 集合的概念

节导语

### 1.1.1 集合的概念

集合正文 A

### 1.1.2 集合的基本关系

集合正文 B

## 1.2 函数

### 1.2.1 函数的概念

函数正文 C
"""


def test_extract_numbered_headings_ignores_unnumbered_heading():
    headings = seg.extract_numbered_headings(SAMPLE_MARKDOWN)

    assert [item.number for item in headings] == ["1.1", "1.1.1", "1.1.2", "1.2", "1.2.1"]
    assert headings[0].depth == 2
    assert headings[1].number_depth == 3
    assert headings[1].title == "集合的概念"
    assert headings[1].full_title == "1.1.1 集合的概念"


def test_select_target_depth_defaults_to_deepest_numbering():
    headings = seg.extract_numbered_headings(SAMPLE_MARKDOWN)

    assert seg.select_target_depth(headings, None) == 3
    assert seg.select_target_depth(headings, 2) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: FAIL with `AttributeError` for missing functions.

- [ ] **Step 3: Implement heading model and extraction**

Add below `SegmentationError` in the script:

```python
@dataclass(frozen=True)
class Heading:
    marker: str
    markdown_depth: int
    number: str
    number_depth: int
    title: str
    full_title: str
    line_index: int
    char_start: int
    char_end: int

    @property
    def depth(self) -> int:
        return self.markdown_depth


def extract_numbered_headings(markdown: str) -> list[Heading]:
    headings: list[Heading] = []
    offset = 0
    for line_index, raw_line in enumerate(markdown.splitlines(keepends=True)):
        line_without_newline = raw_line.rstrip("\r\n")
        match = HEADING_RE.match(line_without_newline)
        if match:
            marker = match.group(1)
            number = match.group(3)
            title = match.group(4).strip()
            full_title = f"{number} {title}".strip()
            headings.append(
                Heading(
                    marker=marker,
                    markdown_depth=len(marker),
                    number=number,
                    number_depth=number.count(".") + 1,
                    title=title,
                    full_title=full_title,
                    line_index=line_index,
                    char_start=offset,
                    char_end=offset + len(raw_line),
                )
            )
        offset += len(raw_line)
    return headings


def select_target_depth(headings: list[Heading], requested_depth: int | None) -> int:
    if not headings:
        raise SegmentationError("No numbered headings detected")
    depths = sorted({heading.number_depth for heading in headings})
    if requested_depth is None:
        return depths[-1]
    if requested_depth not in depths:
        raise SegmentationError(f"Target depth {requested_depth} produced zero segments")
    return requested_depth
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: parse numbered segmentation headings"
```

## Task 3: Build Segment Plans Without Writing Content

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing plan tests**

Append to the test file:

```python
def test_build_plan_uses_sandbox_folder_and_short_links(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "高中" / "课本" / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    plan = seg.build_segmentation_plan(source, vault_root=vault_root, target_depth=None)

    assert plan.sandbox_dir == source.parent / "book"
    assert plan.master_path == source.parent / "book" / "000_book目录.md"
    assert [item.link_title for item in plan.segments] == [
        "1.1.1 集合的概念",
        "1.1.2 集合的基本关系",
        "1.2.1 函数的概念",
    ]
    assert plan.next_command.endswith('--vault-root "' + str(vault_root.resolve()) + '" --yes')


def test_build_plan_rejects_source_outside_vault(tmp_path):
    source = tmp_path / "outside.md"
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    try:
        seg.build_segmentation_plan(source, vault_root=vault_root, target_depth=None)
    except seg.SegmentationError as exc:
        assert "not under vault root" in str(exc)
    else:
        raise AssertionError("expected SegmentationError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: FAIL with missing `build_segmentation_plan`.

- [ ] **Step 3: Implement planning dataclasses and helpers**

Add below `select_target_depth`:

```python
@dataclass(frozen=True)
class SegmentPlan:
    heading: Heading
    link_title: str
    filename: str
    output_path: Path
    char_start: int
    char_end: int
    byte_count: int
    warning: str = ""


@dataclass(frozen=True)
class SegmentationPlan:
    source_path: Path
    vault_root: Path
    sandbox_dir: Path
    master_path: Path
    target_depth: int
    detected_number_depths: list[int]
    headings: list[Heading]
    segments: list[SegmentPlan]
    disambiguations: list[dict[str, str]]
    warnings: list[str]
    source_sha256: str
    next_command: str


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def quote_command(value: Path | str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def safe_filename(stem: str) -> str:
    cleaned = INVALID_FILENAME_CHARS_RE.sub("_", stem).strip().rstrip(".")
    return cleaned or "segment"


def disambiguate_filenames(link_titles: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    seen: dict[str, int] = {}
    filenames: list[str] = []
    disambiguations: list[dict[str, str]] = []
    for link_title in link_titles:
        base = safe_filename(link_title)
        count = seen.get(base, 0) + 1
        seen[base] = count
        final_stem = base if count == 1 else f"{base} - {count:02d}"
        if final_stem != base:
            disambiguations.append({"original": f"{base}.md", "final": f"{final_stem}.md"})
        filenames.append(f"{final_stem}.md")
    return filenames, disambiguations


def build_segment_command(source_path: Path, vault_root: Path, target_depth: int | None) -> str:
    command = (
        f"python {SCRIPT_COMMAND} segment {quote_command(source_path.resolve())} "
        f"--vault-root {quote_command(vault_root.resolve())}"
    )
    if target_depth is not None:
        command += f" --target-depth {target_depth}"
    return command + " --yes"


def build_segmentation_plan(source_path: Path, vault_root: Path, target_depth: int | None = None) -> SegmentationPlan:
    source_path = source_path.expanduser().resolve()
    vault_root = vault_root.expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise SegmentationError(f"Source file missing: {source_path}")
    if source_path.suffix.lower() != ".md":
        raise SegmentationError(f"Source file is not Markdown: {source_path}")
    if not vault_root.exists() or not vault_root.is_dir():
        raise SegmentationError(f"Invalid vault root: {vault_root}")
    if not is_relative_to(source_path, vault_root):
        raise SegmentationError(f"Source path {source_path} is not under vault root {vault_root}")

    markdown = source_path.read_text(encoding="utf-8")
    if not markdown.strip():
        raise SegmentationError(f"Source file is empty: {source_path}")
    headings = extract_numbered_headings(markdown)
    selected_depth = select_target_depth(headings, target_depth)
    detected_depths = sorted({heading.number_depth for heading in headings})
    target_headings = [heading for heading in headings if heading.number_depth == selected_depth]
    if not target_headings:
        raise SegmentationError(f"Target depth {selected_depth} produced zero segments")

    sandbox_dir = source_path.with_suffix("")
    master_path = sandbox_dir / f"000_{source_path.stem}目录.md"
    link_titles = [heading.full_title for heading in target_headings]
    filenames, disambiguations = disambiguate_filenames(link_titles)

    segments: list[SegmentPlan] = []
    warnings: list[str] = []
    for index, heading in enumerate(target_headings):
        next_start = target_headings[index + 1].char_start if index + 1 < len(target_headings) else len(markdown)
        raw_slice = markdown[heading.char_start:next_start]
        if not raw_slice.strip():
            raise SegmentationError(f"Planned segment is empty: {heading.full_title}")
        if len(raw_slice) > 200_000:
            warnings.append(f"Large segment: {heading.full_title} ({len(raw_slice)} characters)")
        segments.append(
            SegmentPlan(
                heading=heading,
                link_title=link_titles[index],
                filename=filenames[index],
                output_path=sandbox_dir / filenames[index],
                char_start=heading.char_start,
                char_end=next_start,
                byte_count=len(raw_slice.encode("utf-8")),
            )
        )

    return SegmentationPlan(
        source_path=source_path,
        vault_root=vault_root,
        sandbox_dir=sandbox_dir,
        master_path=master_path,
        target_depth=selected_depth,
        detected_number_depths=detected_depths,
        headings=headings,
        segments=segments,
        disambiguations=disambiguations,
        warnings=warnings,
        source_sha256=sha256_text(markdown),
        next_command=build_segment_command(source_path, vault_root, target_depth),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: plan deterministic segmentation packages"
```

## Task 4: Render Master Directory Tree

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing master directory tests**

Append:

```python
def test_render_master_directory_contains_only_directory_links(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    master = seg.render_master_directory(plan)

    assert master.startswith("# 目录\n\n")
    assert "- [[1.1 集合的概念]]" not in master
    assert "- [[1.1.1 集合的概念]]" in master
    assert "- [[1.1.2 集合的基本关系]]" in master
    assert "- [[1.2.1 函数的概念]]" in master
    assert "集合正文" not in master
    for line in master.splitlines():
        assert line == "" or line == "# 目录" or line.startswith("- [[")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py::test_render_master_directory_contains_only_directory_links -v
```

Expected: FAIL because `render_master_directory` is missing.

- [ ] **Step 3: Implement master rendering**

Add:

```python
def render_master_directory(plan: SegmentationPlan) -> str:
    lines = ["# 目录", ""]
    for segment in plan.segments:
        lines.append(f"- [[{segment.link_title}]]")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py::test_render_master_directory_contains_only_directory_links -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: render segmentation backbone directory"
```

## Task 5: Write Sandbox Package Non-Destructively

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing write tests**

Append:

```python
def test_write_segmentation_package_creates_master_and_raw_slices(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    original_hash = seg.file_sha256(source)
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    result = seg.write_segmentation_package(plan, overwrite=False)

    assert result["status"] == "written"
    assert plan.master_path.exists()
    assert (plan.sandbox_dir / "1.1.1 集合的概念.md").read_text(encoding="utf-8").startswith("### 1.1.1 集合的概念")
    assert "# 1.1.1 集合的概念" not in (plan.sandbox_dir / "1.1.1 集合的概念.md").read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == SAMPLE_MARKDOWN
    assert seg.file_sha256(source) == original_hash


def test_write_refuses_existing_sandbox_without_overwrite(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    plan.sandbox_dir.mkdir()

    try:
        seg.write_segmentation_package(plan, overwrite=False)
    except seg.SegmentationError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("expected SegmentationError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: FAIL with missing `file_sha256` and `write_segmentation_package`.

- [ ] **Step 3: Implement write helpers**

Add:

```python
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_segmentation_package(plan: SegmentationPlan, overwrite: bool = False) -> dict[str, Any]:
    before_hash = file_sha256(plan.source_path)
    if before_hash != plan.source_sha256:
        raise SegmentationError("Original source hash changed before writing")
    if plan.sandbox_dir.exists():
        if not overwrite:
            raise SegmentationError(f"Output sandbox folder already exists: {plan.sandbox_dir}")
        if not plan.sandbox_dir.is_dir():
            raise SegmentationError(f"Output sandbox path exists and is not a directory: {plan.sandbox_dir}")
        shutil.rmtree(plan.sandbox_dir)

    markdown = plan.source_path.read_text(encoding="utf-8")
    plan.sandbox_dir.mkdir(parents=True, exist_ok=False)
    plan.master_path.write_text(render_master_directory(plan), encoding="utf-8")
    for segment in plan.segments:
        raw_slice = markdown[segment.char_start:segment.char_end]
        if not raw_slice.strip():
            raise SegmentationError(f"Refusing to write empty segment: {segment.link_title}")
        segment.output_path.write_text(raw_slice, encoding="utf-8")

    after_hash = file_sha256(plan.source_path)
    if after_hash != before_hash:
        raise SegmentationError("Original source hash changed during writing")
    return {"status": "written", "sandbox_dir": str(plan.sandbox_dir), "master_path": str(plan.master_path)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: write segmentation sandbox packages"
```

## Task 6: Write Run Records and Verification

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing record tests**

Append:

```python
def test_write_run_records_creates_state_manifest_and_summary(tmp_path):
    repo_root = tmp_path / "repo"
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    seg.write_segmentation_package(plan)

    record_dir = seg.write_run_records(plan, repo_root=repo_root, status="completed", stop_reason="")

    state = json.loads((record_dir / "run-state.json").read_text(encoding="utf-8"))
    manifest = json.loads((record_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = (record_dir / "run-summary.md").read_text(encoding="utf-8")
    assert state["stage"] == "segmentation-stage1"
    assert state["status"] == "completed"
    assert state["counts"]["segments"] == 3
    assert manifest["master_path"] == str(plan.master_path)
    assert "Stage name: segmentation-stage1" in summary


def test_verify_package_checks_links_and_source_hash(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    seg.write_segmentation_package(plan)

    verification = seg.verify_package(plan)

    assert verification["status"] == "passed"
    assert verification["segment_count"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: FAIL with missing `write_run_records` and `verify_package`.

- [ ] **Step 3: Implement serialization, records, and verification**

Add:

```python
def run_record_dir(source_path: Path, repo_root: Path = Path(".")) -> Path:
    slug = safe_filename(source_path.stem)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return repo_root / "agent-memory" / "records" / f"{stamp}-segmentation-stage1-{slug}"


def heading_to_dict(heading: Heading) -> dict[str, Any]:
    return dataclasses.asdict(heading)


def segment_to_dict(segment: SegmentPlan) -> dict[str, Any]:
    data = dataclasses.asdict(segment)
    data["output_path"] = str(segment.output_path)
    return data


def plan_to_manifest(plan: SegmentationPlan) -> dict[str, Any]:
    return {
        "stage": STAGE_NAME,
        "skill": SKILL_NAME,
        "source_path": str(plan.source_path),
        "vault_root": str(plan.vault_root),
        "sandbox_dir": str(plan.sandbox_dir),
        "master_path": str(plan.master_path),
        "target_depth": plan.target_depth,
        "detected_number_depths": plan.detected_number_depths,
        "source_sha256": plan.source_sha256,
        "heading_tree": [heading_to_dict(heading) for heading in plan.headings],
        "segments": [segment_to_dict(segment) for segment in plan.segments],
        "disambiguations": plan.disambiguations,
        "warnings": plan.warnings,
        "next_command": plan.next_command,
    }


def verify_master_text(master_text: str) -> None:
    for line in master_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "# 目录":
            continue
        if not stripped.startswith("- "):
            raise SegmentationError(f"Invalid master directory line: {line}")
        if "[[" in stripped and not re.search(r"\[\[[^\]]+\]\]", stripped):
            raise SegmentationError(f"Invalid Obsidian link line: {line}")


def verify_package(plan: SegmentationPlan) -> dict[str, Any]:
    if not plan.sandbox_dir.is_dir():
        raise SegmentationError(f"Missing sandbox folder: {plan.sandbox_dir}")
    if not plan.master_path.is_file():
        raise SegmentationError(f"Missing master directory: {plan.master_path}")
    master_text = plan.master_path.read_text(encoding="utf-8")
    verify_master_text(master_text)
    for segment in plan.segments:
        if not segment.output_path.is_file():
            raise SegmentationError(f"Missing segment file: {segment.output_path}")
        if master_text.count(f"[[{segment.link_title}]]") != 1:
            raise SegmentationError(f"Master link missing or duplicated: {segment.link_title}")
    segment_files = sorted(path for path in plan.sandbox_dir.glob("*.md") if path != plan.master_path)
    if len(segment_files) != len(plan.segments):
        raise SegmentationError("Segment file count does not match manifest count")
    if file_sha256(plan.source_path) != plan.source_sha256:
        raise SegmentationError("Original source hash changed")
    return {"status": "passed", "segment_count": len(plan.segments)}


def write_run_records(plan: SegmentationPlan, repo_root: Path = Path("."), status: str = "completed", stop_reason: str = "") -> Path:
    record_dir = run_record_dir(plan.source_path, repo_root=repo_root)
    record_dir.mkdir(parents=True, exist_ok=False)
    verification = verify_package(plan) if status == "completed" else {"status": "not-run"}
    manifest = plan_to_manifest(plan)
    manifest["verification"] = verification
    state = {
        "stage": STAGE_NAME,
        "skill": SKILL_NAME,
        "status": status,
        "stop_reason": stop_reason,
        "source_path": str(plan.source_path),
        "vault_root": str(plan.vault_root),
        "sandbox_dir": str(plan.sandbox_dir),
        "master_path": str(plan.master_path),
        "record_dir": str(record_dir),
        "counts": {
            "headings": len(plan.headings),
            "segments": len(plan.segments),
            "warnings": len(plan.warnings),
            "disambiguations": len(plan.disambiguations),
        },
        "warnings": plan.warnings[:20],
        "records": {
            "manifest": str(record_dir / "manifest.json"),
            "run_summary": str(record_dir / "run-summary.md"),
            "run_state": str(record_dir / "run-state.json"),
        },
        "next_step": "review sandbox package in Obsidian" if status == "completed" else "inspect failure and rerun plan",
    }
    summary = f"""# Run Summary

Stage name: {STAGE_NAME}
Skill: {SKILL_NAME}
Source Markdown: `{plan.source_path}`
Vault root: `{plan.vault_root}`
Completion status: {status}
Stop reason: {stop_reason or "none"}
Sandbox folder: `{plan.sandbox_dir}`
Master directory: `{plan.master_path}`
Segment count: {len(plan.segments)}
Warning count: {len(plan.warnings)}
Duplicate disambiguation count: {len(plan.disambiguations)}
Run record folder: `{record_dir}`
Next operational step: {state["next_step"]}
"""
    (record_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    (record_dir / "run-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (record_dir / "run-summary.md").write_text(summary, encoding="utf-8")
    return record_dir
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: record and verify segmentation runs"
```

## Task 7: Add CLI Commands

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing CLI tests**

Append:

```python
def test_main_plan_prints_json_without_writing_package(tmp_path, capsys):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    exit_code = seg.main(["plan", str(source), "--vault-root", str(vault_root), "--yes"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["stage"] == "segmentation-stage1"
    assert payload["counts"]["segments"] == 3
    assert not (source.parent / "book").exists()


def test_main_segment_writes_package_and_records(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    monkeypatch.chdir(repo_root)

    exit_code = seg.main(["segment", str(source), "--vault-root", str(vault_root), "--yes"])

    assert exit_code == 0
    assert (source.parent / "book" / "000_book目录.md").exists()
    assert list((repo_root / "agent-memory" / "records").glob("*-segmentation-stage1-book"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: FAIL because `main` is missing.

- [ ] **Step 3: Implement CLI**

Add to the end of the script:

```python
def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def plan_json(plan: SegmentationPlan) -> dict[str, Any]:
    return {
        "stage": STAGE_NAME,
        "skill": SKILL_NAME,
        "source_path": str(plan.source_path),
        "vault_root": str(plan.vault_root),
        "sandbox_dir": str(plan.sandbox_dir),
        "master_path": str(plan.master_path),
        "detected_number_depths": plan.detected_number_depths,
        "target_depth": plan.target_depth,
        "counts": {
            "headings": len(plan.headings),
            "segments": len(plan.segments),
            "warnings": len(plan.warnings),
            "disambiguations": len(plan.disambiguations),
        },
        "segments": [
            {
                "link_title": segment.link_title,
                "filename": segment.filename,
                "output_path": str(segment.output_path),
                "byte_count": segment.byte_count,
            }
            for segment in plan.segments
        ],
        "warnings": plan.warnings,
        "disambiguations": plan.disambiguations,
        "next_command": plan.next_command,
    }


def command_plan(args: argparse.Namespace) -> int:
    plan = build_segmentation_plan(Path(args.source), Path(args.vault_root), target_depth=args.target_depth)
    print_json(plan_json(plan))
    return 0


def command_segment(args: argparse.Namespace) -> int:
    if not args.yes:
        raise SegmentationError("Refusing to write without --yes")
    plan = build_segmentation_plan(Path(args.source), Path(args.vault_root), target_depth=args.target_depth)
    write_segmentation_package(plan, overwrite=args.overwrite)
    record_dir = write_run_records(plan, repo_root=Path("."), status="completed", stop_reason="")
    print_json(
        {
            "stage": STAGE_NAME,
            "status": "completed",
            "sandbox_dir": str(plan.sandbox_dir),
            "master_path": str(plan.master_path),
            "segments": len(plan.segments),
            "record_dir": str(record_dir),
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Segment formatted MathOS Markdown into an Obsidian sandbox package.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Inspect planned segmentation without writing content files.")
    plan_parser.add_argument("source")
    plan_parser.add_argument("--vault-root", required=True)
    plan_parser.add_argument("--target-depth", type=int)
    plan_parser.add_argument("--yes", action="store_true")
    plan_parser.set_defaults(func=command_plan)

    segment_parser = subparsers.add_parser("segment", help="Write segmentation sandbox package and run records.")
    segment_parser.add_argument("source")
    segment_parser.add_argument("--vault-root", required=True)
    segment_parser.add_argument("--target-depth", type=int)
    segment_parser.add_argument("--overwrite", action="store_true")
    segment_parser.add_argument("--yes", action="store_true")
    segment_parser.set_defaults(func=command_segment)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SegmentationError as exc:
        print_json({"stage": STAGE_NAME, "status": "failed", "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: add segmentation stage one CLI"
```

## Task 8: Add Skill Documentation and Registry Entries

**Files:**
- Create: `skills/mathos-segmentation-stage1/SKILL.md`
- Modify: `docs/agent/skill-registry.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Create the skill file**

Create `skills/mathos-segmentation-stage1/SKILL.md`:

```markdown
---
name: mathos-segmentation-stage1
description: Use after mathos-formatting to split one formatted Markdown file into an Obsidian sandbox package with a master directory and raw segment notes.
---

# MathOS Segmentation Stage One Operator

Status: operational.

Use this operator after `mathos-formatting` when one formatted long Markdown file should be split by numbered headings into raw Obsidian notes.

This skill does not call an LLM, clean content, classify concepts, classify exercises, judge mathematical correctness, or modify the original source Markdown.

## Workflow

Run a plan first:

```powershell
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py plan `
  "<source.md>" `
  --vault-root "<vault root>" `
  --yes
```

Then write the sandbox package:

```powershell
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment `
  "<source.md>" `
  --vault-root "<vault root>" `
  --yes
```

Use `--target-depth <n>` only when the deepest numbered heading level is not the desired physical unit.

Use `--overwrite` only after confirming the existing sandbox folder may be replaced.

## Output Semantics

For `高中\课本\book.md`, output is written to:

```text
高中\课本\book\
├── 000_book目录.md
├── 1.1.1 first segment.md
└── 1.1.2 second segment.md
```

The master directory uses short Obsidian links because it lives beside the segment files.

Segment files contain raw source slices. The operator does not prepend headings, front matter, comments, or metadata.

The original source Markdown is never modified or deleted.

## Stop Conditions

Stop and report when:

- source file is missing, empty, or not Markdown;
- source path is not under the provided vault root;
- no numbered headings are detected;
- target depth produces zero segments;
- output sandbox folder already exists without `--overwrite`;
- a planned segment would be empty;
- writing or verification fails;
- original source hash changes during execution.

## Required Output Summary

Report:

- Stage name: `segmentation-stage1`;
- Skill: `skills/mathos-segmentation-stage1`;
- Source Markdown path;
- Vault root;
- Command used;
- Completion status;
- Stop reason, if stopped;
- Sandbox folder path;
- Master directory path;
- Segment count;
- Warning count;
- Duplicate disambiguation count;
- Run record folder;
- Next operational step.
```

- [ ] **Step 2: Update the skill registry**

Add this section under active skills in `docs/agent/skill-registry.md`:

```markdown
### `skills/mathos-segmentation-stage1`

Status: active.

Purpose: deterministic post-formatting segmentation into Obsidian sandbox packages.

Behavior:

- Consumes one formatted Markdown file after `mathos-formatting`.
- Splits on numbered headings, defaulting to the deepest numbered heading depth.
- Creates a source-stem sandbox folder beside the source file.
- Writes `000_<source-stem>目录.md` and raw segment notes with numbered filenames.
- Leaves the original source Markdown untouched.
- Writes run records under `agent-memory/records/<date>-segmentation-stage1-<slug>/`.
```

- [ ] **Step 3: Update AGENTS.md**

Replace the pipeline line in `AGENTS.md` with:

```text
PDF / Word -> Markdown -> Formatting -> Segmentation Stage One -> Future graph stages
```

Add `skills/mathos-segmentation-stage1` to Active skills.

Add segmentation stop conditions:

```markdown
For `mathos-segmentation-stage1`, examples include:

- Missing, empty, or non-Markdown source file.
- Source path outside the provided vault root.
- No numbered headings detected.
- Selected target depth produces zero segments.
- Existing sandbox folder without explicit overwrite.
- Empty planned segment.
- Source hash changes during execution.
- Package verification failure.
```

- [ ] **Step 4: Run documentation grep checks**

Run:

```powershell
Select-String -Path AGENTS.md,docs\agent\skill-registry.md,skills\mathos-segmentation-stage1\SKILL.md -Pattern 'mathos-segmentation-stage1|Segmentation Stage One|segmentation-stage1'
```

Expected: output shows all three files mention the new skill/stage.

- [ ] **Step 5: Commit**

```powershell
git add AGENTS.md docs/agent/skill-registry.md skills/mathos-segmentation-stage1/SKILL.md
git commit -m "docs: register segmentation stage one skill"
```

## Task 9: Final Verification

**Files:**
- No new source files unless verification reveals issues.

- [ ] **Step 1: Run all tests**

Run:

```powershell
pytest -v
```

Expected: PASS for all tests.

- [ ] **Step 2: Run a real CLI smoke test in a temp folder**

Run:

```powershell
$tmp = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("mathos-segmentation-" + [guid]::NewGuid()))
$vault = New-Item -ItemType Directory -Path (Join-Path $tmp.FullName "vault")
$source = Join-Path $vault.FullName "book.md"
@'
# 第一章 集合

## 1.1 集合

### 1.1.1 集合的概念

正文 A

### 1.1.2 集合的关系

正文 B
'@ | Set-Content -Path $source -Encoding UTF8
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py plan $source --vault-root $vault.FullName --yes
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment $source --vault-root $vault.FullName --yes
Get-ChildItem -Recurse $vault.FullName
```

Expected:

- plan prints JSON with `"segments": 2` in counts;
- segment prints JSON with `"status": "completed"`;
- temp vault contains `book\000_book目录.md`, `book\1.1.1 集合的概念.md`, and `book\1.1.2 集合的关系.md`;
- original `book.md` still exists.

- [ ] **Step 3: Inspect git status**

Run:

```powershell
git status --short
```

Expected: clean after all task commits.

- [ ] **Step 4: Summarize**

Report:

- tests run and pass/fail result;
- smoke test result;
- final commit range;
- paths for the new skill and script;
- any caveats from verification.
