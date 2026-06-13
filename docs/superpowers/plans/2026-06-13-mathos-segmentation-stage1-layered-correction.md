# MathOS Segmentation Stage One Layered Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the existing `mathos-segmentation-stage1` operator so it writes layered Obsidian directory notes with raw text only in leaf notes.

**Architecture:** Replace the current flat deepest-heading `SegmentPlan` model with a `DirectoryNode` tree built from formatted body headings. Keep the existing CLI commands, sandbox folder layout, non-destructive write behavior, and run-record files, but update planning, rendering, writing, verification, tests, and docs to use nodes, directory nodes, and leaf nodes.

**Tech Stack:** Python standard library, `argparse`, `dataclasses`, `hashlib`, `json`, `pathlib`, `pytest`, PowerShell command examples.

---

## File Structure

- Modify `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`: replace flat segment planning with layered node planning, special-pair merge logic, directory rendering, leaf writing, verification, run records, and CLI JSON counts.
- Modify `tests/test_mathos_segmentation_stage1.py`: update tests from flat deepest-heading expectations to layered tree expectations, while preserving safety tests for validation, quoting, duplicate disambiguation, overwrite refusal, and source preservation.
- Modify `skills/mathos-segmentation-stage1/SKILL.md`: document layered directory output and special-pair merge behavior.
- Modify `docs/agent/skill-registry.md`: update behavior summary for the corrected layered operator.
- Modify `AGENTS.md`: no new skill, but update stop-condition wording if needed to mention layered package verification.

Do not edit content-vault files during implementation except in temporary test directories.

## Shared Layered Fixture

Use this fixture in tests that need the corrected tree behavior:

```python
LAYERED_MARKDOWN = """# 第六章 平面向量及其应用

章导语原文

## 6.1 平面向量的概念

节导语原文

### 6.1.1 向量的实际背景与概念

6.1.1 正文

### 6.1.2 向量的几何表示

6.1.2 正文

## 阅读与思考

### 向量及向量符号的由来

阅读正文

## 6.2 平面向量的运算

### 6.2.1 向量的加法运算

6.2.1 正文

# 第七章 复数

第七章导语

## 7.1 复数的概念

### 7.1.1 数系的扩充和复数的概念

7.1.1 正文
"""
```

## Task 1: Introduce Directory Node Model

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing tests for layered node planning**

Replace flat master expectations with new tests near the existing planning tests:

```python
LAYERED_MARKDOWN = """# 第六章 平面向量及其应用

章导语原文

## 6.1 平面向量的概念

节导语原文

### 6.1.1 向量的实际背景与概念

6.1.1 正文

### 6.1.2 向量的几何表示

6.1.2 正文

## 阅读与思考

### 向量及向量符号的由来

阅读正文

## 6.2 平面向量的运算

### 6.2.1 向量的加法运算

6.2.1 正文

# 第七章 复数

第七章导语

## 7.1 复数的概念

### 7.1.1 数系的扩充和复数的概念

7.1.1 正文
"""


def _write_layered_source(tmp_path):
    vault_root = tmp_path / "vault"
    source = vault_root / "book.md"
    source.parent.mkdir(parents=True)
    source.write_text(LAYERED_MARKDOWN, encoding="utf-8")
    return vault_root, source


def test_build_plan_creates_layered_nodes_and_counts(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    assert plan.master_path == source.parent / "book" / "000_book目录.md"
    assert [node.note_stem for node in plan.top_level_nodes] == ["第六章 平面向量及其应用", "第七章 复数"]
    assert plan.counts["nodes"] == 9
    assert plan.counts["directory_nodes"] == 4
    assert plan.counts["leaf_nodes"] == 5
    assert plan.counts["special_merges"] == 1


def test_layered_plan_keeps_full_numeric_prefixes_for_leaf_nodes(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)

    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    leaf_filenames = [node.filename for node in plan.leaf_nodes]
    assert "6.1.1 向量的实际背景与概念.md" in leaf_filenames
    assert "6.1.2 向量的几何表示.md" in leaf_filenames
    assert "6.2.1 向量的加法运算.md" in leaf_filenames
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py::test_build_plan_creates_layered_nodes_and_counts tests/test_mathos_segmentation_stage1.py::test_layered_plan_keeps_full_numeric_prefixes_for_leaf_nodes -v
```

Expected: FAIL because `DirectoryNode`, `top_level_nodes`, `leaf_nodes`, and layered counts do not exist.

- [ ] **Step 3: Add node dataclasses and heading extraction helpers**

In `mathos_segmentation_stage1.py`, keep `Heading` and existing path helpers. Add:

```python
CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百]+章\s+(.+)$")
NUMBERED_TITLE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")
SPECIAL_PAIR_LABELS = {"阅读与思考", "数学探究"}


@dataclass
class DirectoryNode:
    source_heading: Heading
    note_stem: str
    filename: str = ""
    output_path: Path | None = None
    parent: "DirectoryNode | None" = None
    children: list["DirectoryNode"] = field(default_factory=list)
    raw_start: int = 0
    raw_end: int = 0
    is_leaf: bool = True
    is_special_merge: bool = False
    merged_heading: Heading | None = None
    warning: str = ""


def is_chapter_heading(heading: Heading) -> bool:
    return heading.markdown_depth == 1 and CHAPTER_RE.match(heading.full_title) is not None


def heading_number_depth(heading: Heading) -> int | None:
    match = NUMBERED_TITLE_RE.match(heading.full_title)
    if not match:
        return None
    return match.group(1).count(".") + 1


def clean_heading_title(line_text: str) -> str:
    return line_text.strip().lstrip("#").strip()
```

Keep `extract_numbered_headings()` for backward-compatible tests if desired, but add a new `extract_all_headings(markdown: str) -> list[Heading]` that captures every Markdown heading, numbered or not:

```python
ALL_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def extract_all_headings(markdown: str) -> list[Heading]:
    headings: list[Heading] = []
    char_offset = 0
    for line_index, line in enumerate(markdown.splitlines(keepends=True)):
        line_text = line.rstrip("\r\n")
        match = ALL_HEADING_RE.match(line_text)
        if match:
            marker = match.group(1)
            full_title = match.group(2).strip()
            number_match = NUMBERED_TITLE_RE.match(full_title)
            number = number_match.group(1) if number_match else ""
            title = number_match.group(2).strip() if number_match else full_title
            headings.append(
                Heading(
                    marker=marker,
                    markdown_depth=len(marker),
                    number=number,
                    number_depth=number.count(".") + 1 if number else 0,
                    title=title,
                    full_title=full_title,
                    line_index=line_index,
                    char_start=char_offset,
                    char_end=char_offset + len(line),
                )
            )
        char_offset += len(line)
    return headings
```

- [ ] **Step 4: Replace plan dataclass with layered fields**

Change `SegmentationPlan` to include:

```python
@dataclass(frozen=True)
class SegmentationPlan:
    source_path: Path
    vault_root: Path
    sandbox_dir: Path
    master_path: Path
    headings: list[Heading]
    top_level_nodes: list[DirectoryNode]
    nodes: list[DirectoryNode]
    leaf_nodes: list[DirectoryNode]
    directory_nodes: list[DirectoryNode]
    disambiguations: list[dict[str, str]]
    special_merges: list[dict[str, str]]
    warnings: list[str]
    source_sha256: str
    next_command: str

    @property
    def counts(self) -> dict[str, int]:
        return {
            "headings": len(self.headings),
            "nodes": len(self.nodes),
            "directory_nodes": len(self.directory_nodes),
            "leaf_nodes": len(self.leaf_nodes),
            "special_merges": len(self.special_merges),
            "warnings": len(self.warnings),
            "disambiguations": len(self.disambiguations),
        }
```

Remove new reliance on `target_depth` for tree construction. Keep the CLI argument for compatibility, but ignore it or reject it with a clear warning only in a later task. For this correction, do not remove the flag.

- [ ] **Step 5: Implement minimal tree construction**

Add these functions:

```python
def node_level(heading: Heading) -> int:
    if is_chapter_heading(heading):
        return 1
    depth = heading_number_depth(heading)
    if depth is not None:
        return depth + 1
    return heading.markdown_depth


def build_directory_tree(headings: list[Heading], markdown: str, sandbox_dir: Path) -> tuple[list[DirectoryNode], list[DirectoryNode], list[dict[str, str]], list[str]]:
    nodes: list[DirectoryNode] = []
    special_merges: list[dict[str, str]] = []
    warnings: list[str] = []
    stack: list[tuple[int, DirectoryNode]] = []
    index = 0
    while index < len(headings):
        heading = headings[index]
        note_stem = heading.full_title
        is_special_merge = False
        merged_heading: Heading | None = None
        if heading.full_title in SPECIAL_PAIR_LABELS and index + 1 < len(headings):
            candidate = headings[index + 1]
            if candidate.markdown_depth == heading.markdown_depth + 1:
                note_stem = f"{heading.full_title} {candidate.full_title}"
                is_special_merge = True
                merged_heading = candidate
                special_merges.append({"generic": heading.full_title, "specific": candidate.full_title, "merged": note_stem})
                index += 1
        level = node_level(heading)
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        node = DirectoryNode(
            source_heading=heading,
            note_stem=note_stem,
            parent=parent,
            raw_start=heading.char_start,
            raw_end=len(markdown),
            is_special_merge=is_special_merge,
            merged_heading=merged_heading,
        )
        if parent is not None:
            parent.children.append(node)
        nodes.append(node)
        stack.append((level, node))
        index += 1

    for node in nodes:
        node.is_leaf = not node.children
    for node_index, node in enumerate(nodes):
        end = len(markdown)
        for later in nodes[node_index + 1:]:
            ancestor = later.parent
            inside_subtree = False
            while ancestor is not None:
                if ancestor is node:
                    inside_subtree = True
                    break
                ancestor = ancestor.parent
            if not inside_subtree:
                end = later.source_heading.char_start
                break
        node.raw_end = end
    return [node for node in nodes if node.parent is None], nodes, special_merges, warnings
```

- [ ] **Step 6: Update filename assignment**

Create:

```python
def assign_node_paths(nodes: list[DirectoryNode], sandbox_dir: Path) -> list[dict[str, str]]:
    filenames, disambiguations = disambiguate_filenames([node.note_stem for node in nodes])
    for node, filename in zip(nodes, filenames):
        node.filename = filename
        node.output_path = sandbox_dir / filename
    return disambiguations
```

- [ ] **Step 7: Update `build_segmentation_plan()`**

Inside `build_segmentation_plan`, use `extract_all_headings(markdown)`, require at least one chapter heading, build the tree, assign paths, and return the new plan:

```python
headings = extract_all_headings(markdown)
if not headings:
    raise SegmentationError("No Markdown headings detected")
top_level_nodes, nodes, special_merges, warnings = build_directory_tree(headings, markdown, sandbox_dir)
if not top_level_nodes:
    raise SegmentationError("No top-level directory nodes detected")
disambiguations = assign_node_paths(nodes, sandbox_dir)
leaf_nodes = [node for node in nodes if node.is_leaf]
directory_nodes = [node for node in nodes if not node.is_leaf]
if not leaf_nodes:
    raise SegmentationError("No leaf nodes detected")
```

- [ ] **Step 8: Run tests**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: Some old flat tests fail. Update only tests whose expectations conflict with the new approved spec. Keep validation and safety tests.

- [ ] **Step 9: Commit**

After tests for this task pass:

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: build layered segmentation node tree"
```

## Task 2: Render Layered Directory Notes

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing rendering tests**

Add:

```python
def test_render_master_directory_links_only_top_level_chapters(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    master = seg.render_master_directory(plan)

    assert master == "# 目录\n\n- [[第六章 平面向量及其应用]]\n- [[第七章 复数]]\n"
    assert "[[# " not in master
    assert "[[## " not in master
    assert "6.1 平面向量的概念" not in master


def test_render_directory_note_links_only_immediate_children(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    chapter = next(node for node in plan.nodes if node.note_stem == "第六章 平面向量及其应用")

    text = seg.render_directory_note(chapter)

    assert text == (
        "# 目录\n\n"
        "- [[6.1 平面向量的概念]]\n"
        "- [[阅读与思考 向量及向量符号的由来]]\n"
        "- [[6.2 平面向量的运算]]\n"
    )
    assert "6.1.1 向量的实际背景与概念" not in text
    assert "章导语原文" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py::test_render_master_directory_links_only_top_level_chapters tests/test_mathos_segmentation_stage1.py::test_render_directory_note_links_only_immediate_children -v
```

Expected: FAIL because rendering is still flat.

- [ ] **Step 3: Implement clean link rendering**

Replace `render_master_directory()` and add `render_directory_note()`:

```python
def link_for_node(node: DirectoryNode) -> str:
    return Path(node.filename).stem


def render_link_list(nodes: list[DirectoryNode]) -> str:
    lines = ["# 目录", ""]
    for node in nodes:
        lines.append(f"- [[{link_for_node(node)}]]")
    return "\n".join(lines).rstrip() + "\n"


def render_master_directory(plan: SegmentationPlan) -> str:
    return render_link_list(plan.top_level_nodes)


def render_directory_note(node: DirectoryNode) -> str:
    if node.is_leaf:
        raise SegmentationError(f"Cannot render leaf as directory note: {node.note_stem}")
    return render_link_list(node.children)
```

- [ ] **Step 4: Update old rendering tests**

Remove or rewrite tests that assert the master links to deepest numbered headings. Replace them with the new master/chapter/section tests. Keep the duplicate disambiguation link test but update it to use `link_for_node()` or layered nodes.

- [ ] **Step 5: Run tests**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: render layered segmentation directories"
```

## Task 3: Write Layered Packages

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing write tests**

Add:

```python
def test_write_layered_package_creates_directory_and_leaf_notes(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)
    original_hash = seg.file_sha256(source)
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    seg.write_segmentation_package(plan, overwrite=False)

    assert (plan.sandbox_dir / "000_book目录.md").read_text(encoding="utf-8") == seg.render_master_directory(plan)
    assert (plan.sandbox_dir / "第六章 平面向量及其应用.md").read_text(encoding="utf-8").startswith("# 目录\n\n")
    assert "章导语原文" not in (plan.sandbox_dir / "第六章 平面向量及其应用.md").read_text(encoding="utf-8")
    leaf_text = (plan.sandbox_dir / "6.1.1 向量的实际背景与概念.md").read_text(encoding="utf-8")
    assert leaf_text.startswith("### 6.1.1 向量的实际背景与概念")
    assert "6.1.1 正文" in leaf_text
    assert seg.file_sha256(source) == original_hash


def test_write_special_pair_leaf_swallows_specific_heading(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)

    seg.write_segmentation_package(plan)

    special = plan.sandbox_dir / "阅读与思考 向量及向量符号的由来.md"
    assert special.exists()
    text = special.read_text(encoding="utf-8")
    assert text.startswith("## 阅读与思考")
    assert "### 向量及向量符号的由来" in text
    assert "阅读正文" in text
    assert not (plan.sandbox_dir / "阅读与思考.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py::test_write_layered_package_creates_directory_and_leaf_notes tests/test_mathos_segmentation_stage1.py::test_write_special_pair_leaf_swallows_specific_heading -v
```

Expected: FAIL because writer still writes flat segments or uses old `segments`.

- [ ] **Step 3: Update writer**

Change `write_segmentation_package()`:

```python
plan.sandbox_dir.mkdir(parents=True, exist_ok=False)
plan.master_path.write_text(render_master_directory(plan), encoding="utf-8")
for node in plan.nodes:
    assert node.output_path is not None
    if node.is_leaf:
        raw_slice = markdown[node.raw_start:node.raw_end]
        if not raw_slice.strip():
            raise SegmentationError(f"Refusing to write empty leaf: {node.note_stem}")
        node.output_path.write_text(raw_slice, encoding="utf-8")
    else:
        node.output_path.write_text(render_directory_note(node), encoding="utf-8")
```

Keep overwrite refusal and source hash checks.

- [ ] **Step 4: Update old writer tests**

Rename or rewrite old flat segment tests:

- `test_write_segmentation_package_creates_master_and_raw_slices` becomes layered writer test.
- Keep `test_write_refuses_existing_sandbox_without_overwrite` unchanged except for plan field names.

- [ ] **Step 5: Run tests**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: write layered segmentation packages"
```

## Task 4: Update Manifest, Run State, Plan JSON, and Verification

**Files:**
- Modify: `tests/test_mathos_segmentation_stage1.py`
- Modify: `skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py`

- [ ] **Step 1: Add failing record and verification tests**

Add:

```python
def test_plan_json_reports_layered_counts(tmp_path, capsys):
    vault_root, source = _write_layered_source(tmp_path)

    exit_code = seg.main(["plan", str(source), "--vault-root", str(vault_root), "--yes"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["counts"]["nodes"] == 9
    assert payload["counts"]["directory_nodes"] == 4
    assert payload["counts"]["leaf_nodes"] == 5
    assert payload["counts"]["special_merges"] == 1
    assert not (source.parent / "book").exists()


def test_verify_layered_package_rejects_grandchild_link_in_chapter(tmp_path):
    vault_root, source = _write_layered_source(tmp_path)
    plan = seg.build_segmentation_plan(source, vault_root=vault_root)
    seg.write_segmentation_package(plan)
    chapter = next(node for node in plan.nodes if node.note_stem == "第六章 平面向量及其应用")
    chapter.output_path.write_text("# 目录\n\n- [[6.1.1 向量的实际背景与概念]]\n", encoding="utf-8")

    assert_segmentation_error_contains(
        "Directory links do not match immediate children",
        seg.verify_package,
        plan,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py::test_plan_json_reports_layered_counts tests/test_mathos_segmentation_stage1.py::test_verify_layered_package_rejects_grandchild_link_in_chapter -v
```

Expected: FAIL because counts and verification still use flat segment semantics.

- [ ] **Step 3: Update serialization**

Replace `segment_to_dict()` with:

```python
def node_to_dict(node: DirectoryNode) -> dict[str, Any]:
    return {
        "note_stem": node.note_stem,
        "filename": node.filename,
        "output_path": str(node.output_path),
        "parent": node.parent.note_stem if node.parent else "",
        "children": [child.note_stem for child in node.children],
        "is_leaf": node.is_leaf,
        "is_special_merge": node.is_special_merge,
        "raw_start": node.raw_start,
        "raw_end": node.raw_end,
        "warning": node.warning,
    }
```

Update `plan_to_manifest()` to include `nodes`, `leaf_nodes`, `directory_nodes`, `top_level_nodes`, and `special_merges`.

- [ ] **Step 4: Update `plan_json()` and `command_segment()`**

Make `plan_json()` report:

```python
"counts": plan.counts,
"nodes": [node_to_dict(node) for node in plan.nodes],
"special_merges": plan.special_merges,
```

Make segment output include:

```python
"nodes": len(plan.nodes),
"leaf_nodes": len(plan.leaf_nodes),
"directory_nodes": len(plan.directory_nodes),
```

Do not keep only the ambiguous old `"segments"` field. If backward compatibility is desired, include `"segments": len(plan.leaf_nodes)` only with `"leaf_nodes"` also present.

- [ ] **Step 5: Update verification**

Implement:

```python
LINK_RE = re.compile(r"^- \[\[([^\]]+)\]\]$")


def extract_directory_links(text: str) -> list[str]:
    links: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "# 目录":
            continue
        match = LINK_RE.fullmatch(stripped)
        if not match:
            raise SegmentationError(f"Invalid Obsidian link line: {line}")
        target = match.group(1)
        if target.startswith("#") or target.startswith("##"):
            raise SegmentationError(f"Heading marker found inside wikilink target: {target}")
        links.append(target)
    return links
```

Update `verify_package()`:

- master links must equal `[link_for_node(node) for node in plan.top_level_nodes]`;
- every non-leaf node links exactly to `[link_for_node(child) for child in node.children]`;
- every linked target has a matching file;
- every leaf file exists and has non-empty text;
- special merged leaf text contains generic and specific headings;
- no `阅读与思考.md` exists for merged pairs;
- source hash unchanged.

- [ ] **Step 6: Update run records**

Use `plan.counts` in `run-state.json`. Update `run-summary.md` labels:

```text
Node count: ...
Directory node count: ...
Leaf node count: ...
Special merge count: ...
```

- [ ] **Step 7: Run tests**

Run:

```powershell
pytest tests/test_mathos_segmentation_stage1.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add tests/test_mathos_segmentation_stage1.py skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py
git commit -m "feat: verify layered segmentation packages"
```

## Task 5: Update Skill Documentation

**Files:**
- Modify: `skills/mathos-segmentation-stage1/SKILL.md`
- Modify: `docs/agent/skill-registry.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update `SKILL.md`**

Replace flat-output wording with:

```markdown
## Output Semantics

For `高中\课本\book.md`, output is written to:

```text
高中\课本\book\
├── 000_book目录.md
├── 第六章 平面向量及其应用.md
├── 6.1 平面向量的概念.md
├── 6.1.1 向量的实际背景与概念.md
└── 阅读与思考 向量及向量符号的由来.md
```

The master directory links only to top-level chapter files.

Every non-leaf note contains only `# 目录` plus immediate-child file links.

Leaf notes contain raw source slices. The operator does not prepend headings, front matter, comments, or metadata.

Special pairs such as `## 阅读与思考` followed by `### 向量及向量符号的由来` are merged into one leaf note.
```

Ensure the Markdown fence is correctly closed in the real file.

- [ ] **Step 2: Update registry**

In `docs/agent/skill-registry.md`, update the segmentation behavior bullets:

```markdown
- Builds a layered Obsidian package from formatted Markdown body headings.
- Writes a master directory that links only to top-level chapter notes.
- Writes non-leaf notes as pure directory notes with immediate-child links only.
- Writes raw source slices only to leaf notes.
- Merges conservative special heading pairs such as `阅读与思考` plus its following specific subheading.
```

- [ ] **Step 3: Update `AGENTS.md` if needed**

Under segmentation stop conditions, add:

```markdown
- Layered package verification failure, including directory notes linking to grandchildren or missing generated files.
```

- [ ] **Step 4: Run doc grep**

Run:

```powershell
Select-String -Path AGENTS.md,docs\agent\skill-registry.md,skills\mathos-segmentation-stage1\SKILL.md -Pattern 'layered|immediate-child|阅读与思考|leaf'
```

Expected: all three docs mention the corrected behavior where appropriate.

- [ ] **Step 5: Commit**

```powershell
git add AGENTS.md docs/agent/skill-registry.md skills/mathos-segmentation-stage1/SKILL.md
git commit -m "docs: describe layered segmentation behavior"
```

## Task 6: Final Verification and Real Textbook Smoke Test

**Files:**
- No source edits unless verification reveals defects.

- [ ] **Step 1: Run full tests**

Run:

```powershell
pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run temp-vault CLI smoke test**

Run:

```powershell
$tmp = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("mathos-layered-segmentation-" + [guid]::NewGuid()))
$vault = New-Item -ItemType Directory -Path (Join-Path $tmp.FullName "vault")
$source = Join-Path $vault.FullName "book.md"
@'
# 第六章 平面向量及其应用

## 6.1 平面向量的概念

### 6.1.1 向量的实际背景与概念

正文 A

## 阅读与思考

### 向量及向量符号的由来

阅读正文

# 第七章 复数

## 7.1 复数的概念

### 7.1.1 数系的扩充和复数的概念

正文 B
'@ | Set-Content -Path $source -Encoding UTF8
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py plan $source --vault-root $vault.FullName --yes
python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py segment $source --vault-root $vault.FullName --yes
Get-ChildItem -Recurse $vault.FullName
Get-Content (Join-Path $vault.FullName "book\000_book目录.md")
Get-Content (Join-Path $vault.FullName "book\第六章 平面向量及其应用.md")
Get-Content (Join-Path $vault.FullName "book\阅读与思考 向量及向量符号的由来.md")
```

Expected:

- master links only to `第六章 平面向量及其应用` and `第七章 复数`;
- `第六章 平面向量及其应用.md` links only to `6.1 平面向量的概念` and `阅读与思考 向量及向量符号的由来`;
- special leaf includes both `## 阅读与思考` and `### 向量及向量符号的由来`;
- no `阅读与思考.md` exists;
- source file remains present.

- [ ] **Step 3: Optional real textbook dry-run**

Run `plan` only against:

```text
C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\高中\课本\【人教版】高中必修 第二册数学电子课本.md
```

with vault root:

```text
C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map
```

Expected: JSON reports top-level nodes including `第六章 平面向量及其应用`, `第七章 复数`, `第八章 立体几何初步`; do not write to the real vault in this step.

- [ ] **Step 4: Inspect status**

Run:

```powershell
git status --short
```

Expected: no tracked-file changes. Untracked existing `agent-memory/records` from prior user runs may remain; do not delete them unless explicitly instructed.

- [ ] **Step 5: Summarize**

Report:

- test command and pass count;
- temp smoke-test result;
- real textbook plan result if run;
- final commit range;
- whether any untracked pre-existing run records remain.
