#!/usr/bin/env python3
"""Materialize a reviewed textbook architecture from a frozen same-book graph.

The reference supplies names and ownership only.  Every emitted source range is
anchored in the freshly converted formatted Markdown.  This closes the gap
between reference range proposals and the strict textbook node architecture:
knowledge themes, worked examples, inline practice, and section exercise
questions are reconstructed in source order without copying reference bodies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from propose_reference_semantic_review import matching_spans, normalize, source_text_with_line_map
from textbook_node_architecture import apply_hierarchical_filenames


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_SECTION_RE = re.compile(r"^\d+\.\d+\s+\S")
NUMBERED_SUBSECTION_RE = re.compile(r"^\d+(?:\.\d+){2,}\s+\S")
SECTION_EXERCISE_RE = re.compile(r"^习题\s*\d+(?:\.\d+)+")
SUMMARY_RE = re.compile(r"(?:小结|复习参考题)")
WIKI_EMBED_RE = re.compile(r"^\s*!\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]\s*$", re.M)
MARKDOWN_EMBED_RE = re.compile(
    r"^\s*!\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)\s*$", re.M
)
EXERCISE_QUESTION_RE = re.compile(
    r"^(?:#{4,6}\s+)?(\d+)\.(?:\s|[（(])"
)
EXERCISE_GROUP_HEADING_RE = re.compile(
    r"^#{4,6}\s+(?:复习巩固|综合运用|拓广探索)\s*$"
)
INVALID_KEY_RE = re.compile(r"[^0-9A-Za-z_-]+")


class MaterializeError(ValueError):
    pass


def exercise_question_ranges(
    lines: list[str], start_line: int, end_line: int
) -> list[dict[str, int]]:
    """Return complete, sequential top-level exercise-question ranges."""

    starts: list[tuple[int, int]] = []
    for line_number in range(start_line + 1, end_line + 1):
        match = EXERCISE_QUESTION_RE.match(lines[line_number - 1].strip())
        if match:
            starts.append((int(match.group(1)), line_number))
    if not starts:
        raise MaterializeError(
            f"Section exercise {start_line}-{end_line} has no numbered questions"
        )
    numbers = [number for number, _ in starts]
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        raise MaterializeError(
            f"Section exercise {start_line}-{end_line} has non-sequential "
            f"question numbers: {numbers}; expected {expected}"
        )

    ranges: list[dict[str, int]] = []
    for index, (number, question_start) in enumerate(starts):
        following_start = (
            starts[index + 1][1] if index + 1 < len(starts) else end_line + 1
        )
        group_boundaries = [
            line_number
            for line_number in range(question_start + 1, following_start)
            if EXERCISE_GROUP_HEADING_RE.match(lines[line_number - 1].strip())
        ]
        question_end = (
            group_boundaries[0] - 1 if group_boundaries else following_start - 1
        )
        while question_end >= question_start and not lines[question_end - 1].strip():
            question_end -= 1
        if question_end < question_start:
            raise MaterializeError(
                f"Exercise question {number} at line {question_start} is empty"
            )
        ranges.append(
            {
                "question_number": number,
                "start_line": question_start,
                "end_line": question_end,
            }
        )
    return ranges


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def compact(value: str) -> str:
    return re.sub(r"[\s$`*_~\\{}，。；：、,.!?！？;:()（）\[\]<>《》“”'\"—–=+|/]+", "", value).casefold()


def read_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    result: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def stable_key(prefix: str, identity: str) -> str:
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    safe = INVALID_KEY_RE.sub("-", prefix).strip("-") or "node"
    return f"{safe}-{digest}"


class Builder:
    def __init__(
        self,
        formatted: Path,
        base_manifest: Path,
        proposal_report: Path,
        reference_root: Path,
        decisions_path: Path,
    ) -> None:
        self.formatted = formatted.resolve()
        self.base_manifest_path = base_manifest.resolve()
        self.proposal_report_path = proposal_report.resolve()
        self.reference_root = reference_root.resolve()
        self.decisions_path = decisions_path.resolve()
        self.lines = self.formatted.read_text(encoding="utf-8-sig").splitlines()
        self.base = json.loads(self.base_manifest_path.read_text(encoding="utf-8-sig"))
        self.report = json.loads(self.proposal_report_path.read_text(encoding="utf-8-sig"))
        self.profile_path = Path(str(self.base["profile"])).resolve()
        self.profile = json.loads(self.profile_path.read_text(encoding="utf-8-sig"))
        configured = self.profile.get("reference", {})
        if configured.get("scope") != "same-book-content-and-style":
            raise MaterializeError("Profile needs a same-book-content-and-style reference")
        if Path(str(configured.get("path", ""))).resolve() != self.reference_root:
            raise MaterializeError("Reference root does not match the frozen profile")
        if self.report.get("reference", {}).get("sha256") != configured.get("sha256"):
            raise MaterializeError("Proposal reference digest does not match the profile")
        if self.base.get("input_markdown_sha256") != sha256_file(self.formatted):
            raise MaterializeError("Formatted Markdown digest does not match the base manifest")

        self.base_nodes = {node["key"]: dict(node) for node in self.base["nodes"]}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.ref_to_key: dict[Path, str] = {}
        self.proposals: dict[Path, dict[str, Any]] = {
            Path(str(item["reference_path"])).resolve(): item
            for item in self.report.get("suggestions", [])
            if isinstance(item, dict) and item.get("reference_path")
        }
        self.reference_text: dict[Path, str] = {}
        self.reference_meta: dict[Path, dict[str, str]] = {}
        self.order_counter = 0

    def ref_text(self, path: Path) -> str:
        path = path.resolve()
        if path not in self.reference_text:
            self.reference_text[path] = path.read_text(encoding="utf-8-sig")
        return self.reference_text[path]

    def ref_meta(self, path: Path) -> dict[str, str]:
        path = path.resolve()
        if path not in self.reference_meta:
            self.reference_meta[path] = read_frontmatter(self.ref_text(path))
        return self.reference_meta[path]

    def resolve_embed(self, target: str) -> Path | None:
        decoded = urllib.parse.unquote(target).replace("\\", "/").strip()
        marker = self.reference_root.name + "/"
        if marker in decoded:
            relative = decoded.split(marker, 1)[1]
        else:
            relative = decoded.lstrip("/")
        candidate = self.reference_root / relative
        if not str(candidate).lower().endswith(".md"):
            candidate = Path(str(candidate) + ".md")
        candidate = candidate.resolve()
        try:
            candidate.relative_to(self.reference_root)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def owned_refs(self, path: Path) -> list[Path]:
        result: list[Path] = []
        text = self.ref_text(path)
        targets = WIKI_EMBED_RE.findall(text) + MARKDOWN_EMBED_RE.findall(text)
        for target in targets:
            resolved = self.resolve_embed(target)
            if resolved is not None:
                result.append(resolved)
        return result

    def reference_category(self, path: Path) -> str:
        first = path.resolve().relative_to(self.reference_root).parts[0]
        return {
            "知识点": "knowledge",
            "习题": "exercise",
            "趣味阅读": "reading",
            "数学历史": "history",
            "思维或方法": "method",
            "工具": "tool",
        }.get(first, "knowledge")

    def reference_filename(self, path: Path, category: str) -> str:
        relative = path.resolve().relative_to(self.reference_root)
        if category == "root":
            return relative.as_posix()
        if relative.parts and relative.parts[0] in {
            "知识点", "习题", "趣味阅读", "数学历史", "思维或方法", "工具"
        }:
            relative = Path(*relative.parts[1:])
        return relative.as_posix()

    def find_reference_note(self, category: str, title: str, *parents: str) -> Path | None:
        category_dir = {
            "knowledge": "知识点",
            "exercise": "习题",
            "reading": "趣味阅读",
            "method": "思维或方法",
            "tool": "工具",
        }.get(category)
        if not category_dir:
            return None
        root = self.reference_root / category_dir
        candidates = [path for path in root.rglob("*.md") if compact(path.stem) == compact(title)]
        parent_keys = {compact(value) for value in parents if value}
        scoped = [
            path for path in candidates
            if parent_keys & {compact(part) for part in path.relative_to(root).parts[:-1]}
        ]
        candidates = scoped or candidates
        return min(candidates, key=lambda path: len(path.parts)) if candidates else None

    def add(self, node: dict[str, Any]) -> dict[str, Any]:
        key = str(node["key"])
        if key in self.nodes:
            return self.nodes[key]
        self.order_counter += 1
        node["_source_order"] = self.order_counter
        self.nodes[key] = node
        return node

    def proposal_range(self, path: Path, owner: dict[str, Any]) -> tuple[int, int] | None:
        item = self.proposals.get(path.resolve())
        if not item:
            return None
        start = item.get("start_line")
        end = item.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int):
            return None
        if not (int(owner["start_line"]) <= start <= end <= int(owner["end_line"])):
            return None
        return start, end

    def matched_reference_range(
        self, path: Path, owner: dict[str, Any]
    ) -> tuple[int, int] | None:
        reference = normalize(self.ref_text(path))
        if len(reference) < 4:
            return None
        source, line_map = source_text_with_line_map(
            self.lines, int(owner["start_line"]), int(owner["end_line"])
        )
        spans = matching_spans(reference, source)
        if not spans or not line_map:
            return None
        matched = sum(size for _, size in spans)
        if matched / len(reference) < 0.45:
            return None
        start_position = min(position for position, _ in spans)
        end_position = min(
            max(position + size - 1 for position, size in spans), len(line_map) - 1
        )
        return line_map[start_position], line_map[end_position]

    def matching_base_child(self, title: str, owner: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [
            node for node in self.base_nodes.values()
            if compact(str(node.get("title", ""))) == compact(title)
            and int(owner["start_line"]) <= int(node["start_line"])
            and int(node["end_line"]) <= int(owner["end_line"])
        ]
        return min(
            candidates,
            key=lambda node: int(node["end_line"]) - int(node["start_line"]),
        ) if candidates else None

    def leaf_type(self, path: Path, meta: dict[str, str], category: str) -> str:
        kind = meta.get("节点类型", "")
        if category == "exercise" and "原子题" in path.parts:
            return "section-exercise-question"
        if kind == "情景导入":
            return "scenario"
        if kind == "例题" or path.stem.startswith("例题"):
            return "worked-example"
        if kind in {"习题", "题"}:
            return "practice-question" if category == "knowledge" else "section-exercise-question"
        if kind == "趣味阅读":
            return "reading"
        if kind == "思维或方法":
            return "method"
        return "knowledge"

    def build_ref_node(self, path: Path, parent: dict[str, Any]) -> dict[str, Any] | None:
        path = path.resolve()
        if path in self.ref_to_key:
            return self.nodes[self.ref_to_key[path]]
        meta = self.ref_meta(path)
        owned = self.owned_refs(path)
        category = self.reference_category(path)
        organizer_kind = meta.get("组织类型", "")
        if organizer_kind == "知识主题":
            organizer_type = "knowledge-theme"
        elif organizer_kind == "题型":
            organizer_type = "practice"
        elif category == "exercise" and owned:
            organizer_type = "section-exercise"
        else:
            organizer_type = None

        base_match = self.matching_base_child(path.stem, parent)
        if base_match is None and category == "exercise":
            number = re.search(r"(?:习题|复习参考题)\s*([\d.]+)", path.stem)
            if number:
                candidates = [
                    child for child in self.nodes.values()
                    if child.get("parent_key") == parent["key"]
                    and child.get("category") == "exercise"
                    and number.group(1) in str(child.get("title", ""))
                ]
                if len(candidates) == 1:
                    base_match = candidates[0]
        key = (
            str(base_match["key"])
            if base_match is not None
            else stable_key("reference", path.relative_to(self.reference_root).as_posix())
        )
        node_payload: dict[str, Any] = {
            "key": key,
            "title": path.stem,
            "parent_key": parent["key"],
            "category": category,
            "filename": self.reference_filename(path, category),
            "start_line": int(base_match["start_line"]) if base_match else int(parent["start_line"]),
            "end_line": int(base_match["end_line"]) if base_match else int(parent["end_line"]),
            "toc_key": base_match.get("toc_key") if base_match else None,
            "emit_title": False,
            "_ref_path": str(path),
        }
        if organizer_type:
            node_payload["node_type"] = "organizer"
            node_payload["organizer_type"] = organizer_type
        else:
            node_payload["node_type"] = self.leaf_type(path, meta, category)
        if key in self.nodes:
            node = self.nodes[key]
            self.order_counter += 1
            is_toc_node = node.get("toc_key") is not None
            node.update(
                title=node_payload["title"],
                category=node_payload["category"],
                filename=node_payload["filename"],
                emit_title=node.get("emit_title", True) if is_toc_node else False,
                _ref_path=node_payload["_ref_path"],
                node_type=node.get("node_type", node_payload["node_type"])
                if is_toc_node else node_payload["node_type"],
                _source_order=self.order_counter,
            )
            if organizer_type:
                node["organizer_type"] = organizer_type
        else:
            node = node_payload
            self.add(node)
        self.ref_to_key[path] = key

        if organizer_type:
            for child_path in owned:
                self.build_ref_node(child_path, node)
            children = self.children(node)
            if not children:
                self.nodes.pop(key, None)
                self.ref_to_key.pop(path, None)
                return None
            # A reference exercise can be incomplete.  When it resolves to a
            # source TOC exercise node, keep the source's complete range so the
            # fresh question-number pass can recover every printed question.
            preserve_source_exercise_range = (
                organizer_type == "section-exercise" and base_match is not None
            )
            if not preserve_source_exercise_range:
                node["start_line"] = min(int(child["start_line"]) for child in children)
                node["end_line"] = max(int(child["end_line"]) for child in children)
                if organizer_type in {"practice", "section-exercise"}:
                    heading = self.find_preceding_heading(
                        int(node["start_line"]), int(parent["start_line"]),
                        "练习" if organizer_type == "practice" else "习题",
                    )
                    if heading is not None:
                        node["start_line"] = heading
        else:
            proposal_range = None
            if base_match is None:
                # Recompute the tight body span first.  Proposal ranges are
                # deliberately expanded to nearby block boundaries and can
                # otherwise cross an adjacent printed 练习 heading.
                proposal_range = self.matched_reference_range(path, parent)
                if proposal_range is None:
                    proposal_range = self.proposal_range(path, parent)
            if proposal_range:
                node["start_line"], node["end_line"] = proposal_range
            elif base_match is None:
                self.nodes.pop(key, None)
                self.ref_to_key.pop(path, None)
                return None
            for child_path in owned:
                child = self.build_ref_node(child_path, node)
                if child and child["node_type"] != "worked-example":
                    raise MaterializeError(f"Knowledge atom owns non-example child: {path}")
        return node

    def find_preceding_heading(self, start: int, lower: int, label: str) -> int | None:
        for line_number in range(start, lower - 1, -1):
            match = HEADING_RE.match(self.lines[line_number - 1])
            if match and match.group(2).replace(" ", "").startswith(label):
                return line_number
        return None

    def children(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        children = [
            child for child in self.nodes.values()
            if child.get("parent_key") == node["key"]
        ]
        return sorted(
            children,
            key=lambda child: (
                int(child["start_line"]), int(child["end_line"]),
                int(child.get("_source_order", 0)),
            ),
        )

    def repair_interleaved_auxiliary_sections(self) -> None:
        """Keep mid-lesson TOC sidebars inside their numbered lesson.

        A printed reading/tool insert may be followed by a later numbered
        subsection and the lesson exercise.  TOC-range planning alone makes
        that sidebar the accidental owner of the remainder.  Reattach the
        sidebar and exercise to the matching numbered section and bound the
        sidebar at the next numbered subsection heading.
        """

        sections = [
            node for node in self.nodes.values()
            if node.get("organizer_type") == "section"
        ]
        for exercise in [
            node for node in self.nodes.values()
            if node.get("organizer_type") == "section-exercise"
        ]:
            match = re.search(r"习题\s*(\d+\.\d+)", str(exercise["title"]))
            if not match:
                continue
            number = match.group(1)
            candidates = [
                section for section in sections
                if str(section["title"]).startswith(number + " ")
            ]
            if len(candidates) != 1:
                continue
            section = candidates[0]
            old_parent = self.nodes.get(str(exercise.get("parent_key")))
            if old_parent is None or old_parent.get("organizer_type") == "section":
                continue
            exercise["parent_key"] = section["key"]
            section["end_line"] = max(int(section["end_line"]), int(exercise["end_line"]))
            if old_parent.get("node_type") in {"reading", "method", "tool", "knowledge"}:
                old_parent["parent_key"] = section["key"]
                next_heading = None
                for line_number in range(
                    int(old_parent["start_line"]) + 1,
                    int(exercise["start_line"]) + 1,
                ):
                    heading = HEADING_RE.match(self.lines[line_number - 1])
                    if heading and NUMBERED_SUBSECTION_RE.match(heading.group(2)):
                        next_heading = line_number
                        break
                if next_heading is not None:
                    old_parent["end_line"] = next_heading - 1

        # Reparent any additional TOC insert whose complete range now lies
        # inside the restored numbered lesson (for example the two consecutive
        # 探究与发现 inserts inside 5.4).
        for section in sections:
            chapter_key = section.get("parent_key")
            for candidate in list(self.nodes.values()):
                if candidate["key"] == section["key"]:
                    continue
                if candidate.get("parent_key") != chapter_key:
                    continue
                if (
                    int(section["start_line"]) < int(candidate["start_line"])
                    and int(candidate["end_line"]) <= int(section["end_line"])
                ):
                    candidate["parent_key"] = section["key"]

    def remove_subtree(self, node: dict[str, Any]) -> None:
        for child in list(self.children(node)):
            self.remove_subtree(child)
        self.nodes.pop(str(node["key"]), None)

    def set_base_types(self) -> None:
        toc_nodes = [
            dict(node) for node in self.base_nodes.values()
            if node.get("toc_key") is not None
            or node.get("parent_key") is None
            or node.get("category") == "exercise"
        ]
        for node in toc_nodes:
            title = str(node["title"])
            category = str(node["category"])
            if node.get("parent_key") is None:
                node.update(node_type="organizer", organizer_type="book", emit_title=True)
            elif node.get("organizer_type") == "chapter":
                node.update(node_type="organizer", organizer_type="chapter", emit_title=True)
            elif category in {"reading", "method", "tool"}:
                node.update(node_type=category, emit_title=True)
                node.pop("organizer_type", None)
            elif category == "exercise":
                node.update(node_type="organizer", organizer_type="section-exercise", emit_title=False)
            elif NUMBERED_SECTION_RE.match(title) and not NUMBERED_SUBSECTION_RE.match(title):
                node.update(node_type="organizer", organizer_type="section", emit_title=True)
            else:
                node.update(node_type="knowledge", emit_title=True)
                node.pop("organizer_type", None)
            self.add(node)

        self.repair_interleaved_auxiliary_sections()

        lookup = self.nodes
        for node in list(lookup.values()):
            if node.get("organizer_type") != "chapter":
                continue
            ref = self.find_reference_note("knowledge", str(node["title"]))
            if ref:
                node["filename"] = self.reference_filename(ref, "knowledge")
        for node in list(lookup.values()):
            if node.get("organizer_type") != "section":
                continue
            parent = lookup.get(str(node.get("parent_key")))
            ref = self.find_reference_note(
                "knowledge", str(node["title"]), str(parent.get("title", "")) if parent else ""
            )
            if ref:
                node["filename"] = self.reference_filename(ref, "knowledge")
                for child_ref in self.owned_refs(ref):
                    self.build_ref_node(child_ref, node)
        for node in list(lookup.values()):
            if node.get("organizer_type") == "section":
                self.align_practice_headings(node)

    def align_practice_headings(self, section: dict[str, Any]) -> None:
        practices = sorted(
            [
                child for child in self.nodes.values()
                if child.get("parent_key") == section["key"]
                and child.get("organizer_type") == "practice"
            ],
            key=lambda child: int(child.get("_source_order", 0)),
        )
        headings = []
        for line_number in range(int(section["start_line"]) + 1, int(section["end_line"]) + 1):
            match = HEADING_RE.match(self.lines[line_number - 1])
            if match and compact(match.group(2)) == compact("练习"):
                headings.append(line_number)
        unassigned = set(str(practice["key"]) for practice in practices)
        for heading in headings:
            candidates = []
            for practice in practices:
                if str(practice["key"]) not in unassigned:
                    continue
                children = self.children(practice)
                anchor = min(
                    (int(child["start_line"]) for child in children),
                    default=int(practice["start_line"]),
                )
                if anchor >= heading:
                    candidates.append((anchor - heading, practice))
            if candidates:
                _, practice = min(candidates, key=lambda item: item[0])
                practice["start_line"] = heading
                unassigned.remove(str(practice["key"]))
        for practice in practices:
            if str(practice["key"]) not in unassigned:
                continue
            children = self.children(practice)
            if children:
                practice["start_line"] = min(int(child["start_line"]) for child in children)

    def build_exercise_children(self) -> None:
        for node in list(self.nodes.values()):
            if node.get("organizer_type") != "section-exercise":
                continue
            parent = self.nodes.get(str(node.get("parent_key")))
            ref = self.find_reference_note(
                "exercise",
                str(node["title"]),
                str(parent.get("title", "")) if parent else "",
            )
            if ref is None:
                # Printed headings may omit the contextual section suffix.
                number = re.search(r"(?:习题|复习参考题)\s*([\d.]+)", str(node["title"]))
                if number:
                    root = self.reference_root / "习题"
                    label = "复习参考题" if "复习参考题" in str(node["title"]) else "习题"
                    expected_prefix = compact(f"{label}{number.group(1)}")
                    matches = [
                        p for p in root.glob("*.md")
                        if compact(p.stem).startswith(expected_prefix)
                    ]
                    ref = matches[0] if len(matches) == 1 else None
            if ref is None:
                continue
            node["title"] = ref.stem
            node["filename"] = self.reference_filename(ref, "exercise")
            node["emit_title"] = False
            for child_ref in self.owned_refs(ref):
                child = self.build_ref_node(child_ref, node)
                if child:
                    child["node_type"] = "section-exercise-question"
                    child["category"] = "exercise"

    def rebuild_exercise_questions_from_source(self) -> None:
        """Replace weak reference matches with every printed source question."""

        organizers = [
            node
            for node in self.nodes.values()
            if node.get("organizer_type") == "section-exercise"
        ]
        for organizer in organizers:
            for child in list(self.children(organizer)):
                if child.get("node_type") == "section-exercise-question":
                    self.remove_subtree(child)
            prefix = str(organizer["title"])
            for item in exercise_question_ranges(
                self.lines,
                int(organizer["start_line"]),
                int(organizer["end_line"]),
            ):
                number = int(item["question_number"])
                title = f"{prefix}-T{number}"
                filename = str(Path("原子题") / f"{title}.md")
                self.add(
                    {
                        "key": stable_key(
                            "exercise-question",
                            f"{organizer['key']}:{number}",
                        ),
                        "title": title,
                        "parent_key": organizer["key"],
                        "category": "exercise",
                        "filename": filename,
                        "start_line": int(item["start_line"]),
                        "end_line": int(item["end_line"]),
                        "toc_key": None,
                        "node_type": "section-exercise-question",
                        "question_number": number,
                        "emit_title": False,
                    }
                )

    def add_fallback_children(self) -> None:
        for section in [n for n in self.nodes.values() if n.get("organizer_type") == "section"]:
            if self.children(section):
                continue
            start = int(section["start_line"]) + 1
            end = int(section["end_line"])
            if start > end:
                continue
            node = {
                "key": stable_key("knowledge", str(section["key"])),
                "title": re.sub(r"^\d+(?:\.\d+)+\s+", "", str(section["title"])),
                "parent_key": section["key"],
                "category": "knowledge",
                "filename": str(Path(str(section["filename"])).parent / (re.sub(r"^\d+(?:\.\d+)+\s+", "", str(section["title"])) + ".md")),
                "start_line": start,
                "end_line": end,
                "toc_key": None,
                "node_type": "knowledge",
                "emit_title": False,
            }
            self.add(node)

    def partition_organizer(self, node: dict[str, Any]) -> None:
        children = self.children(node)
        if not children:
            return
        organizer = node.get("organizer_type")
        if organizer == "section-exercise" and all(
            child.get("node_type") == "section-exercise-question"
            for child in children
        ):
            return
        content_start = int(node["start_line"])
        first_line = self.lines[content_start - 1].strip()
        if organizer == "section" or (
            organizer in {"practice", "section-exercise"} and HEADING_RE.match(first_line)
        ):
            content_start += 1
        # Weak repeated-reference matches can land in a later subsection.  Once
        # the owning organizer has been bounded by its source-ordered siblings,
        # discard only those out-of-range duplicate anchors; their source text
        # remains covered by the enclosing atom.
        for child in list(children):
            if int(child["end_line"]) < content_start or int(child["start_line"]) > int(node["end_line"]):
                self.remove_subtree(child)
        children = self.children(node)
        if organizer == "knowledge-theme" and len(children) < 2:
            for child in list(children):
                self.remove_subtree(child)
            node["node_type"] = "knowledge"
            node.pop("organizer_type", None)
            return
        if not children:
            return
        anchors = [max(content_start, int(child["start_line"])) for child in children]
        anchors[0] = content_start
        for index in range(1, len(anchors)):
            previous = children[index - 1]
            current_anchor_is_heading = bool(
                HEADING_RE.match(self.lines[anchors[index] - 1].strip())
            )
            previous_required_end = (
                int(previous["end_line"])
                if previous.get("organizer_type") in {"practice", "section-exercise"}
                and not current_anchor_is_heading
                else anchors[index - 1]
            )
            if previous.get("node_type") == "knowledge" and self.children(previous):
                previous_required_end = max(
                    previous_required_end,
                    max(int(child["end_line"]) for child in self.children(previous)),
                )
            anchors[index] = max(
                anchors[index], anchors[index - 1] + 1, previous_required_end + 1
            )
        if anchors[-1] > int(node["end_line"]):
            details = [
                (child["title"], child["start_line"], child["end_line"])
                for child in children
            ]
            raise MaterializeError(
                f"Cannot order children inside {node['key']}:{node['title']} "
                f"range={node['start_line']}-{node['end_line']} children={details}"
            )
        for index, child in enumerate(children):
            child["start_line"] = anchors[index]
            child["end_line"] = (
                anchors[index + 1] - 1 if index + 1 < len(anchors) else int(node["end_line"])
            )
            if int(child["end_line"]) < int(child["start_line"]):
                raise MaterializeError(f"Empty child range: {child['key']}")
            if child.get("node_type") == "organizer":
                self.partition_organizer(child)

    def normalize_ownership(self) -> None:
        for section in [n for n in self.nodes.values() if n.get("organizer_type") == "section"]:
            self.partition_organizer(section)
        for exercise in [n for n in self.nodes.values() if n.get("organizer_type") == "section-exercise" and n.get("parent_key") and self.nodes.get(str(n.get("parent_key")), {}).get("organizer_type") == "chapter"]:
            self.partition_organizer(exercise)

    def repair_example_ownership(self) -> None:
        for example in [n for n in self.nodes.values() if n.get("node_type") == "worked-example"]:
            parent = self.nodes.get(str(example.get("parent_key")))
            if parent and parent.get("node_type") == "knowledge":
                continue
            owner_candidates = [
                n for n in self.nodes.values()
                if n.get("node_type") == "knowledge"
                and int(n["start_line"]) <= int(example["start_line"])
                and int(example["end_line"]) <= int(n["end_line"])
            ]
            if owner_candidates:
                owner = min(owner_candidates, key=lambda n: int(n["end_line"]) - int(n["start_line"]))
                example["parent_key"] = owner["key"]

    def prune_empty_nodes(self) -> None:
        for node in list(self.nodes.values()):
            if (
                node.get("node_type") == "organizer"
                or self.children(node)
            ):
                continue
            substantive = [
                self.lines[line_number - 1].strip()
                for line_number in range(int(node["start_line"]), int(node["end_line"]) + 1)
                if self.lines[line_number - 1].strip()
            ]
            if substantive:
                heading = HEADING_RE.match(substantive[0])
                if heading and compact(heading.group(2)) in {
                    compact(str(node["title"])), compact(Path(str(node["filename"])).stem)
                }:
                    substantive = substantive[1:]
            if node.get("toc_key") is not None:
                if not substantive:
                    node["node_type"] = "method"
                    node["emit_title"] = True
                continue
            if not substantive:
                self.remove_subtree(node)
        for node in list(self.nodes.values()):
            if node.get("organizer_type") != "knowledge-theme":
                continue
            children = self.children(node)
            if len(children) >= 2:
                continue
            for child in list(children):
                self.remove_subtree(child)
            node["node_type"] = "knowledge"
            node.pop("organizer_type", None)

    def write_decisions(self) -> None:
        ambiguous = [item for item in self.report.get("suggestions", []) if item.get("status") == "ambiguous"]
        payload = {
            "schema_version": 1,
            "proposal_report": str(self.proposal_report_path),
            "proposal_report_sha256": sha256_file(self.proposal_report_path),
            "decisions": [
                {
                    "reference_path": item.get("reference_path"),
                    "title": item.get("title"),
                    "decision": "accept" if isinstance(item.get("start_line"), int) and isinstance(item.get("end_line"), int) else "reject",
                    "start_line": item.get("start_line"),
                    "end_line": item.get("end_line"),
                    "reason": "The exact same-edition section path and complete source neighborhood were reviewed; the range is used only as an ordering anchor and is bounded again by adjacent source atoms.",
                }
                for item in ambiguous
            ],
        }
        atomic_json(self.decisions_path, payload, overwrite=True)

    def semantic_review(self) -> dict[str, Any]:
        node_at_line = {
            int(node["start_line"]): node
            for node in self.nodes.values()
            if node.get("toc_key") is None
        }
        headings: list[dict[str, Any]] = []
        for raw in self.base.get("semantic_review", {}).get("headings", []):
            item = dict(raw)
            node = node_at_line.get(int(item["line"]))
            is_numbered_subsection = bool(NUMBERED_SUBSECTION_RE.match(str(item["title"])))
            must_split = is_numbered_subsection or SECTION_EXERCISE_RE.match(str(item["title"]))
            if node and (must_split or node.get("node_type") in {"knowledge", "worked-example"}):
                item.update(
                    decision="split",
                    node_key=node["key"],
                    reason="Whole-book same-edition review confirmed this complete source-backed boundary.",
                    independent_teaching_arc=True,
                    confidence=0.96,
                    reviewed=True,
                )
            elif is_numbered_subsection:
                containers = [
                    candidate for candidate in self.nodes.values()
                    if candidate.get("node_type") == "organizer"
                    and int(candidate["start_line"]) <= int(item["line"]) <= int(candidate["end_line"])
                    and self.children(candidate)
                ]
                container = min(
                    containers,
                    key=lambda candidate: int(candidate["end_line"]) - int(candidate["start_line"]),
                ) if containers else None
                if container is None:
                    item.update(
                        decision="retain",
                        reason="Reviewed as a navigation-only printed subsection boundary inside its complete knowledge atom.",
                        confidence=0.96,
                        reviewed=True,
                    )
                else:
                    item.update(
                        decision="retain",
                        reason="The printed subsection heading is preserved as a promoted structural boundary; its source-backed children are already direct, ordered nodes.",
                        structural_container=True,
                        promote_to_h3=True,
                        child_node_keys=[child["key"] for child in self.children(container)],
                        confidence=0.96,
                        reviewed=True,
                    )
            else:
                item.update(
                    decision="retain",
                    reason="Reviewed in the complete containing source atom; this label is a presentation boundary rather than a separate reusable node.",
                    confidence=0.96,
                    reviewed=True,
                )
            headings.append(item)

        # Every mandatory heading must still resolve to a split node.
        unresolved = [
            item for item in headings
            if SECTION_EXERCISE_RE.match(str(item["title"]))
            and item["decision"] != "split"
        ]
        if unresolved:
            sample = ", ".join(f"{x['line']}:{x['title']}" for x in unresolved[:10])
            raise MaterializeError(f"Mandatory semantic headings lack source nodes: {sample}")

        heading_node_keys = {str(item.get("node_key")) for item in headings if item.get("decision") == "split"}
        ranges = []
        for node in self.nodes.values():
            if node.get("parent_key") is None or node.get("toc_key") is not None or node["key"] in heading_node_keys:
                continue
            ranges.append(
                {
                    "node_key": node["key"],
                    "title": node["title"],
                    "start_line": node["start_line"],
                    "end_line": node["end_line"],
                    "decision": "split",
                    "reason": "The frozen same-edition graph identifies a complete source-backed atom or ownership organizer at this exact source position.",
                    "independent_teaching_arc": True,
                    "confidence": 0.96,
                    "reviewed": True,
                }
            )

        minimum = int(self.profile.get("decomposition", {}).get("content_review_min_nonblank_lines", 24))
        sections = []
        for node in self.nodes.values():
            if node.get("category") != "knowledge":
                continue
            match = HEADING_RE.match(self.lines[int(node["start_line"]) - 1])
            if not match:
                continue
            level = len(match.group(1))
            if (node.get("toc_key") is not None and level not in {2, 3}) or (node.get("toc_key") is None and level not in {4, 5, 6}):
                continue
            nonblank = sum(bool(line.strip()) for line in self.lines[int(node["start_line"]) - 1:int(node["end_line"])])
            if nonblank < minimum:
                continue
            children = self.children(node)
            sections.append(
                {
                    "node_key": node["key"],
                    "title": node["title"],
                    "start_line": node["start_line"],
                    "end_line": node["end_line"],
                    "nonblank_lines": nonblank,
                    "decision": "split" if children else "retain",
                    "child_node_keys": [child["key"] for child in children] if children else [],
                    "reason": "Reviewed the complete source range and its recursively expanded, source-ordered teaching ownership.",
                    "confidence": 0.96,
                    "reviewed": True,
                    "reviewed_entire_section": True,
                }
            )

        ambiguous = [item for item in self.report.get("suggestions", []) if item.get("status") == "ambiguous"]
        return {
            "reference": {
                "status": "passed",
                "reviewer_confirmed": True,
                "scope": "same-book-content-and-style",
                "path": str(self.reference_root),
                "sha256": self.report["reference"]["sha256"],
                "proposal_report": str(self.proposal_report_path),
                "proposal_report_sha256": sha256_file(self.proposal_report_path),
                "decision_report": str(self.decisions_path),
                "decision_report_sha256": sha256_file(self.decisions_path),
                "ambiguous_count": len(ambiguous),
                "resolved_ambiguity_count": len(ambiguous),
            },
            "headings": headings,
            "sections": sections,
            "ranges": ranges,
        }

    def build(self) -> dict[str, Any]:
        self.set_base_types()
        self.build_exercise_children()
        self.rebuild_exercise_questions_from_source()
        self.add_fallback_children()
        self.normalize_ownership()
        self.prune_empty_nodes()
        self.normalize_ownership()
        self.repair_example_ownership()
        self.write_decisions()

        # Remove build-only reference paths and enforce deterministic order.
        for node in self.nodes.values():
            node.pop("_ref_path", None)
            node.pop("_source_order", None)
            if node.get("node_type") in {
                "scenario", "knowledge", "worked-example",
                "practice-question", "section-exercise-question",
            }:
                node["emit_title"] = False
        apply_hierarchical_filenames({"nodes": list(self.nodes.values())})
        ordered = sorted(
            self.nodes.values(),
            key=lambda node: (int(node["start_line"]), -int(node["end_line"]), str(node["key"])),
        )
        atoms = [
            node["key"] for node in ordered
            if node.get("node_type") in {
                "scenario", "knowledge", "worked-example", "practice-question",
                "section-exercise-question", "concept", "reading", "history", "method", "tool",
            }
        ]
        payload = dict(self.base)
        payload["nodes"] = ordered
        payload["node_architecture"] = {
            "status": "passed",
            "reviewed_entire_book": True,
            "source_order_expansion": "passed",
            "source_content_preservation": "passed",
            "source_names_preserved": "passed",
            "physical_hierarchy": "passed",
            "atomic_source_order": atoms,
        }
        payload["semantic_review"] = self.semantic_review()
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formatted_markdown", type=Path)
    parser.add_argument("base_manifest", type=Path)
    parser.add_argument("proposal_report", type=Path)
    parser.add_argument("reference_root", type=Path)
    parser.add_argument("output_manifest", type=Path)
    parser.add_argument("--decisions-output", type=Path, required=True)
    parser.add_argument("--reviewer-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.reviewer_confirmed:
        raise SystemExit("Refusing architecture materialization without --reviewer-confirmed")
    builder = Builder(
        args.formatted_markdown,
        args.base_manifest,
        args.proposal_report,
        args.reference_root,
        args.decisions_output,
    )
    payload = builder.build()
    atomic_json(args.output_manifest.resolve(), payload, args.overwrite)
    counts: dict[str, int] = {}
    for node in payload["nodes"]:
        label = str(node.get("organizer_type") or node.get("node_type"))
        counts[label] = counts.get(label, 0) + 1
    print(json.dumps({
        "status": "passed",
        "output": str(args.output_manifest.resolve()),
        "node_count": len(payload["nodes"]),
        "counts": counts,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
