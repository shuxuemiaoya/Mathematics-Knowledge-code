#!/usr/bin/env python3
"""Materialize frozen atom boundaries and their passed relation graph together."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
import urllib.parse
from collections import defaultdict
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from semantic_atomization import ATOM_CATEGORY_NAMES, verify_artifact
from validate_book_graph import artifact_digest, load_json, sha256_file, validate_organizer_review


CATEGORY_PATHS = {
    "knowledge": "原子层/知识点", "worked-example": "原子层/例题",
    "exercise": "原子层/习题", "scenario": "原子层/情景引入",
    "concept": "原子层/概念", "formula": "原子层/公式",
}
ATOM_CATEGORY_CODES = {
    "knowledge": "K", "worked-example": "W", "exercise": "E", "scenario": "S",
    "concept": "C", "formula": "F",
}
SCENARIO_ROLE_PATHS = {"reflection-question": ("原子层/思考题", "T")}
PRIMARY_CATEGORIES = set(ATOM_CATEGORY_NAMES)
DERIVED_CATEGORIES = {"concept", "formula"}
MARKDOWN_RENDERING = {
    "atom_heading_policy": "omit",
    "atom_filename_policy": "per-folder-sequence-category-code",
    "leaf_organizer_policy": "flat-note",
    "organizer_frontmatter_policy": "required",
    "organizer_self_heading_policy": "omit",
    "organizer_child_heading": "relative-depth",
    "organizer_filename_policy": "clear-title",
    "concept_filename_policy": "preferred-label-collision-safe",
}
MD_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()((?:[^()]|\([^()]*\))*)(\))")
HTML_IMAGE_RE = re.compile(r"(<img\b[^>]*?\bsrc=[\"'])([^\"']+)([\"'])", re.I)
ATOM_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s+.*)?$")
ACTIVITY_TITLE_RE = re.compile(
    r"^(?:观察|思考|尝试|操作|交流|探究|探索|讨论|做一做|议一议)"
    r"(?:[·・、]\s*(?:观察|思考|尝试|操作|交流|探究|探索|讨论))?(?:\s*[：:].*)?$"
)
DEFINITION_FORM_RE = re.compile(r"(?:一般地|定义(?:为)?|称为|叫做|称作|是指|:=|\bis called\b|\bis defined as\b|\bwe call\b|\bmeans\b)", re.I)


class MaterializationError(ValueError):
    pass


def safe_filename(value: str, fallback: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r"[\x00-\x1f<>:\"/\\|?*#]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip(". -")
    return (value or fallback)[:100].rstrip(". -") or fallback


def concept_card_title(value: str) -> str:
    """Reduce editorial labels to the mathematical term being defined."""
    value = str(value).strip()
    reduced = re.sub(r"的(?:定义|概念)(?:[、，,和与].*)?$", "", value).strip()
    return reduced or value or "概念"


def encode_href(value: str) -> str:
    # Obsidian keeps RFC-reserved commas encoded as literal ``%2C`` when it
    # resolves Markdown note embeds.  Filenames retain commas, so leave them
    # literal while still encoding spaces, ``#``, and other path delimiters.
    return urllib.parse.quote(value.replace("\\", "/"), safe="/._-~,")


def markdown_label(value: str) -> str:
    """Escape characters that can terminate an inline Markdown link label."""
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def final_key(atom: dict[str, Any]) -> str:
    identity = f"{atom['owner_key']}:{atom['source_range'][0]}:{atom['source_range'][1]}:{atom['category']}"
    return f"atom-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"


def render_atom_source(lines: list[str], source_range: list[int]) -> str:
    """Render source content without editorial titles.

    Structural Markdown headings are omitted because the atom filename and
    frontmatter already identify the note.  Printed activity markers such as
    ``思考`` and ``观察·思考`` are teaching content, however, so they are
    preserved as plain text instead of disappearing with the heading syntax.
    """
    start, end = source_range
    rendered: list[str] = []
    for line in lines[start - 1 : end]:
        if not ATOM_HEADING_RE.match(line):
            rendered.append(line)
            continue
        title = re.sub(r"^\s{0,3}#{1,6}\s*", "", line).strip()
        if ACTIVITY_TITLE_RE.fullmatch(title):
            rendered.append(title)
    while rendered and not rendered[0].strip():
        rendered.pop(0)
    while rendered and not rendered[-1].strip():
        rendered.pop()
    return "\n".join(rendered) + "\n"


def render_definition_source(lines: list[str], source_range: list[int]) -> str:
    """Render a definition-only excerpt, dropping inline examples and prompts."""
    rendered = render_atom_source(lines, source_range).splitlines()
    cleaned: list[str] = []
    for line in rendered:
        # A textbook sometimes puts the definition and its illustration on the
        # same physical line.  Keep the formal clause and omit the illustration
        # instead of copying the example into a reusable concept card.
        for marker in ("例如", "下面以", "请举例说明"):
            if marker in line:
                line = line.split(marker, 1)[0].rstrip(" ，,：:")
        if line.strip():
            cleaned.append(line)
    return "\n".join(cleaned) + "\n"


def _yaml_string(value: str) -> str:
    """Return a JSON-quoted scalar, which is also valid YAML."""
    return json.dumps(str(value), ensure_ascii=False)


def atom_frontmatter(
    node: dict[str, Any],
    by_key: dict[str, dict[str, Any]],
    root: str,
    profile: dict[str, Any],
    relation_final: dict[str, Any] | None = None,
) -> str:
    """Build compact, useful provenance and study metadata for every atom.

    The body remains an exact source slice.  Metadata is deliberately kept in
    frontmatter so Obsidian properties can be queried without adding headings
    or editorial prose to the atom itself.
    """
    parent_key = str(node.get("derived_from_key") or node.get("parent_key") or "")
    chain: list[str] = []
    seen: set[str] = set()
    cursor = parent_key
    while cursor and cursor in by_key and cursor not in seen:
        seen.add(cursor)
        parent = by_key[cursor]
        if parent.get("layer") == "organizer":
            chain.append(str(parent.get("title", cursor)))
        cursor = str(parent.get("parent_key") or "")
    chain.reverse()
    source_pdf = ""
    source_cfg = profile.get("source")
    if isinstance(source_cfg, dict):
        source_pdf = Path(str(source_cfg.get("path", ""))).name
    category = str(node.get("category", "atom"))
    source_range = list(node.get("source_range", []))
    chars = int(node.get("_source_chars", 0) or 0)
    if not chars:
        # A deterministic estimate is sufficient for the study metadata.  The
        # exact source length is not part of the graph identity.
        chars = max(1, (int(source_range[1]) - int(source_range[0]) + 1) * 45) if len(source_range) == 2 else 45
    minutes = max(2, min(45, round(chars / 90)))
    if category == "knowledge":
        difficulty = "basic" if chars < 500 else ("intermediate" if chars < 1400 else "advanced")
        importance = "core"
        objectives = [f"理解并能复述：{node.get('title', '')}"]
    elif category == "scenario":
        if node.get("scenario_role") == "reflection-question":
            difficulty, importance, objectives = "inquiry", "extension", ["比较、综合已有知识并提出可继续探究的问题"]
        else:
            difficulty, importance, objectives = "introductory", "context", ["说明本节学习动机与问题背景"]
    elif category == "worked-example":
        difficulty, importance, objectives = "intermediate", "illustrative", ["观察完整题意、方法与结论"]
    elif category == "exercise":
        difficulty, importance, objectives = "practice", "practice", ["运用本节知识完成练习"]
    else:
        difficulty, importance, objectives = "reference", "reference", [f"查阅：{node.get('title', '')}"]
    source_sha256 = str(profile.get("source", {}).get("sha256", "")) if isinstance(profile.get("source"), dict) else ""
    lines = ["---", f"title: {_yaml_string(str(node.get('title', '')))}", f"atom_type: {_yaml_string(category)}"]
    lines += [
        f"atom_key: {_yaml_string(str(node.get('key', '')))}",
        f"owner_key: {_yaml_string(str(node.get('parent_key', '')))}",
        f"source: {_yaml_string(source_pdf)}",
        f"source_pdf: {_yaml_string(source_pdf)}",
        f"source_sha256: {_yaml_string(source_sha256)}",
        f"source_range: [{', '.join(str(x) for x in source_range)}]",
    ]
    lines.append("used_by:")
    lines.extend(f"  - {_yaml_string(item)}" for item in chain)
    lines.append("organizers:")
    lines.extend(f"  - {_yaml_string(item)}" for item in chain)
    lines += [
        f"updated_at: {_yaml_string(str(profile.get('updated_at') or date.today().isoformat()))}",
        "review_status: \"passed\"",
        f"estimated_learning_minutes: {minutes}",
        f"difficulty: {_yaml_string(difficulty)}",
        f"importance: {_yaml_string(importance)}",
    ]
    lines.append("learning_objectives:")
    lines.extend(f"  - {_yaml_string(item)}" for item in objectives)
    if category == "knowledge":
        prerequisites: list[str] = []
        if relation_final is not None:
            for relation in relation_final.get("relations", []):
                if isinstance(relation, dict) and relation.get("to_key") == node.get("key") and relation.get("type") in {"prerequisite", "develops", "derives"}:
                    source_node = by_key.get(str(relation.get("from_key")))
                    if source_node and source_node.get("layer") == "atom":
                        prerequisites.append(str(source_node.get("title", "")))
        lines += ["knowledge_granularity: \"complete-teaching-unit\"", "is_definition_card: false", "prerequisites:"]
        lines.extend(f"  - {_yaml_string(item)}" for item in sorted(set(prerequisites)))
        lines += ["keywords:", f"  - {_yaml_string(str(node.get('title', '')))}"]
    elif category == "scenario":
        role = str(node.get("scenario_role", "knowledge-motivation"))
        if role == "knowledge-motivation" and str(node.get("parent_key")) in by_key:
            owner_title = str(by_key[str(node.get("parent_key"))].get("title", ""))
            if owner_title == "本章导引":
                role = "chapter-introduction"
            elif "小节导语" in str(node.get("title", "")):
                role = "section-introduction"
        lines.append(f"scenario_role: {_yaml_string(role)}")
    elif category == "worked-example":
        lines.append("complete_solution: true")
    elif category == "exercise":
        lines.append("exercise_scope: \"top-level-question\"")
    if category in DERIVED_CATEGORIES:
        lines += [f"derived_from: {_yaml_string(str(node.get('derived_from_key', '')))}", f"derived_kind: {_yaml_string(category)}"]
        if category == "concept":
            lines += [f"concept_name: {_yaml_string(str(node.get('title', '')))}", "is_definition_card: true"]
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _organizer_hierarchy(
    node: dict[str, Any],
    by_key: dict[str, dict[str, Any]],
) -> list[str]:
    """Return root-to-self organizer titles for properties and queries."""
    chain = [str(node.get("title", node.get("key", "")))]
    seen = {str(node.get("key", ""))}
    cursor = str(node.get("parent_key") or "")
    while cursor and cursor in by_key and cursor not in seen:
        seen.add(cursor)
        parent = by_key[cursor]
        if parent.get("layer") != "organizer":
            break
        chain.append(str(parent.get("title", cursor)))
        cursor = str(parent.get("parent_key") or "")
    chain.reverse()
    return chain


def _descendant_atom_count(
    node: dict[str, Any],
    by_key: dict[str, dict[str, Any]],
) -> int:
    """Count atoms owned by an organizer subtree."""
    count = 0
    pending = [str(key) for key in node.get("children", [])]
    seen: set[str] = set()
    while pending:
        key = pending.pop()
        if key in seen or key not in by_key:
            continue
        seen.add(key)
        child = by_key[key]
        if child.get("layer") == "atom":
            count += 1
        else:
            pending.extend(str(item) for item in child.get("children", []))
    return count


def organizer_frontmatter(
    node: dict[str, Any],
    by_key: dict[str, dict[str, Any]],
    profile: dict[str, Any],
) -> str:
    """Build queryable Obsidian properties for an organization note."""
    parent_key = str(node.get("parent_key") or "")
    parent = by_key.get(parent_key)
    parent_title = str(parent.get("title", "")) if parent else ""
    parent_file = str(parent.get("filename", "")) if parent else ""
    children = [by_key[str(key)] for key in node.get("children", []) if str(key) in by_key]
    organizer_children = [child for child in children if child.get("layer") == "organizer"]
    atom_children = [child for child in children if child.get("layer") == "atom"]
    if not parent:
        role = "root"
    elif organizer_children and atom_children:
        role = "mixed"
    elif organizer_children:
        role = "branch"
    else:
        role = "leaf"
    source_cfg = profile.get("source", {}) if isinstance(profile.get("source"), dict) else {}
    source_pdf = Path(str(source_cfg.get("path", ""))).name
    heading_ranges = [item for item in node.get("heading_ranges", []) if isinstance(item, list) and len(item) == 2]
    source_anchor = anchor(node, by_key, {})
    lines = [
        "---",
        f"title: {_yaml_string(str(node.get('title', '')))}",
        'node_type: "organizer"',
        f"organizer_key: {_yaml_string(str(node.get('key', '')))}",
        f"parent_organizer_key: {_yaml_string(parent_key) if parent else 'null'}",
        f"parent_organizer: {_yaml_string(parent_title) if parent else 'null'}",
        f"parent_organizer_file: {_yaml_string(parent_file) if parent else 'null'}",
        f"source: {_yaml_string(source_pdf)}",
        f"source_pdf: {_yaml_string(source_pdf)}",
        f"source_sha256: {_yaml_string(str(source_cfg.get('sha256', '')))}",
        f"organizer_level: {int(node.get('organizer_level', 1))}",
        f"organizer_role: {_yaml_string(role)}",
        "hierarchy_path:",
    ]
    lines.extend(f"  - {_yaml_string(item)}" for item in _organizer_hierarchy(node, by_key))
    if heading_ranges:
        lines.append("heading_ranges:")
        lines.extend(f"  - [{int(item[0])}, {int(item[1])}]" for item in heading_ranges)
    else:
        lines.append("heading_ranges: []")
    lines += [
        f"source_anchor: {source_anchor}",
        f"children_count: {len(children)}",
        f"direct_organizer_count: {len(organizer_children)}",
        f"direct_atom_count: {len(atom_children)}",
        f"descendant_atom_count: {_descendant_atom_count(node, by_key)}",
        f"updated_at: {_yaml_string(str(profile.get('updated_at') or date.today().isoformat()))}",
        'review_status: "passed"',
        "---",
    ]
    return "\n".join(lines) + "\n\n"


def _strip_sequence_prefix(value: str) -> str:
    """Remove only generated ordering prefixes (not semantic 1.1 labels)."""
    return re.sub(r"^\d+\s+", "", value)


def normalize_organizer_filenames(nodes: dict[str, dict[str, Any]]) -> None:
    """Use readable organizer names while retaining deterministic collision fallbacks."""
    organizers = {key: node for key, node in nodes.items() if node.get("layer") == "organizer"}
    candidates: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for key, node in organizers.items():
        current = PurePosixPath(str(node["filename"]))
        parts = list(current.parts)
        if not parts:
            continue
        parts[:-1] = [_strip_sequence_prefix(part) for part in parts[:-1]]
        stem = _strip_sequence_prefix(current.stem)
        parts[-1] = f"{stem}{current.suffix}"
        candidate = str(PurePosixPath(*parts))
        candidates[key] = candidate
        collisions.setdefault(candidate, []).append(key)
    for key, node in organizers.items():
        candidate = candidates.get(key)
        if candidate and len(collisions.get(candidate, [])) == 1:
            node["filename"] = candidate


def definition_evidence_range(
    requested: list[int],
    source_lines: list[str] | None,
    atom_range: list[int],
) -> list[int]:
    """Constrain a concept card to a definition-like source span.

    Concept cards are reference definitions, not miniature copies of an entire
    teaching passage.  When a model supplied a broad evidence range, prefer a
    nearby formal-definition sentence and discard examples, activities and
    questions.  The range always remains inside the originating knowledge atom.
    """
    start, end = (int(requested[0]), int(requested[1])) if len(requested) == 2 else (int(atom_range[0]), int(atom_range[1]))
    start = max(start, int(atom_range[0])); end = min(end, int(atom_range[1]))
    if start > end:
        start, end = int(atom_range[0]), int(atom_range[1])
    if not source_lines:
        return [start, end]
    cues = re.compile(r"一般地|定义|称为|叫做|称作|记作|表示.*方法|是指|组成的集合")
    reject = re.compile(r"^\s*(?:例|思考|练习|习题|看下面|[（(]?\d+[）).、])|[？?]\s*$")
    candidates: list[int] = []
    for number in range(start, end + 1):
        line = source_lines[number - 1].strip()
        if not line or ATOM_HEADING_RE.match(line) or reject.search(line):
            continue
        if cues.search(line):
            candidates.append(number)
    if candidates:
        # A sentence containing “一般地” is normally the canonical definition.
        # Keep a short adjacent formula/condition block only when the defining
        # sentence explicitly introduces one.
        preferred = [n for n in candidates if "一般地" in source_lines[n - 1] or "定义" in source_lines[n - 1]]
        named_definition = [n for n in candidates if re.search(r"称为|叫做|称作|是指", source_lines[n - 1])]
        chosen = preferred[0] if preferred else (named_definition[0] if named_definition else candidates[0])
        chosen_line = source_lines[chosen - 1]
        if "一般地" in chosen_line and ("称为" in chosen_line or "叫做" in chosen_line):
            return [chosen, chosen]
        if "一般地" in chosen_line:
            left = chosen
            right = chosen
            for number in range(chosen + 1, min(int(atom_range[1]), chosen + 12) + 1):
                nxt = source_lines[number - 1].strip()
                if ATOM_HEADING_RE.match(nxt) or re.match(r"^\s*(?:例|思考|练习|习题|观察|尝试)", nxt):
                    break
                right = number
                if "称为" in nxt or "叫做" in nxt or "称作" in nxt:
                    break
            return [left, right]
        if re.search(r"称为|叫做|称作|是指", chosen_line):
            return [chosen, chosen]
        # Include immediately adjacent display-math/conditions, stopping at a
        # new activity or example marker.
        left = chosen; right = chosen
        while right < end and right - chosen < 6:
            nxt = source_lines[right].strip()
            if right > chosen and (not nxt or ATOM_HEADING_RE.match(nxt) or reject.search(nxt)):
                break
            right += 1
        return [left, min(right, end)]
    # Fallback: one substantive line, never an activity heading or question.
    for number in range(start, end + 1):
        line = source_lines[number - 1].strip()
        if line and not ATOM_HEADING_RE.match(line) and not reject.search(line):
            return [number, number]
    return [start, end]


def flatten_leaf_organizer_filenames(nodes: dict[str, dict[str, Any]], root: str) -> None:
    """Represent an organizer that owns only atoms as one note in its parent folder."""
    for key, node in nodes.items():
        if key == root or node.get("layer") != "organizer":
            continue
        if any(nodes[str(child)].get("layer") == "organizer" for child in node.get("children", [])):
            continue
        parent = nodes.get(str(node.get("parent_key")))
        if parent is None:
            raise MaterializationError(f"Leaf organizer has no parent: {key}")
        parent_directory = PurePosixPath(str(parent["filename"])).parent
        current = PurePosixPath(str(node["filename"]))
        if current.parent == parent_directory:
            continue
        if current.parent.parent != parent_directory:
            raise MaterializationError(f"Leaf organizer note is not in its direct folder: {key}")
        node["filename"] = str(parent_directory / f"{current.parent.name}.md")


def organizer_heading_depth(node: dict[str, Any], nodes: dict[str, dict[str, Any]], root: str) -> int:
    """Return the child's root-relative Markdown heading depth, capped at H6."""
    root_level = int(nodes[root].get("organizer_level", 1))
    depth = int(node.get("organizer_level", root_level + 1)) - root_level
    if depth < 1:
        raise MaterializationError(f"Organizer depth is not below the root: {node.get('key')}")
    return min(depth, 6)


def anchor(node: dict[str, Any], nodes: dict[str, dict[str, Any]], cache: dict[str, int]) -> int:
    key = str(node["key"])
    if key in cache:
        return cache[key]
    candidates: list[int] = []
    if node.get("layer") == "atom":
        candidates.append(int(node["source_range"][0]))
    else:
        candidates.extend(int(item[0]) for item in node.get("heading_ranges", []))
        candidates.extend(anchor(nodes[str(child)], nodes, cache) for child in node.get("children", []) if str(child) in nodes)
    if not candidates:
        raise MaterializationError(f"Node has no source anchor: {key}")
    cache[key] = min(candidates)
    return cache[key]


def prepare_nodes(base: dict[str, Any], final: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    raw = base.get("nodes")
    if not isinstance(raw, list):
        raise MaterializationError("Base manifest nodes must be an array")
    base_nodes = {str(node["key"]): node for node in raw if isinstance(node, dict) and isinstance(node.get("key"), str)}
    roots = [key for key, node in base_nodes.items() if node.get("layer") == "organizer" and node.get("parent_key") is None]
    if len(roots) != 1:
        raise MaterializationError("Base manifest must contain one root organizer")
    root = roots[0]
    scope = final.get("scope_root_keys")
    if not isinstance(scope, list) or not scope:
        raise MaterializationError("Final atomization has no scope roots")
    included = {root}

    def include(key: str) -> None:
        node = base_nodes.get(key)
        if node is None or node.get("layer") != "organizer":
            raise MaterializationError(f"Unknown scope organizer: {key}")
        included.add(key)
        for child in node.get("children", []):
            if base_nodes.get(str(child), {}).get("layer") == "organizer":
                include(str(child))

    for key in scope:
        include(str(key))
    nodes: dict[str, dict[str, Any]] = {}
    for key in included:
        original = base_nodes[key]
        nodes[key] = {field: original.get(field) for field in ("key", "title", "layer", "parent_key", "organizer_level", "filename", "heading_ranges")}
        nodes[key]["children"] = []
    atoms = final.get("atoms")
    if not isinstance(atoms, list) or not atoms:
        raise MaterializationError("Final atomization has no atoms")
    atoms = sorted(atoms, key=lambda item: (int(item["source_range"][0]), int(item["source_range"][1])))
    folder_sequences: dict[str, int] = defaultdict(int)
    for sequence, atom in enumerate(atoms, start=1):
        if atom.get("category") not in ATOM_CATEGORY_NAMES or str(atom.get("owner_key")) not in nodes:
            raise MaterializationError(f"Invalid category or owner for {atom.get('atom_id')}")
        key = final_key(atom)
        title = str(atom.get("title", "")).strip() or f"Atom {sequence}"
        category_code = ATOM_CATEGORY_CODES[str(atom["category"])]
        category_path = CATEGORY_PATHS[str(atom["category"])]
        scenario_role = atom.get("scenario_role")
        if atom["category"] == "scenario" and scenario_role in SCENARIO_ROLE_PATHS:
            category_path, category_code = SCENARIO_ROLE_PATHS[str(scenario_role)]
        folder_sequences[category_path] += 1
        filename = f"{category_path}/{folder_sequences[category_path]:04d}-{category_code}.md"
        nodes[key] = {"key": key, "title": title, "layer": "atom", "parent_key": str(atom["owner_key"]), "category": atom["category"], "coverage_role": "primary", "filename": filename, "source_range": list(atom["source_range"]), "atomization_id": atom["atom_id"]}
        if scenario_role is not None:
            nodes[key]["scenario_role"] = scenario_role
    # Populate every organizer before resolving descendant-based anchors.
    # Synthesized knowledge-topic organizers can legitimately have no printed
    # heading range, so their anchor depends on children that may otherwise be
    # visited later in an arbitrary set-derived dictionary order.
    for key, node in nodes.items():
        if node.get("layer") != "organizer":
            continue
        organizer_children = (
            [str(child) for child in scope]
            if key == root else
            [str(child) for child in base_nodes[key].get("children", []) if str(child) in included and base_nodes.get(str(child), {}).get("layer") == "organizer"]
        )
        atom_children = [final_key(atom) for atom in atoms if str(atom.get("owner_key")) == key]
        node["children"] = organizer_children + atom_children
        if not node["children"]:
            raise MaterializationError(f"Selected organizer has no children: {key}")
    cache: dict[str, int] = {}
    for key, node in nodes.items():
        if node.get("layer") == "organizer":
            node["children"] = sorted(node["children"], key=lambda child: (anchor(nodes[child], nodes, cache), child))
    flatten_leaf_organizer_filenames(nodes, root)
    normalize_organizer_filenames(nodes)
    return list(nodes.values()), root


def add_derived_nodes(
    nodes: list[dict[str, Any]],
    relation_final: dict[str, Any],
    source_lines: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Create source-faithful concept/formula cards without changing coverage."""
    by_key = {str(node["key"]): node for node in nodes}
    derived: list[dict[str, Any]] = []
    # Derived cards may use a narrower definition-only source slice than the
    # relation artifact's complete grounding evidence.  Deep-copy the sealed
    # payload so card clipping can never mutate the canonical relation data.
    concepts = [copy.deepcopy(item) for item in relation_final.get("concepts", []) if isinstance(item, dict)]
    formulas = [copy.deepcopy(item) for item in relation_final.get("formulas", []) if isinstance(item, dict)]
    bridge_examples = {str(item.get("atom_key")) for item in relation_final.get("atom_roles", []) if isinstance(item, dict) and item.get("role") == "bridge"}
    concept_bases = {
        str(concept.get("key")): safe_filename(concept_card_title(str(concept.get("preferred_label", ""))), "概念")
        for concept in concepts
    }
    concept_collisions: dict[str, list[str]] = {}
    for concept_key, base in concept_bases.items():
        concept_collisions.setdefault(unicodedata.normalize("NFKC", base).casefold(), []).append(concept_key)
    concept_filenames: dict[str, str] = {}
    for concept_key, base in concept_bases.items():
        collision = len(concept_collisions[unicodedata.normalize("NFKC", base).casefold()]) > 1
        suffix = f"--{hashlib.sha256(concept_key.encode()).hexdigest()[:6]}" if collision else ""
        concept_filenames[concept_key] = f"{CATEGORY_PATHS['concept']}/{base}{suffix}.md"
    concept_sequence = 0
    for concept in concepts:
        evidence = sorted(
            (item for item in concept.get("evidence", []) if isinstance(item, dict) and by_key.get(str(item.get("atom_key")), {}).get("category") == "knowledge"),
            key=lambda item: (int(item.get("source_range", [10**12])[0]), str(item.get("atom_key"))),
        )
        if not evidence:
            continue
        source_evidence = evidence[0]
        source_key = str(source_evidence["atom_key"])
        atom_range = list(by_key[source_key]["source_range"])
        source_range = definition_evidence_range(list(source_evidence["source_range"]), source_lines, atom_range)
        definition_text = "\n".join(source_lines[source_range[0] - 1 : source_range[1]]) if source_lines else ""
        if source_lines and not DEFINITION_FORM_RE.search(definition_text):
            # Keep the canonical concept in JSON for relation analysis, but do
            # not create a Markdown concept card without a formal definition.
            continue
        parent_key = str(by_key[source_key]["parent_key"])
        concept_sequence += 1
        key = f"atom-derived-{hashlib.sha256(('concept:' + str(concept['key']) + ':' + str(source_range)).encode()).hexdigest()[:16]}"
        node = {
            "key": key, "title": concept_card_title(str(concept.get("preferred_label", f"Concept {concept_sequence}"))),
            "layer": "atom", "parent_key": parent_key, "category": "concept", "coverage_role": "derived",
            "filename": concept_filenames[str(concept["key"])], "source_range": source_range,
            "derived_from_key": source_key, "concept_key": str(concept["key"]),
        }
        concept["derived_atom_key"] = key
        derived.append(node)
    formula_sequence = 0
    normalized_formulas: list[dict[str, Any]] = []
    for formula in sorted(formulas, key=lambda item: (int(item.get("source_range", [10**12])[0]), str(item.get("key")))):
        source_key = str(formula.get("derived_from_key", ""))
        source_node = by_key.get(source_key)
        if source_node is None or source_node.get("category") not in {"knowledge", "worked-example"}:
            raise MaterializationError(f"Formula has invalid source atom: {formula.get('key')}")
        if source_node.get("category") == "worked-example" and source_key not in bridge_examples:
            raise MaterializationError(f"Formula from an ordinary worked example is forbidden: {formula.get('key')}")
        source_range = list(formula.get("source_range", []))
        if len(source_range) != 2 or int(source_range[0]) < int(source_node["source_range"][0]) or int(source_range[1]) > int(source_node["source_range"][1]):
            raise MaterializationError(f"Formula range is outside its source atom: {formula.get('key')}")
        formula_sequence += 1
        key = f"atom-derived-{hashlib.sha256(('formula:' + str(formula['key']) + ':' + str(source_range)).encode()).hexdigest()[:16]}"
        derived.append({
            "key": key, "title": str(formula.get("title", f"Formula {formula_sequence}")),
            "layer": "atom", "parent_key": str(source_node["parent_key"]), "category": "formula", "coverage_role": "derived",
            "filename": f"{CATEGORY_PATHS['formula']}/{formula_sequence:04d}-F.md", "source_range": source_range,
            "derived_from_key": source_key, "formula_key": str(formula["key"]),
        })
        formula["derived_atom_key"] = key
        normalized_formulas.append(formula)
    derived.sort(key=lambda item: (int(item["source_range"][0]), item["category"], str(item["key"])))
    return [*nodes, *derived], [str(item["key"]) for item in derived], concepts, normalized_formulas


def chapter_for_node(nodes: dict[str, dict[str, Any]], root: str, key: str) -> str:
    cursor = key
    while nodes[cursor].get("parent_key") not in {None, root}:
        cursor = str(nodes[cursor]["parent_key"])
    return cursor


def derived_index_specs(nodes: list[dict[str, Any]], derived_order: list[str], root: str) -> list[dict[str, Any]]:
    by_key = {str(node["key"]): node for node in nodes}
    root_directory = PurePosixPath(str(by_key[root]["filename"])).parent
    grouped: dict[tuple[str, str], list[str]] = {}
    for key in derived_order:
        node = by_key[key]
        chapter = chapter_for_node(by_key, root, str(node["derived_from_key"]))
        grouped.setdefault((chapter, str(node["category"])), []).append(key)
    specs: list[dict[str, Any]] = []
    chapters = [str(key) for key in by_key[root].get("children", []) if by_key.get(str(key), {}).get("layer") == "organizer"]
    for chapter_index, chapter in enumerate(chapters, start=1):
        for category, label in (("concept", "概念索引"), ("formula", "公式索引")):
            keys = grouped.get((chapter, category), [])
            if not keys:
                continue
            specs.append({
                "chapter_key": chapter, "category": category, "title": f"{by_key[chapter]['title']} · {label}",
                "filename": str(root_directory / "派生索引" / f"{chapter_index:02d}-{label}.md"), "derived_keys": keys,
            })
    return specs


def complement_ranges(line_count: int, covered: list[tuple[int, int]]) -> list[dict[str, Any]]:
    marks = [False] * (line_count + 1)
    for start, end in covered:
        for number in range(start, end + 1):
            marks[number] = True
    result: list[dict[str, Any]] = []
    number = 1
    while number <= line_count:
        if marks[number]:
            number += 1
            continue
        start = number
        while number <= line_count and not marks[number]:
            number += 1
        result.append({"start": start, "end": number - 1, "reason": "Outside selected LLM atomization scope or reviewed source exclusion"})
    return result


def resolve_asset(source: Path, raw: str) -> Path | None:
    href = urllib.parse.unquote(raw.strip().strip("<>").split("#", 1)[0])
    parsed = urllib.parse.urlparse(href)
    if parsed.scheme or href.startswith(("/", "\\", "#")):
        return None
    return (source.parent / parsed.path.replace("\\", os.sep)).resolve()


def rewrite_assets(text: str, source: Path, note: Path, temporary: Path, copied: dict[Path, Path], unresolved: list[str]) -> str:
    def target(raw: str) -> str:
        asset = resolve_asset(source, raw)
        if asset is None:
            return raw
        if not asset.is_file():
            unresolved.append(str(asset))
            return raw
        try:
            relative = asset.relative_to(source.parent)
        except ValueError:
            relative = Path(f"external-{hashlib.sha256(str(asset).encode()).hexdigest()[:12]}") / asset.name
        destination = temporary / "资源" / relative
        if asset not in copied:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, destination)
            copied[asset] = destination
        return encode_href(os.path.relpath(destination, note.parent).replace("\\", "/"))

    text = MD_IMAGE_RE.sub(lambda match: f"{match.group(1)}{target(match.group(2))}{match.group(3)}", text)
    return HTML_IMAGE_RE.sub(lambda match: f"{match.group(1)}{target(match.group(2))}{match.group(3)}", text)


def materialize(base_path: Path, final_path: Path, book_root: Path, output_manifest: Path, output_profile: Path | None = None, overwrite: bool = False, relation_final_path: Path | None = None) -> dict[str, Any]:
    base_path, final_path = base_path.expanduser().resolve(), final_path.expanduser().resolve()
    book_root, output_manifest = book_root.expanduser().resolve(), output_manifest.expanduser().resolve()
    output_profile = output_profile.expanduser().resolve() if output_profile else output_manifest.with_name("book-profile.json")
    if book_root.exists() and not overwrite:
        raise FileExistsError(f"Book root exists; pass --overwrite explicitly: {book_root}")
    if any(path.exists() and not overwrite for path in (output_manifest, output_profile)):
        raise FileExistsError("Profile or manifest exists; pass --overwrite explicitly")
    base, final = load_json(base_path), load_json(final_path)
    verify_artifact(final, "atomization-final")
    if final.get("status") != "passed" or final.get("unresolved_count") != 0:
        raise MaterializationError("Atomization is blocked")
    if final.get("base_manifest_sha256") != sha256_file(base_path):
        raise MaterializationError("Final atomization binds a different base manifest")
    new_mode = final.get("atomization", {}).get("mode") == "llm-category-aware-graph"
    if new_mode:
        raw_nodes = base.get("nodes", [])
        node_keys = {
            str(node["key"])
            for node in raw_nodes
            if isinstance(node, dict) and isinstance(node.get("key"), str)
        }
        organizer_errors = validate_organizer_review(
            base,
            base.get("source_markdown_sha256"),
            node_keys,
            required=True,
        )
        if organizer_errors:
            raise MaterializationError(
                "Category-aware materialization requires a passed, digest-bound organizer review: "
                + json.dumps(organizer_errors, ensure_ascii=False)
            )
    relation_final: dict[str, Any] | None = None
    if relation_final_path is not None:
        relation_final_path = relation_final_path.expanduser().resolve()
        relation_final = load_json(relation_final_path)
        verify_artifact(relation_final, "relation-final-v2")
        if relation_final.get("status") != "passed" or relation_final.get("unresolved_count") != 0 or relation_final.get("boundary_feedback"):
            raise MaterializationError("Relations or boundary feedback are not fully resolved")
        if relation_final.get("atomization_final_sha256") != final.get("artifact_sha256"):
            raise MaterializationError("Relation final binds a different atomization-final")
        if relation_final.get("manifest_sha256") != sha256_file(base_path):
            raise MaterializationError("Relation final binds a different base manifest")
    elif new_mode:
        raise MaterializationError("Category-aware graph mode requires --relation-final before materialization")
    source = Path(str(base.get("source_markdown", ""))).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != final.get("source_markdown_sha256"):
        raise MaterializationError("Final atomization source is stale")
    base_profile = load_json(Path(str(base["profile"])).expanduser().resolve())
    rendering_profile = base_profile.get("markdown_rendering")
    self_heading_policy = (
        str(rendering_profile.get("organizer_self_heading_policy", "omit"))
        if isinstance(rendering_profile, dict) else "omit"
    )
    if new_mode:
        # The note filename/frontmatter already names the organizer.  Its body
        # is an index of direct children, so repeating its own title adds no
        # navigation value and makes embedded notes visibly duplicate it.
        self_heading_policy = "omit"
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    output_nodes, root = prepare_nodes(base, final)
    derived_order: list[str] = []
    concepts: list[dict[str, Any]] = []
    formulas: list[dict[str, Any]] = []
    if relation_final is not None:
        output_nodes, derived_order, concepts, formulas = add_derived_nodes(output_nodes, relation_final, lines)
    by_key = {str(node["key"]): node for node in output_nodes}
    index_specs = derived_index_specs(output_nodes, derived_order, root)
    book_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{book_root.name}.materialize-", dir=book_root.parent))
    copied: dict[Path, Path] = {}
    unresolved: list[str] = []
    try:
        for node in output_nodes:
            note = temporary / str(node["filename"])
            note.parent.mkdir(parents=True, exist_ok=True)
            if node["layer"] == "atom":
                source_text = render_definition_source(lines, node["source_range"]) if node.get("category") == "concept" else render_atom_source(lines, node["source_range"])
                # Preserve exact source in the body while exposing provenance
                # and study metadata as Obsidian properties.
                metadata = atom_frontmatter(node, by_key, root, base_profile, relation_final) if (new_mode or relation_final is not None) else ""
                note.write_text(metadata + rewrite_assets(source_text, source, note, temporary, copied, unresolved), encoding="utf-8")
            else:
                links = []
                has_organizer_child = any(
                    by_key.get(str(child), {}).get("layer") == "organizer"
                    for child in node.get("children", [])
                )
                if has_organizer_child and self_heading_policy == "nested-organizer-note":
                    level = min(max(int(node.get("organizer_level", 1)), 1), 6)
                    links.append(f"{'#' * level} {node['title']}")
                for child_key in node["children"]:
                    child = by_key[child_key]
                    relative = os.path.relpath(temporary / child["filename"], note.parent).replace("\\", "/")
                    embed = f"![{markdown_label(str(child['title']))}]({encode_href(relative)})"
                    if child.get("layer") == "organizer":
                        if has_organizer_child and self_heading_policy == "nested-organizer-note":
                            depth = min(max(int(child.get("organizer_level", 1)), 1), 6)
                        else:
                            depth = organizer_heading_depth(child, by_key, root)
                        embed = f"{'#' * depth} {child['title']}\n\n{embed}"
                    links.append(embed)
                note.write_text(
                    organizer_frontmatter(node, by_key, base_profile)
                    + "\n\n".join(links) + "\n",
                    encoding="utf-8",
                )
        for spec in index_specs:
            note = temporary / str(spec["filename"])
            note.parent.mkdir(parents=True, exist_ok=True)
            entries: list[str] = []
            for key in spec["derived_keys"]:
                child = by_key[key]
                relative = os.path.relpath(temporary / str(child["filename"]), note.parent).replace("\\", "/")
                entries.append(f"## {child['title']}\n\n![{markdown_label(str(child['title']))}]({encode_href(relative)})")
            chapter = by_key[str(spec["chapter_key"])]
            index_node = {
                "key": f"derived-index:{spec['chapter_key']}:{spec['category']}",
                "title": str(spec["title"]),
                "layer": "organizer",
                "parent_key": str(spec["chapter_key"]),
                "organizer_level": int(chapter.get("organizer_level", 1)) + 1,
                "filename": str(spec["filename"]),
                "heading_ranges": [],
                "children": list(spec["derived_keys"]),
            }
            note.write_text(
                organizer_frontmatter(index_node, by_key, base_profile)
                + "\n\n".join(entries) + "\n",
                encoding="utf-8",
            )
        if unresolved:
            raise MaterializationError(f"Unresolved assets: {sorted(set(unresolved))[:10]}")
        if book_root.exists():
            shutil.rmtree(book_root)
        os.replace(temporary, book_root)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    base_profile["paths"] = {**base_profile.get("paths", {}), "staging_root": str(output_manifest.parent), "book_root": str(book_root)}
    base_profile["atomization"] = dict(final["atomization"])
    base_profile["atom_categories"] = dict(CATEGORY_PATHS)
    base_profile["atom_subcategory_paths"] = {
        role: path for role, (path, _code) in SCENARIO_ROLE_PATHS.items()
    }
    if relation_final is not None:
        base_profile["relation_analysis"] = dict(relation_final.get("relation_analysis", base_profile.get("relation_analysis", {})))
    if new_mode:
        base_profile["canvas"] = {
            **dict(base_profile.get("canvas", {})),
            "concept_nodes": "hidden", "formula_nodes": "hidden",
            "isolation_policy": "semantic-or-labelled-membership",
        }
    # Preserve the child-heading directory contract while omitting the note's
    # own duplicated heading.
    base_profile["markdown_rendering"] = {
        **MARKDOWN_RENDERING,
        "organizer_self_heading_policy": self_heading_policy,
    }
    output_profile.parent.mkdir(parents=True, exist_ok=True)
    output_profile.write_text(json.dumps(base_profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    covered: list[tuple[int, int]] = []
    for node in output_nodes:
        covered.extend([tuple(node["source_range"])] if node["layer"] == "atom" and node.get("coverage_role", "primary") == "primary" else ([tuple(item) for item in node.get("heading_ranges", [])] if node["layer"] == "organizer" else []))
    source_order = [str(node["key"]) for node in sorted((node for node in output_nodes if node["layer"] == "atom" and node.get("coverage_role", "primary") == "primary"), key=lambda item: (int(item["source_range"][0]), int(item["source_range"][1])))]
    bindings = {name: dict(binding) for name, binding in final.get("bindings", {}).items() if isinstance(binding, dict)}
    atomization_review = {
        "status": "passed", "mode": str(final.get("atomization", {}).get("mode", "llm-two-pass")),
        "final_artifact": {"path": str(final_path), "sha256": final["artifact_sha256"]},
        "bindings": bindings, "reviewer": final.get("reviewer"), "unresolved_count": 0,
    }
    if isinstance(final.get("role_review"), dict):
        atomization_review["role_review"] = dict(final["role_review"])
    manifest = {
        "schema_version": 1, "profile": str(output_profile), "source_sha256": base_profile.get("source", {}).get("sha256"),
        "source_markdown": str(source), "source_markdown_sha256": sha256_file(source),
        "review": {"status": "passed", "reviewed_entire_book": True, "toc_hierarchy": "passed", "source_coverage": "passed", "atom_link_free": "passed", "method": "Category-aware joint atomization and pre-materialization relation closure" if new_mode else ("Two-pass constrained semantic atomization plus teaching-role audit" if final.get("role_review") else "Two-pass constrained semantic atomization")},
        "atomization_review": atomization_review,
        "excluded_ranges": complement_ranges(len(lines), covered), "nodes": output_nodes, "source_order": source_order,
        "derived_order": derived_order, "derived_indexes": index_specs,
        "concepts": concepts, "formulas": formulas,
        "atom_concept_links": [] if relation_final is None else relation_final.get("atom_concept_links", []),
        "concept_relations": [] if relation_final is None else relation_final.get("concept_relations", []),
        "relations": [] if relation_final is None else relation_final.get("relations", []),
    }
    if relation_final is not None:
        featured = sorted(item["atom_key"] for item in relation_final.get("atom_roles", []) if item.get("role") == "bridge")
        manifest["relation_review"] = {
            "status": "passed", "mode": "llm-three-pass", "graph_model": "atom-concept-dual-layer",
            "final_artifact": {"path": str(relation_final_path), "sha256": relation_final["artifact_sha256"]},
            "bindings": relation_final.get("bindings", {}), "reviewer": relation_final.get("reviewer", {}),
            "featured_example_keys": featured, "independent_atoms": relation_final.get("independent_atoms", []),
            "boundary_feedback": [], "unresolved_count": 0,
        }
    if isinstance(base.get("organizer_review"), dict):
        manifest["organizer_review"] = dict(base["organizer_review"])
    output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {"organizers": sum(node["layer"] == "organizer" for node in output_nodes), "atoms": len(source_order), "derived_atoms": len(derived_order), "atom_categories": {category: sum(node.get("category") == category for node in output_nodes) for category in CATEGORY_PATHS}, "assets": len(copied), "derived_indexes": len(index_specs)}
    report = {"schema_version": 1, "status": "passed", "book_root": str(book_root), "manifest": str(output_manifest), "profile": str(output_profile), "source_markdown": str(source), "source_markdown_sha256": sha256_file(source), "atomization_final_sha256": artifact_digest(final), "root_key": root, "counts": counts, "unresolved_assets": []}
    output_manifest.with_name("materialization-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_manifest", type=Path)
    parser.add_argument("atomization_final", type=Path)
    parser.add_argument("--book-root", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-profile", type=Path)
    parser.add_argument("--relation-final", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report, code = materialize(args.base_manifest, args.atomization_final, args.book_root, args.output_manifest, args.output_profile, args.overwrite, args.relation_final), 0
    except Exception as exc:
        report, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
