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
ALL_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_TITLE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")
CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百]+章\s+(.+)$")
SPECIAL_PAIR_LABELS = {"阅读与思考", "数学探究"}
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class SegmentationError(Exception):
    """Raised when stage-one segmentation cannot continue safely."""


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


@dataclass
class DirectoryNode:
    source_heading: Heading
    note_stem: str
    filename: str = ""
    output_path: Path | None = None
    parent: DirectoryNode | None = None
    children: list[DirectoryNode] = field(default_factory=list)
    raw_start: int = 0
    raw_end: int = 0
    is_leaf: bool = True
    is_special_merge: bool = False
    merged_heading: Heading | None = None
    warning: str = ""
    byte_count: int = 0

    @property
    def heading(self) -> Heading:
        return self.source_heading

    @property
    def link_title(self) -> str:
        return self.note_stem

    @property
    def char_start(self) -> int:
        return self.raw_start

    @property
    def char_end(self) -> int:
        return self.raw_end


@dataclass(frozen=True)
class SegmentationPlan:
    source_path: Path
    vault_root: Path
    sandbox_dir: Path
    master_path: Path
    target_depth: int
    detected_number_depths: list[int]
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
    def segments(self) -> list[DirectoryNode]:
        return self.leaf_nodes

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

def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def quote_command(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def safe_filename(stem: str) -> str:
    cleaned = INVALID_FILENAME_CHARS_RE.sub("_", stem).strip().rstrip(" .")
    return cleaned or "segment"


def disambiguate_filenames(link_titles: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    seen: dict[str, int] = {}
    filenames: list[str] = []
    disambiguations: list[dict[str, str]] = []

    for link_title in link_titles:
        base = safe_filename(link_title)
        key = base.casefold()
        count = seen.get(key, 0) + 1
        seen[key] = count
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


def extract_numbered_headings(markdown: str) -> list[Heading]:
    headings: list[Heading] = []
    char_offset = 0

    for line_index, line in enumerate(markdown.splitlines(keepends=True)):
        line_text = line.rstrip("\r\n")
        match = HEADING_RE.match(line_text)
        if match:
            marker, full_title, number, title = match.groups()
            headings.append(
                Heading(
                    marker=marker,
                    markdown_depth=len(marker),
                    number=number,
                    number_depth=number.count(".") + 1,
                    title=title,
                    full_title=full_title,
                    line_index=line_index,
                    char_start=char_offset,
                    char_end=char_offset + len(line),
                )
            )
        char_offset += len(line)

    return headings


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


def select_target_depth(headings: list[Heading], requested_depth: int | None) -> int:
    if not headings:
        raise SegmentationError("No numbered headings detected")

    if requested_depth is None:
        return max(heading.number_depth for heading in headings)

    if not any(heading.number_depth == requested_depth for heading in headings):
        raise SegmentationError(f"Target depth {requested_depth} produced zero segments")

    return requested_depth


def node_level(heading: Heading) -> int:
    return heading.markdown_depth


def is_chapter_heading(heading: Heading) -> bool:
    return heading.markdown_depth == 1 and CHAPTER_RE.match(heading.full_title) is not None


def build_directory_tree(
    headings: list[Heading], markdown: str, sandbox_dir: Path
) -> tuple[list[DirectoryNode], list[DirectoryNode], list[dict[str, str]], list[str]]:
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
                special_merges.append(
                    {"generic": heading.full_title, "specific": candidate.full_title, "merged": note_stem}
                )
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
        raw_slice = markdown[node.raw_start:node.raw_end]
        node.byte_count = len(raw_slice.encode("utf-8"))
    return [node for node in nodes if node.parent is None], nodes, special_merges, warnings


def assign_node_paths(nodes: list[DirectoryNode], sandbox_dir: Path) -> list[dict[str, str]]:
    filenames, disambiguations = disambiguate_filenames([node.note_stem for node in nodes])
    for node, filename in zip(nodes, filenames):
        node.filename = filename
        node.output_path = sandbox_dir / filename
    return disambiguations


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

    headings = extract_all_headings(markdown)
    if not headings:
        raise SegmentationError("No Markdown headings detected")

    numbered_headings = extract_numbered_headings(markdown)
    if not numbered_headings:
        raise SegmentationError("No numbered headings detected")

    selected_depth = select_target_depth(numbered_headings, target_depth)
    detected_depths = sorted({heading.number_depth for heading in numbered_headings})

    sandbox_dir = source_path.with_suffix("")
    master_path = sandbox_dir / f"000_{source_path.stem}目录.md"

    top_level_nodes, nodes, special_merges, warnings = build_directory_tree(headings, markdown, sandbox_dir)
    if not top_level_nodes:
        raise SegmentationError("No top-level directory nodes detected")

    disambiguations = assign_node_paths(nodes, sandbox_dir)
    leaf_nodes = [node for node in nodes if node.is_leaf]
    directory_nodes = [node for node in nodes if not node.is_leaf]
    if not leaf_nodes:
        raise SegmentationError("No leaf nodes detected")

    # Add warning for large leaf nodes
    for node in leaf_nodes:
        raw_slice = markdown[node.raw_start:node.raw_end]
        if len(raw_slice) > 200_000:
            warning = f"Large segment: {node.note_stem} ({len(raw_slice)} characters)"
            node.warning = warning
            warnings.append(warning)

    return SegmentationPlan(
        source_path=source_path,
        vault_root=vault_root,
        sandbox_dir=sandbox_dir,
        master_path=master_path,
        target_depth=selected_depth,
        detected_number_depths=detected_depths,
        headings=headings,
        top_level_nodes=top_level_nodes,
        nodes=nodes,
        leaf_nodes=leaf_nodes,
        directory_nodes=directory_nodes,
        disambiguations=disambiguations,
        special_merges=special_merges,
        warnings=warnings,
        source_sha256=sha256_text(markdown),
        next_command=build_segment_command(source_path, vault_root, target_depth),
    )


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_segmentation_package(plan: SegmentationPlan, overwrite: bool = False) -> dict[str, Any]:
    markdown = plan.source_path.read_text(encoding="utf-8")
    before_file_hash = file_sha256(plan.source_path)
    if sha256_text(markdown) != plan.source_sha256:
        raise SegmentationError("Original source hash changed before writing")
    if plan.sandbox_dir.exists():
        if not overwrite:
            raise SegmentationError(f"Output sandbox folder already exists: {plan.sandbox_dir}")
        if not plan.sandbox_dir.is_dir():
            raise SegmentationError(f"Output sandbox path exists and is not a directory: {plan.sandbox_dir}")
        shutil.rmtree(plan.sandbox_dir)

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

    after_file_hash = file_sha256(plan.source_path)
    if after_file_hash != before_file_hash:
        raise SegmentationError("Original source hash changed during writing")
    return {"status": "written", "sandbox_dir": str(plan.sandbox_dir), "master_path": str(plan.master_path)}


def run_record_dir(source_path: Path, repo_root: Path = Path(".")) -> Path:
    slug = safe_filename(source_path.stem)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return repo_root / "agent-memory" / "records" / f"{stamp}-segmentation-stage1-{slug}"


def heading_to_dict(heading: Heading) -> dict[str, Any]:
    return dataclasses.asdict(heading)


def segment_to_dict(segment: DirectoryNode) -> dict[str, Any]:
    return {
        "heading": dataclasses.asdict(segment.source_heading),
        "link_title": segment.note_stem,
        "filename": segment.filename,
        "output_path": str(segment.output_path),
        "char_start": segment.raw_start,
        "char_end": segment.raw_end,
        "byte_count": segment.byte_count,
        "warning": segment.warning,
    }


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
        "nodes": [node_to_dict(node) for node in plan.nodes],
        "segments": [segment_to_dict(segment) for segment in plan.segments],
        "disambiguations": plan.disambiguations,
        "special_merges": plan.special_merges,
        "warnings": plan.warnings,
        "next_command": plan.next_command,
    }


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


def verify_package(plan: SegmentationPlan) -> dict[str, Any]:
    if not plan.sandbox_dir.is_dir():
        raise SegmentationError(f"Missing sandbox folder: {plan.sandbox_dir}")
    if not plan.master_path.is_file():
        raise SegmentationError(f"Missing master directory: {plan.master_path}")

    # 1. Master links verification
    master_text = plan.master_path.read_text(encoding="utf-8")
    master_links = extract_directory_links(master_text)
    expected_master_links = [link_for_node(node) for node in plan.top_level_nodes]
    if master_links != expected_master_links:
        raise SegmentationError("Master directory links do not match top-level chapters")

    # 2. Files and intermediate children links verification
    for node in plan.nodes:
        if not node.output_path.is_file():
            raise SegmentationError(f"Missing node file: {node.output_path}")

        file_text = node.output_path.read_text(encoding="utf-8")
        if not file_text.strip():
            raise SegmentationError(f"Empty node file: {node.output_path}")

        if node.is_leaf:
            # Leaf files must contain the heading
            if node.is_special_merge:
                if node.source_heading.full_title not in file_text:
                    raise SegmentationError(
                        f"Merged heading missing in leaf text: {node.source_heading.full_title}"
                    )
                if node.merged_heading and node.merged_heading.full_title not in file_text:
                    raise SegmentationError(
                        f"Merged specific heading missing in leaf text: {node.merged_heading.full_title}"
                    )
            else:
                if node.source_heading.full_title not in file_text:
                    raise SegmentationError(f"Heading missing in leaf text: {node.source_heading.full_title}")
        else:
            # Directory notes verification
            dir_links = extract_directory_links(file_text)
            expected_links = [link_for_node(child) for child in node.children]
            if dir_links != expected_links:
                raise SegmentationError(f"Directory links do not match immediate children for {node.note_stem}")

    # 3. Ensure no unmerged reading/thinking files exist
    for merge in plan.special_merges:
        generic_file = plan.sandbox_dir / (safe_filename(merge["generic"]) + ".md")
        if generic_file.exists():
            raise SegmentationError(f"Unmerged generic file should not exist: {generic_file}")

    # 4. Check total file count
    expected_files = {plan.master_path.resolve()} | {node.output_path.resolve() for node in plan.nodes}
    actual_files = {p.resolve() for p in plan.sandbox_dir.glob("*.md")}
    if actual_files != expected_files:
        extra_files = actual_files - expected_files
        missing_files = expected_files - actual_files
        raise SegmentationError(
            f"File count mismatch in sandbox. Extra: {extra_files}, Missing: {missing_files}"
        )

    # 5. Source hash check
    if sha256_text(plan.source_path.read_text(encoding="utf-8")) != plan.source_sha256:
        raise SegmentationError("Original source hash changed")

    return {"status": "passed", "node_count": len(plan.nodes), "leaf_count": len(plan.leaf_nodes), "segment_count": len(plan.leaf_nodes)}


def write_run_records(
    plan: SegmentationPlan,
    repo_root: Path = Path("."),
    status: str = "completed",
    stop_reason: str = "",
) -> Path:
    record_dir = run_record_dir(plan.source_path, repo_root=repo_root)
    record_dir.mkdir(parents=True, exist_ok=False)
    verification = verify_package(plan) if status == "completed" else {"status": "not-run"}
    manifest = plan_to_manifest(plan)
    manifest["verification"] = verification
    next_step = "review sandbox package in Obsidian" if status == "completed" else "inspect failure and rerun plan"
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
            "nodes": len(plan.nodes),
            "directory_nodes": len(plan.directory_nodes),
            "leaf_nodes": len(plan.leaf_nodes),
            "special_merges": len(plan.special_merges),
            "warnings": len(plan.warnings),
            "disambiguations": len(plan.disambiguations),
            "segments": len(plan.leaf_nodes),  # for backward compatibility
        },
        "warnings": plan.warnings[:20],
        "records": {
            "manifest": str(record_dir / "manifest.json"),
            "run_summary": str(record_dir / "run-summary.md"),
            "run_state": str(record_dir / "run-state.json"),
        },
        "next_step": next_step,
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
Node count: {len(plan.nodes)}
Directory node count: {len(plan.directory_nodes)}
Leaf node count: {len(plan.leaf_nodes)}
Special merge count: {len(plan.special_merges)}
Segment count: {len(plan.leaf_nodes)}
Warning count: {len(plan.warnings)}
Duplicate disambiguation count: {len(plan.disambiguations)}
Run record folder: `{record_dir}`
Next operational step: {next_step}
"""
    (record_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (record_dir / "run-state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (record_dir / "run-summary.md").write_text(summary, encoding="utf-8")
    return record_dir


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
            "nodes": len(plan.nodes),
            "directory_nodes": len(plan.directory_nodes),
            "leaf_nodes": len(plan.leaf_nodes),
            "special_merges": len(plan.special_merges),
            "warnings": len(plan.warnings),
            "disambiguations": len(plan.disambiguations),
            "segments": len(plan.leaf_nodes),  # for backward compatibility
        },
        "nodes": [node_to_dict(node) for node in plan.nodes],
        "special_merges": plan.special_merges,
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
            "nodes": len(plan.nodes),
            "leaf_nodes": len(plan.leaf_nodes),
            "directory_nodes": len(plan.directory_nodes),
            "segments": len(plan.leaf_nodes),
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
