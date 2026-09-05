#!/usr/bin/env python3
"""Validate a TOC-centered organizer and link-free atom book graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any


ATOM_CATEGORIES = {
    "knowledge": "原子层/知识点",
    "worked-example": "原子层/例题",
    "exercise": "原子层/习题",
    "scenario": "原子层/情景引入",
}
ATOM_COLORS = {
    "knowledge": "2",
    "worked-example": "4",
    "exercise": "6",
    "scenario": "5",
}
ATOM_LABELS = {
    "knowledge": "知识点",
    "worked-example": "例题",
    "exercise": "习题",
    "scenario": "情景引入",
}
ATOM_CATEGORY_CODES = {
    "knowledge": "K",
    "worked-example": "W",
    "exercise": "E",
    "scenario": "S",
}
MARKDOWN_RENDERING_CONTRACT = {
    "atom_heading_policy": "omit",
    "atom_filename_policy": "sequence-category-code",
    "leaf_organizer_policy": "flat-note",
    "organizer_self_heading_policy": "omit",
    "organizer_child_heading": "relative-depth",
}
ORGANIZER_COLOR = "1"
RELATION_LABELS = {
    "prerequisite": "先修", "develops": "发展", "derives": "推导",
    "motivates": "引发", "illustrates": "例证", "applies": "应用",
    "practices": "练习", "contrasts": "对比", "analogous": "类比",
}
RELATION_COLORS = {
    "prerequisite": "1", "develops": "2", "derives": "4",
    "motivates": "5", "illustrates": "4", "applies": "4",
    "practices": "6", "contrasts": "1", "analogous": "5",
}
CONCEPT_RELATION_LABELS = {
    "prerequisite": "先修", "develops": "发展", "derives": "推导",
    "broader": "上位", "part_of": "组成", "contrasts": "对比", "analogous": "类比",
}
CONCEPT_ROLE_LABELS = {
    "introduces": "引入", "explains": "解释", "derives": "推导",
    "triggered_by": "触发", "motivates": "引发", "illustrates": "例证",
    "applies": "应用", "practices": "练习", "assumes": "前置",
}
SYMMETRIC_RELATIONS = {"contrasts", "analogous"}
CONCEPT_KINDS = {"concept", "definition", "property", "theorem", "rule", "procedure", "representation", "method"}
ATOM_CONCEPT_ROLES = {"introduces", "explains", "derives", "triggered_by", "motivates", "illustrates", "applies", "practices", "assumes"}
CONCEPT_RELATION_TYPES = {"prerequisite", "develops", "derives", "broader", "part_of", "contrasts", "analogous"}
BACKBONE_COLOR = "3"
SOURCE_ORDER_COLOR = "#7A7A7A"
LAYERS = {"organizer", "atom"}
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
ANY_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}(?:\s+.*)?$")
ORGANIZER_LINK_RE = re.compile(
    r"^!\[((?:[^\[\]\\]|\\.)+)\]\(((?:[^()]|\([^()]*\))*)\)\s*$"
)
MARKDOWN_LINK_RE = re.compile(
    r"(?<![!\\])\[(?:[^\[\]\n]|\\\[|\\\])*\]\(((?:[^\s()]|\([^\s()]*\))+)\)"
)
MARKDOWN_EMBED_RE = re.compile(
    r"!\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)"
)
WIKILINK_RE = re.compile(r"!?\[\[[^\]]+\]\]")
HTML_ANCHOR_RE = re.compile(r"<a\b[^>]*\bhref\s*=", re.IGNORECASE)


class GraphValidationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(payload: Any) -> str:
    rendered = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def artifact_digest(payload: dict[str, Any]) -> str:
    return canonical_digest(
        {
            key: value
            for key, value in payload.items()
            if key != "artifact_sha256" and not key.startswith("_")
        }
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise GraphValidationError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GraphValidationError(f"JSON root must be an object: {path}")
    return payload


def strip_frontmatter(text: str) -> list[str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return lines
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() in {"---", "..."}:
            return lines[index + 1 :]
    return lines


def normalize_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphValidationError(f"{field} must be a nonempty relative path")
    normalized = value.replace("\\", "/").strip()
    parts = normalized.split("/")
    if normalized.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise GraphValidationError(f"{field} contains an unsafe path: {value}")
    if not normalized.casefold().endswith(".md"):
        raise GraphValidationError(f"{field} must end in .md: {value}")
    return normalized


def parse_range(value: Any, field: str, line_count: int) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
    ):
        raise GraphValidationError(f"{field} must be [start, end]")
    start, end = value
    if start < 1 or end < start or end > line_count:
        raise GraphValidationError(f"{field} is outside source Markdown")
    return start, end


def resolve_link(href: str, source_note: Path, book_root: Path) -> Path:
    raw = urllib.parse.unquote(href.strip().strip("<>").split("#", 1)[0])
    if raw.startswith(("/", "\\")):
        target = book_root / raw.lstrip("/\\")
    else:
        target = source_note.parent / raw.replace("/", os.sep)
    return target.resolve()


def is_markdown_note_embed(href: str) -> bool:
    raw = urllib.parse.unquote(href.strip().strip("<>").split("#", 1)[0])
    return Path(raw).suffix.casefold() in {"", ".md"}


def stable_canvas_id(kind: str, key: str) -> str:
    return hashlib.sha256(f"{kind}:{key}".encode("utf-8")).hexdigest()[:16]


def graph_descendants(nodes: dict[str, dict[str, Any]], root_key: str) -> list[str]:
    ordered: list[str] = []

    def visit(key: str) -> None:
        ordered.append(key)
        node = nodes[key]
        if node.get("layer") == "organizer":
            for child in node.get("_children", node.get("children", [])):
                if str(child) in nodes:
                    visit(str(child))

    visit(root_key)
    return ordered


def resolve_canvas_index_path(value: Any, index_root: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise GraphValidationError("Canvas index path must be a nonempty string")
    candidate = Path(value.replace("\\", "/"))
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise GraphValidationError(f"Unsafe Canvas index path: {value}")
    if candidate.suffix.casefold() != ".canvas":
        raise GraphValidationError(f"Canvas index path must end in .canvas: {value}")
    resolved = (index_root / candidate).resolve()
    try:
        resolved.relative_to(index_root)
    except ValueError as exc:
        raise GraphValidationError(f"Canvas path escapes index directory: {value}") from exc
    return resolved


def read_canvas_document(
    canvas_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Path], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    try:
        canvas = load_json(canvas_path)
    except Exception as exc:
        return [], [], {}, [{"code": "canvas-invalid", "path": str(canvas_path), "detail": str(exc)}]
    nodes = canvas.get("nodes")
    edges = canvas.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return [], [], {}, [{"code": "canvas-invalid", "path": str(canvas_path), "detail": "nodes and edges must be arrays"}]
    typed_nodes = [node for node in nodes if isinstance(node, dict)]
    typed_edges = [edge for edge in edges if isinstance(edge, dict)]
    if len(typed_nodes) != len(nodes):
        errors.append({"code": "canvas-node-invalid", "path": str(canvas_path)})
    if len(typed_edges) != len(edges):
        errors.append({"code": "canvas-edge-invalid", "path": str(canvas_path)})
    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(ids) != len(typed_nodes) or len(ids) != len(set(ids)) or not all(isinstance(item, str) and item for item in ids):
        errors.append({"code": "canvas-node-id-invalid", "path": str(canvas_path)})
    endpoint_ids = set(ids)
    link_targets: dict[str, Path] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for field in ("x", "y", "width", "height"):
            value = node.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append({"code": "canvas-node-geometry-invalid", "path": str(canvas_path), "node": node.get("id"), "field": field})
        if isinstance(node.get("width"), (int, float)) and node["width"] <= 0:
            errors.append({"code": "canvas-node-size-invalid", "path": str(canvas_path), "node": node.get("id")})
        if isinstance(node.get("height"), (int, float)) and node["height"] <= 0:
            errors.append({"code": "canvas-node-size-invalid", "path": str(canvas_path), "node": node.get("id")})
        if node.get("type") == "text":
            text = node.get("text")
            if not isinstance(text, str) or WIKILINK_RE.search(text):
                errors.append({"code": "canvas-card-link-invalid", "path": str(canvas_path), "node": node.get("id")})
                continue
            links = MARKDOWN_LINK_RE.findall(text)
            if len(links) > 1:
                errors.append({"code": "canvas-card-link-invalid", "path": str(canvas_path), "node": node.get("id")})
                continue
            if links:
                raw = urllib.parse.unquote(links[0].strip().strip("<>").split("#", 1)[0])
                target = (canvas_path.parent / raw.replace("/", os.sep)).resolve()
                link_targets[str(node.get("id"))] = target
                if not target.is_file():
                    errors.append({"code": "canvas-card-target-missing", "path": str(canvas_path), "node": node.get("id"), "target": str(target)})
        elif node.get("type") != "group":
            errors.append({"code": "canvas-node-type-invalid", "path": str(canvas_path), "node": node.get("id")})
    edge_ids = [edge.get("id") for edge in typed_edges]
    if len(edge_ids) != len(set(edge_ids)) or not all(isinstance(item, str) and item for item in edge_ids):
        errors.append({"code": "canvas-edge-id-invalid", "path": str(canvas_path)})
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("fromNode") not in endpoint_ids or edge.get("toNode") not in endpoint_ids:
            errors.append({"code": "canvas-edge-endpoint-invalid", "path": str(canvas_path)})
    return typed_nodes, typed_edges, link_targets, errors


def canvas_counts(
    canvas_nodes: list[dict[str, Any]],
    canvas_edges: list[dict[str, Any]],
    expected_keys: set[str],
    nodes: dict[str, dict[str, Any]],
    ownership_edges: int,
    relation_edges: int,
) -> dict[str, int]:
    return {
        "cards": sum(node.get("type") == "text" for node in canvas_nodes),
        "groups": sum(node.get("type") == "group" for node in canvas_nodes),
        "edges": len(canvas_edges),
        "ownership_edges": ownership_edges,
        "relation_edges": relation_edges,
        "organizers": sum(nodes[key].get("layer") == "organizer" for key in expected_keys),
        "atoms": sum(nodes[key].get("layer") == "atom" for key in expected_keys),
    }


def validate_index_counts(
    entry: dict[str, Any], actual: dict[str, int], path: Path
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    declared = entry.get("counts")
    if not isinstance(declared, dict):
        return [{"code": "canvas-index-counts-missing", "path": str(path)}]
    for field, expected in actual.items():
        if declared.get(field) != expected:
            errors.append(
                {
                    "code": "canvas-index-count-mismatch",
                    "path": str(path),
                    "field": field,
                    "expected": expected,
                    "actual": declared.get(field),
                }
            )
    return errors


def validate_tree_canvas(
    canvas_path: Path,
    entry: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    expected_order: list[str],
    group_roots: list[str],
    group_scope: str,
    expected_targets: dict[str, Path],
) -> list[dict[str, Any]]:
    canvas_nodes, canvas_edges, targets, errors = read_canvas_document(canvas_path)
    cards = {str(node.get("id")): node for node in canvas_nodes if node.get("type") == "text"}
    groups = {str(node.get("id")): node for node in canvas_nodes if node.get("type") == "group"}
    expected_keys = set(expected_order)
    expected_card_ids = {stable_canvas_id("card", key): key for key in expected_keys}
    if set(cards) != set(expected_card_ids):
        errors.append(
            {
                "code": "canvas-card-set-mismatch",
                "path": str(canvas_path),
                "missing": sorted(set(expected_card_ids) - set(cards)),
                "extra": sorted(set(cards) - set(expected_card_ids)),
            }
        )
    expected_group_ids = {
        stable_canvas_id("group", f"{group_scope}:{key}"): key for key in group_roots
    }
    if set(groups) != set(expected_group_ids):
        errors.append(
            {
                "code": "canvas-group-set-mismatch",
                "path": str(canvas_path),
                "missing": sorted(set(expected_group_ids) - set(groups)),
                "extra": sorted(set(groups) - set(expected_group_ids)),
            }
        )

    expected_edges: dict[str, tuple[str, str]] = {}
    for parent in expected_order:
        if nodes[parent].get("layer") != "organizer":
            continue
        for child in nodes[parent].get("_children", nodes[parent].get("children", [])):
            child_key = str(child)
            if child_key in expected_keys:
                expected_edges[stable_canvas_id("edge", f"ownership:{parent}:{child_key}")] = (
                    stable_canvas_id("card", parent),
                    stable_canvas_id("card", child_key),
                )
    actual_edges = {str(edge.get("id")): edge for edge in canvas_edges}
    if set(actual_edges) != set(expected_edges):
        errors.append(
            {
                "code": "canvas-ownership-edge-set-mismatch",
                "path": str(canvas_path),
                "missing": sorted(set(expected_edges) - set(actual_edges)),
                "extra": sorted(set(actual_edges) - set(expected_edges)),
            }
        )
    for edge_id, (from_id, to_id) in expected_edges.items():
        edge = actual_edges.get(edge_id)
        if edge is not None and (
            edge.get("fromNode") != from_id
            or edge.get("toNode") != to_id
            or edge.get("label") is not None
            or edge.get("color") is not None
        ):
            errors.append({"code": "canvas-ownership-edge-invalid", "path": str(canvas_path), "edge": edge_id})

    for key in expected_keys:
        card_id = stable_canvas_id("card", key)
        card = cards.get(card_id)
        if card is None:
            continue
        expected_target = expected_targets[key].resolve()
        if targets.get(card_id) != expected_target:
            errors.append(
                {
                    "code": "canvas-card-target-invalid",
                    "path": str(canvas_path),
                    "node": key,
                    "expected": str(expected_target),
                    "actual": str(targets.get(card_id)),
                }
            )
        node = nodes[key]
        expected_color = ORGANIZER_COLOR
        if node.get("layer") == "atom":
            category = str(node.get("category"))
            expected_color = ATOM_COLORS.get(category)
            text = card.get("text")
            if not isinstance(text, str) or f"{ATOM_LABELS.get(category)} · " not in text:
                errors.append({"code": "canvas-atom-label-invalid", "path": str(canvas_path), "node": key})
        if card.get("color") != expected_color:
            errors.append({"code": "canvas-card-color-invalid", "path": str(canvas_path), "node": key})

    for parent in expected_order:
        parent_id = stable_canvas_id("card", parent)
        parent_card = cards.get(parent_id)
        if parent_card is None or nodes[parent].get("layer") != "organizer":
            continue
        child_keys = [
            str(child)
            for child in nodes[parent].get("_children", nodes[parent].get("children", []))
            if str(child) in expected_keys and stable_canvas_id("card", str(child)) in cards
        ]
        child_cards = [cards[stable_canvas_id("card", key)] for key in child_keys]
        if any(card.get("x", 0) <= parent_card.get("x", 0) for card in child_cards):
            errors.append({"code": "canvas-hierarchy-direction-invalid", "path": str(canvas_path), "node": parent})
        child_y = [card.get("y") for card in child_cards]
        if any(not isinstance(value, (int, float)) for value in child_y) or any(
            child_y[index] >= child_y[index + 1] for index in range(len(child_y) - 1)
        ):
            errors.append({"code": "canvas-sibling-order-invalid", "path": str(canvas_path), "node": parent})

    for group_id, root_key in expected_group_ids.items():
        group = groups.get(group_id)
        if group is None:
            continue
        if group.get("label") != nodes[root_key].get("title"):
            errors.append({"code": "canvas-group-label-invalid", "path": str(canvas_path), "group": group_id})
        member_keys = [key for key in graph_descendants(nodes, root_key) if key in expected_keys]
        for key in member_keys:
            card = cards.get(stable_canvas_id("card", key))
            if card is None:
                continue
            contained = (
                group.get("x", 0) <= card.get("x", 0)
                and group.get("y", 0) <= card.get("y", 0)
                and group.get("x", 0) + group.get("width", 0) >= card.get("x", 0) + card.get("width", 0)
                and group.get("y", 0) + group.get("height", 0) >= card.get("y", 0) + card.get("height", 0)
            )
            if not contained:
                errors.append({"code": "canvas-group-containment-invalid", "path": str(canvas_path), "group": group_id, "node": key})

    actual_counts = canvas_counts(
        canvas_nodes,
        canvas_edges,
        expected_keys,
        nodes,
        ownership_edges=len(expected_edges),
        relation_edges=0,
    )
    errors.extend(validate_index_counts(entry, actual_counts, canvas_path))
    return errors


def validate_semantic_canvas(
    canvas_path: Path,
    entry: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    relations: list[dict[str, Any]],
    book_root: Path,
) -> list[dict[str, Any]]:
    canvas_nodes, canvas_edges, targets, errors = read_canvas_document(canvas_path)
    participants = {
        str(relation[field])
        for relation in relations
        for field in ("from_key", "to_key")
        if relation.get(field) in nodes
    }
    cards = {str(node.get("id")): node for node in canvas_nodes if node.get("type") == "text"}
    groups = [node for node in canvas_nodes if node.get("type") == "group"]
    expected_card_ids = {stable_canvas_id("card", key): key for key in participants}
    if set(cards) != set(expected_card_ids):
        errors.append({"code": "semantic-card-set-mismatch", "path": str(canvas_path)})
    if groups:
        errors.append({"code": "semantic-groups-forbidden", "path": str(canvas_path)})
    for card_id, key in expected_card_ids.items():
        if targets.get(card_id) != (book_root / str(nodes[key]["_filename"])).resolve():
            errors.append({"code": "semantic-card-target-invalid", "path": str(canvas_path), "node": key})
        card = cards.get(card_id)
        if card is not None:
            expected_color = ORGANIZER_COLOR if nodes[key].get("layer") == "organizer" else ATOM_COLORS.get(str(nodes[key].get("category")))
            if card.get("color") != expected_color:
                errors.append({"code": "semantic-card-color-invalid", "path": str(canvas_path), "node": key})
    expected_edges = {
        stable_canvas_id("edge", f"relation:{relation['key']}"): relation
        for relation in relations
        if isinstance(relation.get("key"), str)
    }
    actual_edges = {str(edge.get("id")): edge for edge in canvas_edges}
    if set(actual_edges) != set(expected_edges):
        errors.append({"code": "semantic-edge-set-mismatch", "path": str(canvas_path)})
    for edge_id, relation in expected_edges.items():
        edge = actual_edges.get(edge_id)
        if edge is None:
            continue
        expected_label = relation.get("label")
        if isinstance(expected_label, str):
            expected_label = expected_label.strip() or None
        expected_color = relation.get("color") if relation.get("color") in {"1", "2", "3", "4", "5", "6"} else None
        if (
            edge.get("fromNode") != stable_canvas_id("card", str(relation["from_key"]))
            or edge.get("toNode") != stable_canvas_id("card", str(relation["to_key"]))
            or edge.get("label") != expected_label
            or edge.get("color") != expected_color
        ):
            errors.append({"code": "semantic-edge-invalid", "path": str(canvas_path), "edge": edge_id})
    actual_counts = canvas_counts(
        canvas_nodes,
        canvas_edges,
        participants,
        nodes,
        ownership_edges=0,
        relation_edges=len(relations),
    )
    errors.extend(validate_index_counts(entry, actual_counts, canvas_path))
    return errors


def validate_canvas_bundle(
    canvas_index_path: Path,
    manifest_path: Path,
    book_root: Path,
    nodes: dict[str, dict[str, Any]],
    organizers: list[dict[str, Any]],
    atoms: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    canvas_index_path = canvas_index_path.expanduser().resolve()
    try:
        index = load_json(canvas_index_path)
    except Exception as exc:
        return [{"code": "canvas-index-invalid", "detail": str(exc)}]
    index_root = canvas_index_path.parent
    if index.get("schema_version") != 1:
        errors.append({"code": "canvas-index-schema-version"})
    if Path(str(index.get("manifest", ""))).expanduser().resolve() != manifest_path:
        errors.append({"code": "canvas-index-manifest-mismatch"})
    if index.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append({"code": "canvas-index-manifest-digest-mismatch"})
    if Path(str(index.get("book_root", ""))).expanduser().resolve() != book_root:
        errors.append({"code": "canvas-index-book-root-mismatch"})
    if index.get("layout") != {
        "hierarchy_direction": "left-to-right",
        "sibling_order": "source-top-to-bottom",
        "atom_grouping": "none",
    }:
        errors.append({"code": "canvas-index-layout-invalid"})

    roots = [node for node in organizers if node.get("parent_key") is None]
    if len(roots) != 1:
        return [*errors, {"code": "canvas-index-root-unavailable"}]
    root_key = str(roots[0]["key"])
    root_children = [str(key) for key in nodes[root_key].get("_children", [])]
    chapter_keys = [key for key in root_children if nodes.get(key, {}).get("layer") == "organizer"]
    root_atoms = [key for key in root_children if nodes.get(key, {}).get("layer") == "atom"]
    if root_atoms:
        errors.append({"code": "canvas-root-atoms-forbidden", "nodes": root_atoms})

    overview_entry = index.get("overview")
    chapter_entries = index.get("chapters")
    if not isinstance(overview_entry, dict):
        errors.append({"code": "canvas-overview-entry-invalid"})
        overview_entry = {}
    elif (
        overview_entry.get("role") != "overview"
        or overview_entry.get("root_key") != root_key
        or overview_entry.get("path") != "overview.canvas"
    ):
        errors.append({"code": "canvas-overview-entry-invalid"})
    if not isinstance(chapter_entries, list) or not all(isinstance(item, dict) for item in chapter_entries):
        errors.append({"code": "canvas-chapter-entries-invalid"})
        chapter_entries = []
    entry_keys = [str(item.get("root_key")) for item in chapter_entries]
    if entry_keys != chapter_keys or len(entry_keys) != len(set(entry_keys)):
        errors.append({"code": "canvas-chapter-order-or-coverage", "expected": chapter_keys, "actual": entry_keys})

    chapter_paths: dict[str, Path] = {}
    for entry in chapter_entries:
        if entry.get("role") != "chapter" or not str(entry.get("path", "")).startswith("chapters/"):
            errors.append({"code": "canvas-chapter-entry-invalid", "root_key": entry.get("root_key")})
        try:
            path = resolve_canvas_index_path(entry.get("path"), index_root)
            chapter_paths[str(entry.get("root_key"))] = path
        except Exception as exc:
            errors.append({"code": "canvas-chapter-path-invalid", "detail": str(exc)})

    organizer_keys = {str(node["key"]) for node in organizers}
    if overview_entry:
        try:
            overview_path = resolve_canvas_index_path(overview_entry.get("path"), index_root)
            expected_targets = {
                key: chapter_paths[key]
                if key in chapter_paths
                else (book_root / str(nodes[key]["_filename"])).resolve()
                for key in organizer_keys
            }
            errors.extend(
                validate_tree_canvas(
                    overview_path,
                    overview_entry,
                    nodes,
                    [key for key in graph_descendants(nodes, root_key) if key in organizer_keys],
                    chapter_keys,
                    "overview",
                    expected_targets,
                )
            )
        except Exception as exc:
            errors.append({"code": "canvas-overview-path-invalid", "detail": str(exc)})

    atom_occurrences = {str(node["key"]): 0 for node in atoms}
    for entry in chapter_entries:
        chapter_key = str(entry.get("root_key"))
        chapter_path = chapter_paths.get(chapter_key)
        if chapter_path is None or chapter_key not in nodes:
            continue
        expected_order = graph_descendants(nodes, chapter_key)
        for key in expected_order:
            if key in atom_occurrences:
                atom_occurrences[key] += 1
        group_roots = [
            str(child)
            for child in nodes[chapter_key].get("_children", [])
            if nodes.get(str(child), {}).get("layer") == "organizer"
        ]
        expected_targets = {
            key: (book_root / str(nodes[key]["_filename"])).resolve()
            for key in expected_order
        }
        errors.extend(
            validate_tree_canvas(
                chapter_path,
                entry,
                nodes,
                expected_order,
                group_roots,
                chapter_key,
                expected_targets,
            )
        )
    invalid_occurrences = {key: count for key, count in atom_occurrences.items() if count != 1}
    if invalid_occurrences:
        errors.append({"code": "canvas-atom-chapter-coverage", "actual": invalid_occurrences})

    semantic_entry = index.get("semantics")
    if relations:
        if not isinstance(semantic_entry, dict):
            errors.append({"code": "semantic-canvas-entry-missing"})
        else:
            if semantic_entry.get("role") != "semantics" or semantic_entry.get("path") != "semantics.canvas":
                errors.append({"code": "semantic-canvas-entry-invalid"})
            try:
                semantic_path = resolve_canvas_index_path(semantic_entry.get("path"), index_root)
                errors.extend(
                    validate_semantic_canvas(
                        semantic_path, semantic_entry, nodes, relations, book_root
                    )
                )
            except Exception as exc:
                errors.append({"code": "semantic-canvas-path-invalid", "detail": str(exc)})
    elif semantic_entry is not None:
        errors.append({"code": "semantic-canvas-unexpected"})
    return errors


def canvas_bounds(nodes: list[dict[str, Any]]) -> dict[str, int | float]:
    if not nodes:
        return {"x": 0, "y": 0, "width": 0, "height": 0, "aspect_ratio": 1.0}
    min_x = min(int(node["x"]) for node in nodes)
    min_y = min(int(node["y"]) for node in nodes)
    max_x = max(int(node["x"]) + int(node["width"]) for node in nodes)
    max_y = max(int(node["y"]) + int(node["height"]) for node in nodes)
    width, height = max_x - min_x, max_y - min_y
    return {"x": min_x, "y": min_y, "width": width, "height": height, "aspect_ratio": round(width / height, 4) if height else 1.0}


def text_overlap_errors(canvas_nodes: list[dict[str, Any]], canvas_path: Path) -> list[dict[str, Any]]:
    cards = [node for node in canvas_nodes if node.get("type") == "text"]
    errors: list[dict[str, Any]] = []
    for index, left in enumerate(cards):
        left_box = (left["x"], left["y"], left["x"] + left["width"], left["y"] + left["height"])
        for right in cards[index + 1 :]:
            right_box = (right["x"], right["y"], right["x"] + right["width"], right["y"] + right["height"])
            if not (left_box[2] <= right_box[0] or right_box[2] <= left_box[0] or left_box[3] <= right_box[1] or right_box[3] <= left_box[1]):
                errors.append({"code": "canvas-card-overlap", "path": str(canvas_path), "left": left.get("id"), "right": right.get("id")})
    return errors


def validator_chapter_for(nodes: dict[str, dict[str, Any]], root_key: str, key: str) -> str:
    cursor = key
    parent = nodes[cursor].get("parent_key")
    while parent is not None and str(parent) != root_key:
        cursor = str(parent)
        parent = nodes[cursor].get("parent_key")
    return cursor


def validator_section_for(nodes: dict[str, dict[str, Any]], chapter_key: str, key: str) -> str:
    if key == chapter_key:
        return "__chapter_intro__"
    cursor = key
    parent = nodes[cursor].get("parent_key")
    if parent is not None and str(parent) == chapter_key and nodes[cursor].get("layer") == "atom":
        return "__chapter_intro__"
    while parent is not None and str(parent) != chapter_key:
        cursor = str(parent)
        parent = nodes[cursor].get("parent_key")
    return cursor if parent is not None else "__chapter_intro__"


def validator_visible_atom(nodes: dict[str, dict[str, Any]], key: str, featured_examples: set[str]) -> bool:
    return nodes[key].get("category") in {"knowledge", "scenario"} or key in featured_examples


def validator_descendant_atoms(nodes: dict[str, dict[str, Any]], organizer_key: str) -> list[str]:
    return [key for key in graph_descendants(nodes, organizer_key)[1:] if nodes[key].get("layer") == "atom"]


def validator_exercise_owners(
    nodes: dict[str, dict[str, Any]], chapter_key: str, exercise_atoms: list[str]
) -> tuple[dict[str, str], dict[str, list[str]]]:
    categories: dict[str, set[str]] = {}

    def organizer_categories(key: str) -> set[str]:
        if key not in categories:
            categories[key] = {str(nodes[atom].get("category")) for atom in validator_descendant_atoms(nodes, key)}
        return categories[key]

    owner_by_atom: dict[str, str] = {}
    atoms_by_owner: dict[str, list[str]] = defaultdict(list)
    for atom_key in exercise_atoms:
        cursor = str(nodes[atom_key]["parent_key"])
        owner = cursor
        while cursor != chapter_key and organizer_categories(cursor) == {"exercise"}:
            owner = cursor
            parent = nodes[cursor].get("parent_key")
            if parent is None or str(parent) == chapter_key:
                break
            cursor = str(parent)
        owner_by_atom[atom_key] = owner
        atoms_by_owner[owner].append(atom_key)
    return owner_by_atom, dict(atoms_by_owner)


def relation_sides(relation_type: str) -> tuple[str, str]:
    if relation_type == "motivates":
        return "right", "top"
    if relation_type in {"illustrates", "applies", "practices", "contrasts", "analogous"}:
        return "bottom", "top"
    return "right", "left"


def validate_constellation_counts(entry: dict[str, Any], canvas_nodes: list[dict[str, Any]], canvas_edges: list[dict[str, Any]], expected: dict[str, int], canvas_path: Path) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    actual = {
        **expected,
        "cards": sum(node.get("type") == "text" for node in canvas_nodes),
        "groups": sum(node.get("type") == "group" for node in canvas_nodes),
        "edges": len(canvas_edges),
    }
    errors.extend(validate_index_counts(entry, actual, canvas_path))
    declared_bounds = entry.get("bounds")
    actual_bounds = canvas_bounds(canvas_nodes)
    if declared_bounds != actual_bounds:
        errors.append({"code": "canvas-index-bounds-mismatch", "path": str(canvas_path), "expected": actual_bounds, "actual": declared_bounds})
    if actual["cards"] >= 30 and not 0.5 <= float(actual_bounds["aspect_ratio"]) <= 2.0:
        errors.append({"code": "canvas-aspect-ratio-invalid", "path": str(canvas_path), "aspect_ratio": actual_bounds["aspect_ratio"]})
    errors.extend(text_overlap_errors(canvas_nodes, canvas_path))
    return errors


def validate_atlas_canvas(
    canvas_path: Path,
    entry: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    root_key: str,
    chapter_keys: list[str],
    chapter_paths: dict[str, Path],
    book_root: Path,
    relations: list[dict[str, Any]],
    atom_chapter: dict[str, str],
    semantic_ready: bool,
    featured_examples: set[str],
) -> list[dict[str, Any]]:
    canvas_nodes, canvas_edges, targets, errors = read_canvas_document(canvas_path)
    cards = {str(node.get("id")): node for node in canvas_nodes if node.get("type") == "text"}
    groups = [node for node in canvas_nodes if node.get("type") == "group"]
    expected_cards = {stable_canvas_id("atlas", root_key), stable_canvas_id("utility", "atlas-legend"), *(stable_canvas_id("chapter", key) for key in chapter_keys)}
    if set(cards) != expected_cards:
        errors.append({"code": "canvas-atlas-card-set-mismatch", "path": str(canvas_path), "missing": sorted(expected_cards-set(cards)), "extra": sorted(set(cards)-expected_cards)})
    if groups:
        errors.append({"code": "canvas-atlas-groups-forbidden", "path": str(canvas_path)})
    for key in chapter_keys:
        card_id = stable_canvas_id("chapter", key)
        expected_target = chapter_paths[key] if semantic_ready else (book_root / str(nodes[key]["_filename"])).resolve()
        if targets.get(card_id) != expected_target.resolve():
            errors.append({"code": "canvas-atlas-chapter-target-invalid", "chapter": key})
        text = cards.get(card_id, {}).get("text", "")
        if semantic_ready and "关系待复核" in text:
            errors.append({"code": "canvas-atlas-ready-label-invalid", "chapter": key})
        if not semantic_ready and "关系待复核" not in text:
            errors.append({"code": "canvas-atlas-pending-label-missing", "chapter": key})
    expected_edges: dict[str, dict[str, Any]] = {}
    for left, right in zip(chapter_keys, chapter_keys[1:]):
        edge_id = stable_canvas_id("edge", f"atlas:source-order:{left}:{right}")
        expected_edges[edge_id] = {"fromNode": stable_canvas_id("chapter", left), "toNode": stable_canvas_id("chapter", right), "fromSide": "right", "toSide": "left", "label": "书序", "color": SOURCE_ORDER_COLOR, "toEnd": "arrow"}
    aggregation: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for relation in relations if semantic_ready else []:
        if not validator_visible_atom(nodes, str(relation["from_key"]), featured_examples) or not validator_visible_atom(nodes, str(relation["to_key"]), featured_examples):
            continue
        left, right = atom_chapter[str(relation["from_key"])], atom_chapter[str(relation["to_key"])]
        if left != right:
            aggregation.setdefault((left, right, str(relation["tier"])), []).append(relation)
    for (left, right, tier), items in aggregation.items():
        edge_id = stable_canvas_id("edge", f"atlas:aggregate:{left}:{right}:{tier}")
        labels = sorted({RELATION_LABELS[str(item["type"])] for item in items})
        expected_edges[edge_id] = {"fromNode": stable_canvas_id("chapter", left), "toNode": stable_canvas_id("chapter", right), "fromSide": "right", "toSide": "top" if any(item["type"] == "motivates" for item in items) else "left", "label": ("主线 · " if tier == "backbone" else "") + "/".join(labels) + f" ×{len(items)}", "color": BACKBONE_COLOR if tier == "backbone" else RELATION_COLORS[str(items[0]["type"])], "toEnd": "arrow"}
    actual_edges = {str(edge.get("id")): edge for edge in canvas_edges}
    if set(actual_edges) != set(expected_edges):
        errors.append({"code": "canvas-atlas-edge-set-mismatch", "missing": sorted(set(expected_edges)-set(actual_edges)), "extra": sorted(set(actual_edges)-set(expected_edges))})
    for edge_id, expected in expected_edges.items():
        edge = actual_edges.get(edge_id)
        if edge is not None and any(edge.get(field) != value for field, value in expected.items()):
            errors.append({"code": "canvas-atlas-edge-invalid", "edge": edge_id})
    semantic_edges = len(expected_edges) - max(len(chapter_keys)-1, 0)
    counts = {
        "organizers": 1 + len(chapter_keys), "atoms": 0, "internal_atoms": 0,
        "external_portals": 0, "landmarks": 0, "navigation_nodes": 2, "regions": 0,
        "backbone_edges": sum("主线" in str(item["label"]) for item in expected_edges.values()),
        "supporting_edges": semantic_edges - sum("主线" in str(item["label"]) for item in expected_edges.values()),
        "source_order_edges": max(len(chapter_keys)-1, 0), "semantic_edges": semantic_edges,
        "landmark_edges": 0,
    }
    errors.extend(validate_constellation_counts(entry, canvas_nodes, canvas_edges, counts, canvas_path))
    return errors


def validate_chapter_constellation(
    canvas_path: Path,
    entry: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    root_key: str,
    chapter_key: str,
    overview_path: Path,
    book_root: Path,
    relations: list[dict[str, Any]],
    atom_chapter: dict[str, str],
    featured_examples: set[str],
    concepts: list[dict[str, Any]],
    atom_concept_links: list[dict[str, Any]],
    concept_relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    canvas_nodes, canvas_edges, targets, errors = read_canvas_document(canvas_path)
    cards = {str(node.get("id")): node for node in canvas_nodes if node.get("type") == "text"}
    groups = {str(node.get("id")): node for node in canvas_nodes if node.get("type") == "group"}
    chapter_desc = graph_descendants(nodes, chapter_key)[1:]
    source_atoms = {key for key in chapter_desc if nodes[key].get("layer") == "atom"}
    internal_atoms = {key for key in source_atoms if validator_visible_atom(nodes, key, featured_examples)}
    exercise_atoms = [key for key in source_atoms if nodes[key].get("category") == "exercise"]
    owner_by_exercise, exercises_by_owner = validator_exercise_owners(nodes, chapter_key, exercise_atoms)
    concept_by_key = {str(item["key"]): item for item in concepts if isinstance(item, dict) and item.get("key")}
    links_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in atom_concept_links:
        if isinstance(link, dict) and str(link.get("concept_key")) in concept_by_key and str(link.get("atom_key")) in atom_chapter:
            links_by_concept[str(link["concept_key"])].append(link)

    def concept_chapters(concept_key: str) -> set[str]:
        return {atom_chapter[str(link["atom_key"])] for link in links_by_concept.get(concept_key, [])}

    def concept_is_hub(concept_key: str) -> bool:
        visible_atoms = {
            str(link["atom_key"]) for link in links_by_concept.get(concept_key, [])
            if nodes[str(link["atom_key"])].get("category") != "worked-example"
            or str(link["atom_key"]) in featured_examples
        }
        degree = sum(concept_key in {str(item.get("from_key")), str(item.get("to_key"))} for item in concept_relations)
        regions = {(atom_chapter[atom], validator_section_for(nodes, atom_chapter[atom], atom)) for atom in visible_atoms}
        cross_chapter = len({atom_chapter[atom] for atom in visible_atoms}) >= 2 or any(
            concept_key in {str(item.get("from_key")), str(item.get("to_key"))}
            and concept_chapters(str(item.get("from_key"))) != concept_chapters(str(item.get("to_key")))
            for item in concept_relations
        )
        return len(visible_atoms) >= 2 or degree >= 3 or len(regions) >= 2 or cross_chapter

    local_links_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in atom_concept_links:
        if isinstance(link, dict) and str(link.get("atom_key")) in source_atoms:
            local_links_by_concept[str(link.get("concept_key"))].append(link)
    local_hubs = {key for key in local_links_by_concept if key in concept_by_key and concept_is_hub(key)}
    chapter_concept_relations = [
        relation for relation in concept_relations
        if isinstance(relation, dict) and (
            chapter_key in concept_chapters(str(relation.get("from_key")))
            or chapter_key in concept_chapters(str(relation.get("to_key")))
        )
    ]
    chapter_relations_all = [relation for relation in relations if str(relation["from_key"]) in source_atoms or str(relation["to_key"]) in source_atoms]
    chapter_relations = [
        relation for relation in chapter_relations_all
        if validator_visible_atom(nodes, str(relation["from_key"]), featured_examples)
        and validator_visible_atom(nodes, str(relation["to_key"]), featured_examples)
        and (str(relation["from_key"]) in internal_atoms or str(relation["to_key"]) in internal_atoms)
    ]
    def representative_atom(concept_key: str, prefer_local: bool = True) -> str | None:
        candidates: list[tuple[tuple[Any, ...], str]] = []
        for link in links_by_concept.get(concept_key, []):
            atom_key = str(link["atom_key"])
            category = nodes[atom_key].get("category")
            if not (validator_visible_atom(nodes, atom_key, featured_examples) or atom_key in owner_by_exercise):
                continue
            source_start = int(nodes[atom_key]["source_range"][0])
            candidates.append(((
                0 if prefer_local and atom_key in source_atoms else 1,
                0 if link.get("role") == "introduces" and category == "knowledge" else 1,
                0 if category == "knowledge" else 1,
                source_start, atom_key,
            ), atom_key))
        return min(candidates)[1] if candidates else None

    concept_representatives: dict[str, str] = {}
    for relation in chapter_concept_relations:
        for concept_key in (str(relation["from_key"]), str(relation["to_key"])):
            if concept_key not in local_hubs:
                representative = representative_atom(concept_key)
                if representative is not None:
                    concept_representatives[concept_key] = representative
    external_atoms = {
        str(endpoint) for relation in chapter_relations
        for endpoint in (relation["from_key"], relation["to_key"])
        if str(endpoint) not in internal_atoms
    } | {
        atom_key for atom_key in concept_representatives.values()
        if atom_key not in source_atoms and validator_visible_atom(nodes, atom_key, featured_examples)
    }
    exercise_anchors: dict[str, list[str]] = defaultdict(list)
    exercise_anchor_counts: dict[tuple[str, str], int] = defaultdict(int)
    for relation in chapter_relations_all:
        left, right = str(relation["from_key"]), str(relation["to_key"])
        if right in owner_by_exercise and left in internal_atoms and nodes[left].get("category") == "knowledge":
            owner = owner_by_exercise[right]
            exercise_anchors[owner].append(left)
            exercise_anchor_counts[(owner, left)] += 1
        elif left in owner_by_exercise and right in internal_atoms and nodes[right].get("category") == "knowledge":
            owner = owner_by_exercise[left]
            exercise_anchors[owner].append(right)
            exercise_anchor_counts[(owner, right)] += 1
    for owner in exercises_by_owner:
        exercise_anchors[owner] = list(dict.fromkeys(exercise_anchors.get(owner, [])))
    direct_sections: list[str] = []
    for child in nodes[chapter_key].get("_children", nodes[chapter_key].get("children", [])):
        section = str(child) if nodes[str(child)].get("layer") == "organizer" else "__chapter_intro__"
        if section not in direct_sections:
            direct_sections.append(section)
    for owner in exercises_by_owner:
        section = validator_section_for(nodes, chapter_key, owner)
        if section not in direct_sections:
            direct_sections.append(section)
    exercise_subtree_organizers = {
        key for owner in exercises_by_owner if owner != chapter_key
        and {nodes[atom].get("category") for atom in validator_descendant_atoms(nodes, owner)} == {"exercise"}
        for key in graph_descendants(nodes, owner) if nodes[key].get("layer") == "organizer"
    }
    candidate_landmarks = {
        key for section in direct_sections if section != "__chapter_intro__"
        for key in graph_descendants(nodes, section)[1:]
        if nodes[key].get("layer") == "organizer" and key not in exercise_subtree_organizers
    }
    landmarks = {
        key for key in candidate_landmarks
        if any(descendant in internal_atoms for descendant in graph_descendants(nodes, key))
        or any(owner in set(graph_descendants(nodes, key)) for owner in exercises_by_owner)
    }
    junctions = {owner for owner, anchors in exercise_anchors.items() if len(anchors) > 1}
    expected_cards = {
        *(stable_canvas_id("card", key) for key in internal_atoms),
        *(stable_canvas_id("external", key) for key in external_atoms),
        *(stable_canvas_id("landmark", key) for key in landmarks),
        *(stable_canvas_id("exercise-organizer", key) for key in exercises_by_owner),
        *(stable_canvas_id("junction", key) for key in junctions),
        *(stable_canvas_id("concept", key) for key in local_hubs),
        stable_canvas_id("utility", f"{chapter_key}:title"),
        stable_canvas_id("utility", f"{chapter_key}:back"),
        stable_canvas_id("utility", f"{chapter_key}:legend"),
    }
    if set(cards) != expected_cards:
        errors.append({"code": "canvas-chapter-card-set-mismatch", "chapter": chapter_key, "missing": sorted(expected_cards-set(cards)), "extra": sorted(set(cards)-expected_cards)})
    expected_groups = {stable_canvas_id("region", f"{chapter_key}:{section}"): section for section in direct_sections}
    if set(groups) != set(expected_groups):
        errors.append({"code": "canvas-chapter-region-set-mismatch", "chapter": chapter_key})
    for index, section in enumerate(direct_sections, start=1):
        group = groups.get(stable_canvas_id("region", f"{chapter_key}:{section}"))
        label = "章引入" if section == "__chapter_intro__" else str(nodes[section]["title"])
        if group is not None and group.get("label") != f"{index:02d} · {label}":
            errors.append({"code": "canvas-region-order-or-label-invalid", "chapter": chapter_key, "region": section})
        if group is None:
            continue
        members = [key for key in internal_atoms if validator_section_for(nodes, chapter_key, key) == section]
        member_ids = [stable_canvas_id("card", key) for key in members]
        exercise_members = [key for key in exercises_by_owner if validator_section_for(nodes, chapter_key, key) == section]
        member_ids.extend(stable_canvas_id("exercise-organizer", key) for key in exercise_members)
        member_ids.extend(stable_canvas_id("junction", key) for key in exercise_members if key in junctions)
        if section != "__chapter_intro__":
            member_ids.extend(stable_canvas_id("landmark", key) for key in graph_descendants(nodes, section)[1:] if key in landmarks)
        for card_id in member_ids:
            card = cards.get(card_id)
            if card is None:
                continue
            if not (group["x"] <= card["x"] and group["y"] <= card["y"] and group["x"] + group["width"] >= card["x"] + card["width"] and group["y"] + group["height"] >= card["y"] + card["height"]):
                errors.append({"code": "canvas-region-containment-invalid", "chapter": chapter_key, "region": section, "card": card_id})
    for key in internal_atoms:
        card_id = stable_canvas_id("card", key)
        card = cards.get(card_id)
        if card is None:
            continue
        if targets.get(card_id) != (book_root / str(nodes[key]["_filename"])).resolve():
            errors.append({"code": "canvas-atom-target-invalid", "chapter": chapter_key, "atom": key})
        if card.get("color") != ATOM_COLORS.get(str(nodes[key].get("category"))) or f"{ATOM_LABELS.get(str(nodes[key].get('category')))} · " not in str(card.get("text")):
            errors.append({"code": "canvas-atom-visual-invalid", "chapter": chapter_key, "atom": key})
    forbidden_atom_cards = {
        stable_canvas_id("card", key) for key in source_atoms
        if key not in internal_atoms
    }
    if forbidden_atom_cards.intersection(cards):
        errors.append({"code": "canvas-unselected-atom-visible", "chapter": chapter_key, "cards": sorted(forbidden_atom_cards.intersection(cards))})
    for key in external_atoms:
        card_id = stable_canvas_id("external", key)
        if targets.get(card_id) != (book_root / str(nodes[key]["_filename"])).resolve():
            errors.append({"code": "canvas-external-target-invalid", "chapter": chapter_key, "atom": key})
    for key in landmarks:
        card_id = stable_canvas_id("landmark", key)
        if targets.get(card_id) != (book_root / str(nodes[key]["_filename"])).resolve():
            errors.append({"code": "canvas-landmark-target-invalid", "chapter": chapter_key, "organizer": key})
    for key, represented in exercises_by_owner.items():
        card_id = stable_canvas_id("exercise-organizer", key)
        if targets.get(card_id) != (book_root / str(nodes[key]["_filename"])).resolve():
            errors.append({"code": "canvas-exercise-organizer-target-invalid", "chapter": chapter_key, "organizer": key})
        card = cards.get(card_id, {})
        if card.get("color") != ATOM_COLORS["exercise"] or f"共 {len(represented)} 个练习原子" not in str(card.get("text")):
            errors.append({"code": "canvas-exercise-organizer-visual-invalid", "chapter": chapter_key, "organizer": key})
    for key in junctions:
        if stable_canvas_id("junction", key) in targets:
            errors.append({"code": "canvas-junction-must-be-virtual", "chapter": chapter_key, "organizer": key})
    for key in local_hubs:
        card_id = stable_canvas_id("concept", key)
        card = cards.get(card_id, {})
        if card_id in targets or card.get("color") != BACKBONE_COLOR or "✦ 规范概念" not in str(card.get("text")):
            errors.append({"code": "canvas-concept-hub-invalid", "chapter": chapter_key, "concept": key})
    if targets.get(stable_canvas_id("utility", f"{chapter_key}:back")) != overview_path.resolve():
        errors.append({"code": "canvas-back-target-invalid", "chapter": chapter_key})
    expected_edges: dict[str, dict[str, Any]] = {}

    def atom_display_id(atom_key: str) -> str | None:
        if atom_key in internal_atoms:
            return stable_canvas_id("card", atom_key)
        if atom_key in owner_by_exercise:
            return stable_canvas_id("exercise-organizer", owner_by_exercise[atom_key])
        if atom_key in external_atoms:
            return stable_canvas_id("external", atom_key)
        return None

    rendered_concept_relations: list[tuple[dict[str, Any], str, str]] = []
    for relation in chapter_concept_relations:
        endpoints: list[str] = []
        for concept_key in (str(relation["from_key"]), str(relation["to_key"])):
            if concept_key in local_hubs:
                endpoints.append(stable_canvas_id("concept", concept_key))
            else:
                atom_key = concept_representatives.get(concept_key)
                endpoint_id = atom_display_id(atom_key) if atom_key is not None else None
                if endpoint_id is not None:
                    endpoints.append(endpoint_id)
        if len(endpoints) == 2 and endpoints[0] != endpoints[1]:
            rendered_concept_relations.append((relation, endpoints[0], endpoints[1]))
    rendered_basis_keys = {str(item[0]["key"]) for item in rendered_concept_relations}
    rendered_chapter_relations = [
        relation for relation in chapter_relations
        if not set(str(value) for value in relation.get("basis_keys", [])).intersection(rendered_basis_keys)
    ]
    for relation in rendered_chapter_relations:
        left, right = str(relation["from_key"]), str(relation["to_key"])
        relation_type, tier = str(relation["type"]), str(relation["tier"])
        edge_id = stable_canvas_id("edge", f"{chapter_key}:relation:{relation['key']}")
        expected_edges[edge_id] = {
            "fromNode": stable_canvas_id("card", left) if left in internal_atoms else stable_canvas_id("external", left),
            "toNode": stable_canvas_id("card", right) if right in internal_atoms else stable_canvas_id("external", right),
            "fromSide": relation_sides(relation_type)[0],
            "toSide": relation_sides(relation_type)[1],
            "label": ("主线 · " if tier == "backbone" else "") + RELATION_LABELS[relation_type],
            "color": BACKBONE_COLOR if tier == "backbone" else RELATION_COLORS[relation_type],
            "toEnd": "none" if relation_type in SYMMETRIC_RELATIONS else "arrow",
        }
    concept_relation_edge_count = 0
    for relation, from_id, to_id in rendered_concept_relations:
        relation_type, tier = str(relation["type"]), str(relation["tier"])
        vertical = relation_type in {"broader", "part_of", "contrasts", "analogous"}
        edge_id = stable_canvas_id("edge", f"{chapter_key}:concept:{relation['key']}:{from_id}:{to_id}")
        expected_edges[edge_id] = {
            "fromNode": from_id, "toNode": to_id,
            "fromSide": "bottom" if vertical else "right", "toSide": "top" if vertical else "left",
            "label": ("主线 · " if tier == "backbone" else "") + CONCEPT_RELATION_LABELS[relation_type],
            "color": BACKBONE_COLOR if tier == "backbone" else RELATION_COLORS.get(relation_type, ORGANIZER_COLOR),
            "toEnd": "none" if relation_type in SYMMETRIC_RELATIONS else "arrow",
        }
        concept_relation_edge_count += 1
    concept_membership_edge_count = 0
    seen_membership: set[tuple[str, str, str]] = set()
    for concept_key in sorted(local_hubs):
        for link in local_links_by_concept[concept_key]:
            atom_key, role = str(link["atom_key"]), str(link["role"])
            endpoint_id = atom_display_id(atom_key)
            identity = concept_key, str(endpoint_id), role
            if endpoint_id is None or identity in seen_membership:
                continue
            seen_membership.add(identity)
            producer = role in {"introduces", "explains", "derives", "motivates"}
            from_id = endpoint_id if producer else stable_canvas_id("concept", concept_key)
            to_id = stable_canvas_id("concept", concept_key) if producer else endpoint_id
            edge_id = stable_canvas_id("edge", f"{chapter_key}:concept-link:{concept_key}:{endpoint_id}:{role}:{atom_key}")
            expected_edges[edge_id] = {
                "fromNode": from_id, "toNode": to_id, "fromSide": "bottom", "toSide": "top",
                "label": CONCEPT_ROLE_LABELS[role], "color": SOURCE_ORDER_COLOR, "toEnd": "arrow",
            }
            concept_membership_edge_count += 1
    exercise_edge_count = 0
    for owner, represented in exercises_by_owner.items():
        anchors = exercise_anchors.get(owner, [])
        owner_id = stable_canvas_id("exercise-organizer", owner)
        if len(anchors) > 1:
            junction_id = stable_canvas_id("junction", owner)
            for anchor in anchors:
                edge_id = stable_canvas_id("edge", f"{chapter_key}:exercise:{owner}:anchor:{anchor}")
                expected_edges[edge_id] = {
                    "fromNode": stable_canvas_id("card", anchor), "toNode": junction_id,
                    "fromSide": "bottom", "toSide": "top",
                    "label": f"练习 ×{exercise_anchor_counts[(owner, anchor)]}",
                    "color": ATOM_COLORS["exercise"], "toEnd": "arrow",
                }
                exercise_edge_count += 1
            edge_id = stable_canvas_id("edge", f"{chapter_key}:exercise:{owner}:contains")
            expected_edges[edge_id] = {
                "fromNode": junction_id, "toNode": owner_id,
                "fromSide": "bottom", "toSide": "top", "label": f"包含 ×{len(represented)}",
                "color": ATOM_COLORS["exercise"], "toEnd": "arrow",
            }
            exercise_edge_count += 1
        elif anchors:
            anchor = anchors[0]
            edge_id = stable_canvas_id("edge", f"{chapter_key}:exercise:{owner}:anchor:{anchor}")
            expected_edges[edge_id] = {
                "fromNode": stable_canvas_id("card", anchor), "toNode": owner_id,
                "fromSide": "bottom", "toSide": "top",
                "label": f"练习 ×{exercise_anchor_counts[(owner, anchor)]}",
                "color": ATOM_COLORS["exercise"], "toEnd": "arrow",
            }
            exercise_edge_count += 1
    def first_rendered_descendant(organizer_key: str) -> str | None:
        for raw_child in nodes[organizer_key].get("_children", nodes[organizer_key].get("children", [])):
            child = str(raw_child)
            child_node = nodes[child]
            if child in internal_atoms:
                return stable_canvas_id("card", child)
            if child_node.get("layer") == "atom":
                owner = owner_by_exercise.get(child)
                if owner in exercises_by_owner:
                    return stable_canvas_id("exercise-organizer", owner)
                continue
            if child in landmarks:
                return stable_canvas_id("landmark", child)
            if child in exercises_by_owner:
                return stable_canvas_id("exercise-organizer", child)
            nested = first_rendered_descendant(child)
            if nested is not None:
                return nested
        return None

    landmark_edge_count = 0
    for landmark in landmarks:
        target_id = first_rendered_descendant(landmark)
        if target_id is None:
            errors.append({"code": "canvas-landmark-without-visible-descendant", "chapter": chapter_key, "organizer": landmark})
            continue
        edge_id = stable_canvas_id("edge", f"{chapter_key}:landmark:{landmark}:{target_id}")
        expected_edges[edge_id] = {
            "fromNode": stable_canvas_id("landmark", landmark), "toNode": target_id,
            "fromSide": "bottom", "toSide": "top", "label": "包含",
            "color": SOURCE_ORDER_COLOR, "toEnd": "arrow",
        }
        landmark_edge_count += 1
    actual_edges = {str(edge.get("id")): edge for edge in canvas_edges}
    if set(actual_edges) != set(expected_edges):
        errors.append({"code": "canvas-chapter-edge-set-mismatch", "chapter": chapter_key, "missing": sorted(set(expected_edges)-set(actual_edges)), "extra": sorted(set(actual_edges)-set(expected_edges))})
    for edge_id, expected in expected_edges.items():
        edge = actual_edges.get(edge_id)
        if edge is not None and any(edge.get(field) != value for field, value in expected.items()):
            errors.append({"code": "canvas-chapter-edge-invalid", "chapter": chapter_key, "edge": edge_id})
    substantive_ids = {
        *(stable_canvas_id("card", key) for key in internal_atoms),
        *(stable_canvas_id("external", key) for key in external_atoms),
        *(stable_canvas_id("landmark", key) for key in landmarks),
        *(stable_canvas_id("exercise-organizer", key) for key in exercises_by_owner),
        *(stable_canvas_id("junction", key) for key in junctions),
        *(stable_canvas_id("concept", key) for key in local_hubs),
    }
    if len(substantive_ids) > 1:
        incident_ids = {
            str(endpoint)
            for edge in canvas_edges
            for endpoint in (edge.get("fromNode"), edge.get("toNode"))
            if endpoint is not None
        }
        isolated_ids = sorted(substantive_ids - incident_ids)
        if isolated_ids:
            errors.append({"code": "canvas-isolated-substantive-node", "chapter": chapter_key, "nodes": isolated_ids})
    counts = {
        "organizers": 1 + sum(nodes[key].get("layer") == "organizer" for key in chapter_desc),
        "atoms": len(internal_atoms), "source_atoms": len(source_atoms), "internal_atoms": len(internal_atoms),
        "exercise_atoms_collapsed": len(exercise_atoms),
        "featured_examples": len(featured_examples.intersection(source_atoms)),
        "hidden_examples": sum(nodes[key].get("category") == "worked-example" and key not in featured_examples for key in source_atoms),
        "exercise_organizers": len(exercises_by_owner), "virtual_nodes": len(junctions),
        "concept_hubs": len(local_hubs), "concept_membership_edges": concept_membership_edge_count,
        "concept_relation_edges": concept_relation_edge_count,
        "external_portals": len(external_atoms), "landmarks": len(landmarks), "navigation_nodes": 3, "regions": len(direct_sections),
        "backbone_edges": sum(relation.get("tier") == "backbone" for relation in rendered_chapter_relations) + sum(item[0].get("tier") == "backbone" for item in rendered_concept_relations),
        "supporting_edges": sum(relation.get("tier") == "supporting" for relation in rendered_chapter_relations) + sum(item[0].get("tier") == "supporting" for item in rendered_concept_relations) + exercise_edge_count + concept_membership_edge_count,
        "source_order_edges": 0, "semantic_edges": len(rendered_chapter_relations) + concept_relation_edge_count + concept_membership_edge_count, "exercise_aggregate_edges": exercise_edge_count,
        "landmark_edges": landmark_edge_count,
    }
    errors.extend(validate_constellation_counts(entry, canvas_nodes, canvas_edges, counts, canvas_path))
    return errors


def validate_v3_map_document(
    canvas_path: Path,
    entry: dict[str, Any],
    expected_atoms: set[str],
    expected_exercise_owners: set[str],
    expected_portals: dict[str, Path],
    nodes: dict[str, dict[str, Any]],
    book_root: Path,
    concepts: list[dict[str, Any]],
    atom_concept_links: list[dict[str, Any]],
    chapter_level: bool,
) -> list[dict[str, Any]]:
    canvas_nodes, canvas_edges, targets, errors = read_canvas_document(canvas_path)
    errors.extend(text_overlap_errors(canvas_nodes, canvas_path))
    cards = {str(item.get("id")): item for item in canvas_nodes if item.get("type") == "text"}
    actual_atom_ids = {stable_canvas_id("card", key) for key in expected_atoms}
    missing_atoms = sorted(actual_atom_ids - set(cards))
    unexpected_exercise_atoms = sorted(
        stable_canvas_id("card", key) for key, node in nodes.items()
        if node.get("category") == "exercise" and stable_canvas_id("card", key) in cards
    )
    if missing_atoms:
        errors.append({"code": "canvas-v3-visible-atom-missing", "path": str(canvas_path), "node_ids": missing_atoms})
    if unexpected_exercise_atoms:
        errors.append({"code": "canvas-v3-individual-exercise-forbidden", "path": str(canvas_path), "node_ids": unexpected_exercise_atoms})
    for key in expected_atoms:
        node_id = stable_canvas_id("card", key)
        expected_target = (book_root / str(nodes[key]["_filename"])).resolve()
        if targets.get(node_id) != expected_target:
            errors.append({"code": "canvas-v3-atom-target-invalid", "path": str(canvas_path), "atom_key": key})
        if cards.get(node_id, {}).get("color") != ATOM_COLORS.get(str(nodes[key].get("category"))):
            errors.append({"code": "canvas-v3-atom-color-invalid", "path": str(canvas_path), "atom_key": key})
    expected_entries = {stable_canvas_id("exercise-entry", key) for key in expected_exercise_owners}
    actual_entries = {node_id for node_id in cards if node_id in expected_entries}
    if actual_entries != expected_entries:
        errors.append({"code": "canvas-v3-exercise-entry-coverage", "path": str(canvas_path), "missing": sorted(expected_entries - actual_entries)})
    if chapter_level and expected_entries:
        errors.append({"code": "canvas-v3-chapter-exercise-entry-forbidden", "path": str(canvas_path)})
    for key in expected_exercise_owners:
        node_id = stable_canvas_id("exercise-entry", key)
        if targets.get(node_id) != (book_root / str(nodes[key]["_filename"])).resolve():
            errors.append({"code": "canvas-v3-exercise-target-invalid", "path": str(canvas_path), "organizer": key})
    for portal_id, target in expected_portals.items():
        if portal_id not in cards or targets.get(portal_id) != target.resolve():
            errors.append({"code": "canvas-v3-section-portal-invalid", "path": str(canvas_path), "portal": portal_id})
    for edge in canvas_edges:
        if edge.get("fromSide") not in {"left", "right", "top", "bottom"} or edge.get("toSide") not in {"left", "right", "top", "bottom"}:
            errors.append({"code": "canvas-v3-edge-port-invalid", "path": str(canvas_path), "edge": edge.get("id")})
        if chapter_level and str(edge.get("label", "")).startswith("练习"):
            errors.append({"code": "canvas-v3-practice-edge-leaked-to-chapter", "path": str(canvas_path), "edge": edge.get("id")})
    concept_by_id = {stable_canvas_id("concept", str(item["key"])): str(item["key"]) for item in concepts if item.get("key")}
    links_by_concept: dict[str, set[str]] = defaultdict(set)
    for link in atom_concept_links:
        atom_key, concept_key = str(link.get("atom_key")), str(link.get("concept_key"))
        if atom_key in expected_atoms:
            links_by_concept[concept_key].add(atom_key)
    concept_ids = set(cards).intersection(concept_by_id)
    for node_id in concept_ids:
        concept_key = concept_by_id[node_id]
        if len(links_by_concept.get(concept_key, set())) < 2:
            errors.append({"code": "canvas-v3-one-to-one-concept-hub-forbidden", "path": str(canvas_path), "concept_key": concept_key})
    substantive = actual_atom_ids | expected_entries | concept_ids
    incident = {str(endpoint) for edge in canvas_edges for endpoint in (edge.get("fromNode"), edge.get("toNode"))}
    isolated = sorted(node_id for node_id in substantive if node_id in cards and node_id not in incident)
    if len(substantive) > 1 and isolated:
        errors.append({"code": "canvas-isolated-substantive-node", "path": str(canvas_path), "nodes": isolated})
    counts = entry.get("counts")
    if not isinstance(counts, dict):
        errors.append({"code": "canvas-index-counts-missing", "path": str(canvas_path)})
    else:
        actual_basic = {
            "cards": sum(item.get("type") == "text" for item in canvas_nodes),
            "groups": sum(item.get("type") == "group" for item in canvas_nodes),
            "edges": len(canvas_edges),
            "internal_atoms": len(expected_atoms),
            "concept_hubs": len(concept_ids),
        }
        for field, value in actual_basic.items():
            if counts.get(field) != value:
                errors.append({"code": "canvas-index-count-mismatch", "path": str(canvas_path), "field": field, "expected": value, "actual": counts.get(field)})
        if chapter_level and counts.get("exercise_relation_edges") != 0:
            errors.append({"code": "canvas-v3-chapter-practice-count-invalid", "path": str(canvas_path)})
        if not chapter_level and counts.get("exercise_organizers") != len(expected_exercise_owners):
            errors.append({"code": "canvas-v3-section-exercise-count-invalid", "path": str(canvas_path)})
    actual_bounds = canvas_bounds(canvas_nodes)
    if entry.get("bounds") != actual_bounds:
        errors.append({"code": "canvas-index-bounds-mismatch", "path": str(canvas_path), "expected": actual_bounds, "actual": entry.get("bounds")})
    if sum(item.get("type") == "text" for item in canvas_nodes) >= 30 and not 0.5 <= float(actual_bounds["aspect_ratio"]) <= 2.0:
        errors.append({"code": "canvas-aspect-ratio-invalid", "path": str(canvas_path), "aspect_ratio": actual_bounds["aspect_ratio"]})
    if not isinstance(entry.get("visual_quality"), dict):
        errors.append({"code": "canvas-v3-visual-quality-missing", "path": str(canvas_path)})
    return errors


def validate_constellation_bundle_v3(
    index: dict[str, Any], canvas_index_path: Path, manifest_path: Path, book_root: Path,
    nodes: dict[str, dict[str, Any]], organizers: list[dict[str, Any]], atoms: list[dict[str, Any]],
    relations: list[dict[str, Any]], relation_review: Any, concepts: list[dict[str, Any]],
    atom_concept_links: list[dict[str, Any]], concept_relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    index_root = canvas_index_path.parent
    if Path(str(index.get("manifest", ""))).expanduser().resolve() != manifest_path or index.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append({"code": "canvas-index-manifest-binding-invalid"})
    if Path(str(index.get("book_root", ""))).expanduser().resolve() != book_root:
        errors.append({"code": "canvas-index-book-root-mismatch"})
    expected_layout = {
        "mode": "three-level-constellation", "theme": "adaptive",
        "zoom_levels": ["book-chapters", "chapter-core", "section-detail"],
        "learning_direction": "center-outward-clockwise",
        "organization_encoding": "regions-with-click-through-portals",
        "atom_visibility": "chapter-core-and-section-detail",
        "exercise_representation": "chapter-counts-section-primary-entries",
        "concept_hub_visibility": "multi-atom-and-semantic-bridge-only",
        "edge_noise_policy": "one-primary-practice-edge-per-exercise-organizer",
        "edge_ports": {"progression": "right-to-left", "inspiration": "right-to-top", "support-and-containment": "bottom-to-top"},
    }
    if index.get("layout") != expected_layout:
        errors.append({"code": "canvas-index-layout-invalid"})
    roots = [node for node in organizers if node.get("parent_key") is None]
    if len(roots) != 1:
        return [*errors, {"code": "canvas-index-root-unavailable"}]
    root_key = str(roots[0]["key"])
    chapters = [str(key) for key in nodes[root_key].get("_children", []) if nodes.get(str(key), {}).get("layer") == "organizer"]
    semantic_ready = isinstance(relation_review, dict) and relation_review.get("status") == "passed" and relation_review.get("unresolved_count") == 0
    if index.get("relation_status") != ("passed" if semantic_ready else "review_required"):
        errors.append({"code": "canvas-index-relation-status-invalid"})
    chapter_entries = index.get("chapter_maps") if isinstance(index.get("chapter_maps"), list) else []
    section_entries = index.get("section_maps") if isinstance(index.get("section_maps"), list) else []
    if [str(item.get("root_key")) for item in chapter_entries] != chapters:
        errors.append({"code": "canvas-chapter-order-or-coverage", "expected": chapters})
    chapter_paths: dict[str, Path] = {}
    for entry in chapter_entries:
        chapter = str(entry.get("root_key"))
        if entry.get("role") != "chapter-knowledge-map" or entry.get("status") != ("ready" if semantic_ready else "relation-review-required"):
            errors.append({"code": "canvas-chapter-entry-invalid", "chapter": chapter})
        if semantic_ready:
            try:
                chapter_paths[chapter] = resolve_canvas_index_path(entry.get("path"), index_root)
            except Exception as exc:
                errors.append({"code": "canvas-chapter-path-invalid", "chapter": chapter, "detail": str(exc)})
    expected_sections: list[tuple[str, str]] = []
    for chapter in chapters:
        values: list[str] = []
        for child in nodes[chapter].get("_children", []):
            child_key = str(child)
            section = child_key if nodes[child_key].get("layer") == "organizer" else "__chapter_intro__"
            if section not in values:
                values.append(section)
        expected_sections.extend((chapter, section) for section in (values or ["__chapter_intro__"]))
    actual_sections = [(str(item.get("chapter_key")), str(item.get("root_key"))) for item in section_entries]
    if actual_sections != expected_sections:
        errors.append({"code": "canvas-v3-section-order-or-coverage", "expected": expected_sections, "actual": actual_sections})
    section_paths: dict[tuple[str, str], Path] = {}
    for entry in section_entries:
        identity = str(entry.get("chapter_key")), str(entry.get("root_key"))
        if entry.get("role") != "section-detail-map" or entry.get("status") != ("ready" if semantic_ready else "relation-review-required"):
            errors.append({"code": "canvas-v3-section-entry-invalid", "identity": identity})
        if semantic_ready:
            try:
                section_paths[identity] = resolve_canvas_index_path(entry.get("path"), index_root)
            except Exception as exc:
                errors.append({"code": "canvas-v3-section-path-invalid", "identity": identity, "detail": str(exc)})
    featured = {str(key) for key in relation_review.get("featured_example_keys", []) if str(key) in nodes} if isinstance(relation_review, dict) else set()
    atlas = index.get("atlas") if isinstance(index.get("atlas"), dict) else {}
    try:
        atlas_path = resolve_canvas_index_path(atlas.get("path"), index_root)
        expected_targets = chapter_paths if semantic_ready else {key: (book_root / str(nodes[key]["_filename"])).resolve() for key in chapters}
        errors.extend(validate_atlas_canvas(atlas_path, atlas, nodes, root_key, chapters, expected_targets, book_root, relations, {str(atom["key"]): validator_chapter_for(nodes, root_key, str(atom["key"])) for atom in atoms}, semantic_ready, featured))
    except Exception as exc:
        errors.append({"code": "canvas-atlas-path-invalid", "detail": str(exc)})
    if not semantic_ready:
        return errors
    chapter_entry_by_key = {str(item.get("root_key")): item for item in chapter_entries}
    section_entry_by_key = {(str(item.get("chapter_key")), str(item.get("root_key"))): item for item in section_entries}
    for chapter in chapters:
        chapter_desc = graph_descendants(nodes, chapter)[1:]
        visible = {key for key in chapter_desc if nodes[key].get("layer") == "atom" and validator_visible_atom(nodes, key, featured)}
        section_portals = {
            stable_canvas_id("section-portal", f"{chapter}:{section}"): section_paths[(chapter, section)]
            for owner, section in expected_sections if owner == chapter and (chapter, section) in section_paths
        }
        if chapter in chapter_paths:
            errors.extend(validate_v3_map_document(chapter_paths[chapter], chapter_entry_by_key[chapter], visible, set(), section_portals, nodes, book_root, concepts, atom_concept_links, True))
    for chapter, section in expected_sections:
        if (chapter, section) not in section_paths:
            continue
        if section == "__chapter_intro__":
            source_atoms = [str(key) for key in nodes[chapter].get("_children", []) if nodes[str(key)].get("layer") == "atom"]
        else:
            source_atoms = [key for key in graph_descendants(nodes, section)[1:] if nodes[key].get("layer") == "atom"]
        visible = {key for key in source_atoms if validator_visible_atom(nodes, key, featured)}
        exercises = [key for key in source_atoms if nodes[key].get("category") == "exercise"]
        _, by_owner = validator_exercise_owners(nodes, chapter, exercises)
        errors.extend(validate_v3_map_document(section_paths[(chapter, section)], section_entry_by_key[(chapter, section)], visible, set(by_owner), {}, nodes, book_root, concepts, atom_concept_links, False))
    return errors


def validate_constellation_bundle(
    canvas_index_path: Path,
    manifest_path: Path,
    book_root: Path,
    nodes: dict[str, dict[str, Any]],
    organizers: list[dict[str, Any]],
    atoms: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    relation_review: Any,
    concepts: list[dict[str, Any]],
    atom_concept_links: list[dict[str, Any]],
    concept_relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    canvas_index_path = canvas_index_path.expanduser().resolve()
    try:
        index = load_json(canvas_index_path)
    except Exception as exc:
        return [{"code": "canvas-index-invalid", "detail": str(exc)}]
    if index.get("schema_version") == 3:
        return validate_constellation_bundle_v3(
            index, canvas_index_path, manifest_path, book_root, nodes, organizers, atoms,
            relations, relation_review, concepts, atom_concept_links, concept_relations,
        )
    index_root = canvas_index_path.parent
    if index.get("schema_version") != 2:
        errors.append({"code": "canvas-index-schema-version"})
    if Path(str(index.get("manifest", ""))).expanduser().resolve() != manifest_path or index.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append({"code": "canvas-index-manifest-binding-invalid"})
    if Path(str(index.get("book_root", ""))).expanduser().resolve() != book_root:
        errors.append({"code": "canvas-index-book-root-mismatch"})
    expected_layout = {
        "mode": "two-level-constellation", "theme": "adaptive",
        "zoom_levels": ["book-chapters", "chapter-atoms"], "learning_direction": "center-outward",
        "organization_encoding": "regions-and-landmarks", "source_region_order": "clockwise",
        "atom_visibility": "knowledge-scenario-and-bridge-examples",
        "exercise_representation": "organizer-clusters",
        "virtual_nodes": "exercise-convergence-and-selective-concept-hubs",
        "concept_hub_visibility": "two-displays-or-degree-three-or-cross-region-or-cross-chapter",
        "edge_ports": {
            "progression": "right-to-left", "inspiration": "right-to-top",
            "support-and-containment": "bottom-to-top",
        },
    }
    if index.get("layout") != expected_layout:
        errors.append({"code": "canvas-index-layout-invalid"})
    roots = [node for node in organizers if node.get("parent_key") is None]
    if len(roots) != 1:
        return [*errors, {"code": "canvas-index-root-unavailable"}]
    root_key = str(roots[0]["key"])
    chapter_keys = [str(key) for key in nodes[root_key].get("_children", []) if nodes.get(str(key), {}).get("layer") == "organizer"]
    if any(nodes.get(str(key), {}).get("layer") == "atom" for key in nodes[root_key].get("_children", [])):
        errors.append({"code": "canvas-root-atoms-forbidden"})
    semantic_ready = isinstance(relation_review, dict) and relation_review.get("status") == "passed" and relation_review.get("unresolved_count") == 0
    featured_examples = {
        str(key) for key in relation_review.get("featured_example_keys", [])
        if isinstance(relation_review, dict) and str(key) in nodes and nodes[str(key)].get("category") == "worked-example"
    } if isinstance(relation_review, dict) else set()
    if index.get("relation_status") != ("passed" if semantic_ready else "review_required"):
        errors.append({"code": "canvas-index-relation-status-invalid"})
    atlas_entry = index.get("atlas")
    if not isinstance(atlas_entry, dict) or atlas_entry.get("role") != "book-atlas" or atlas_entry.get("root_key") != root_key or atlas_entry.get("path") != "overview.canvas":
        errors.append({"code": "canvas-atlas-entry-invalid"})
        atlas_entry = {}
    raw_chapters = index.get("chapter_maps")
    if not isinstance(raw_chapters, list) or not all(isinstance(item, dict) for item in raw_chapters):
        errors.append({"code": "canvas-chapter-entries-invalid"})
        raw_chapters = []
    if [str(item.get("root_key")) for item in raw_chapters] != chapter_keys:
        errors.append({"code": "canvas-chapter-order-or-coverage", "expected": chapter_keys})
    chapter_paths: dict[str, Path] = {}
    for entry in raw_chapters:
        key = str(entry.get("root_key"))
        expected_status = "ready" if semantic_ready else "relation-review-required"
        if entry.get("role") != "chapter-knowledge-map" or entry.get("status") != expected_status:
            errors.append({"code": "canvas-chapter-entry-invalid", "chapter": key})
        if semantic_ready:
            try:
                path = resolve_canvas_index_path(entry.get("path"), index_root)
                chapter_paths[key] = path
            except Exception as exc:
                errors.append({"code": "canvas-chapter-path-invalid", "chapter": key, "detail": str(exc)})
        elif entry.get("path") is not None or entry.get("counts") is not None or entry.get("bounds") is not None:
            errors.append({"code": "canvas-pending-chapter-must-have-no-output", "chapter": key})
    atom_chapter = {str(atom["key"]): validator_chapter_for(nodes, root_key, str(atom["key"])) for atom in atoms}
    try:
        atlas_path = resolve_canvas_index_path(atlas_entry.get("path"), index_root)
        expected_chapter_paths = chapter_paths if semantic_ready else {key: (book_root / str(nodes[key]["_filename"])).resolve() for key in chapter_keys}
        errors.extend(validate_atlas_canvas(atlas_path, atlas_entry, nodes, root_key, chapter_keys, expected_chapter_paths, book_root, relations, atom_chapter, semantic_ready, featured_examples))
    except Exception as exc:
        errors.append({"code": "canvas-atlas-path-invalid", "detail": str(exc)})
        atlas_path = index_root / "overview.canvas"
    if semantic_ready:
        occurrences = {
            str(atom["key"]): 0 for atom in atoms
            if validator_visible_atom(nodes, str(atom["key"]), featured_examples)
        }
        by_key = {str(entry.get("root_key")): entry for entry in raw_chapters}
        for chapter_key in chapter_keys:
            for key in graph_descendants(nodes, chapter_key):
                if key in occurrences:
                    occurrences[key] += 1
            if chapter_key in chapter_paths:
                errors.extend(validate_chapter_constellation(
                    chapter_paths[chapter_key], by_key[chapter_key], nodes, root_key,
                    chapter_key, atlas_path, book_root, relations, atom_chapter,
                    featured_examples, concepts, atom_concept_links, concept_relations,
                ))
        invalid = {key: value for key, value in occurrences.items() if value != 1}
        if invalid:
            errors.append({"code": "canvas-atom-chapter-coverage", "actual": invalid})
    return errors


def validate_atomization_review(
    profile: dict[str, Any],
    manifest: dict[str, Any],
    source_markdown_sha256: str | None,
    atoms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Require sealed two-pass evidence only when the profile enables it."""
    errors: list[dict[str, Any]] = []
    config = profile.get("atomization")
    if config is None:
        return errors
    if not isinstance(config, dict):
        return [{"code": "atomization-config-invalid"}]
    expected_config = {
        "mode": "llm-two-pass",
        "knowledge_granularity": "complete-teaching-unit",
        "scenario_policy": "substantial-only",
    }
    for field, expected in expected_config.items():
        if config.get(field) != expected:
            errors.append(
                {
                    "code": "atomization-config-invalid",
                    "field": field,
                    "expected": expected,
                }
            )
    for field in ("confidence_threshold", "short_atom_confidence_threshold"):
        value = config.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= float(value) <= 1
        ):
            errors.append({"code": "atomization-config-invalid", "field": field})
    role_audit_required = config.get("teaching_role_audit") == "required-before-materialization"
    if "teaching_role_audit" in config and not role_audit_required:
        errors.append({"code": "atomization-config-invalid", "field": "teaching_role_audit"})
    if role_audit_required:
        value = config.get("role_correction_confidence_threshold")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            errors.append({"code": "atomization-config-invalid", "field": "role_correction_confidence_threshold"})
    review = manifest.get("atomization_review")
    if not isinstance(review, dict):
        return [*errors, {"code": "atomization-review-missing"}]
    if review.get("status") != "passed" or review.get("unresolved_count") != 0:
        errors.append({"code": "atomization-review-incomplete"})
    if role_audit_required:
        role_review = review.get("role_review")
        if not isinstance(role_review, dict) or role_review.get("status") != "passed" or role_review.get("unresolved_count") != 0:
            errors.append({"code": "atom-teaching-role-review-missing-or-incomplete"})
    final_binding = review.get("final_artifact")
    if not isinstance(final_binding, dict):
        return [*errors, {"code": "atomization-final-binding-missing"}]
    final_path = Path(str(final_binding.get("path", ""))).expanduser().resolve()
    if not final_path.is_file():
        return [
            *errors,
            {"code": "atomization-final-missing", "path": str(final_path)},
        ]
    try:
        final = load_json(final_path)
    except Exception as exc:
        return [
            *errors,
            {"code": "atomization-final-invalid", "detail": str(exc)},
        ]
    digest = artifact_digest(final)
    if (
        final.get("artifact_sha256") != digest
        or final_binding.get("sha256") != digest
    ):
        errors.append({"code": "atomization-final-digest-mismatch"})
    if (
        final.get("kind") != "atomization-final"
        or final.get("status") != "passed"
        or final.get("unresolved_count") != 0
    ):
        errors.append({"code": "atomization-final-not-passed"})
    if final.get("source_markdown_sha256") != source_markdown_sha256:
        errors.append({"code": "atomization-source-digest-mismatch"})

    for name, binding in review.get("bindings", {}).items():
        if not isinstance(binding, dict):
            errors.append({"code": "atomization-binding-invalid", "binding": name})
            continue
        path = Path(str(binding.get("path", ""))).expanduser().resolve()
        if not path.is_file():
            errors.append(
                {
                    "code": "atomization-binding-missing",
                    "binding": name,
                    "path": str(path),
                }
            )
            continue
        try:
            artifact = load_json(path)
        except Exception as exc:
            errors.append(
                {
                    "code": "atomization-binding-invalid",
                    "binding": name,
                    "detail": str(exc),
                }
            )
            continue
        if (
            artifact.get("artifact_sha256") != artifact_digest(artifact)
            or binding.get("sha256") != artifact.get("artifact_sha256")
        ):
            errors.append(
                {"code": "atomization-binding-digest-mismatch", "binding": name}
            )

    final_atoms = final.get("atoms")
    if not isinstance(final_atoms, list):
        errors.append({"code": "atomization-final-atoms-invalid"})
        return errors
    final_by_id = {
        str(atom.get("atom_id")): atom
        for atom in final_atoms
        if isinstance(atom, dict) and isinstance(atom.get("atom_id"), str)
    }
    manifest_by_id = {
        str(atom.get("atomization_id")): atom
        for atom in atoms
        if isinstance(atom.get("atomization_id"), str)
    }
    if set(final_by_id) != set(manifest_by_id):
        errors.append(
            {
                "code": "atomization-materialization-coverage-mismatch",
                "missing": sorted(set(final_by_id) - set(manifest_by_id)),
                "extra": sorted(set(manifest_by_id) - set(final_by_id)),
            }
        )
    for atom_id in set(final_by_id).intersection(manifest_by_id):
        final_atom = final_by_id[atom_id]
        manifest_atom = manifest_by_id[atom_id]
        for field in ("owner_key", "source_range", "category", "title"):
            actual = (
                manifest_atom.get("parent_key")
                if field == "owner_key"
                else manifest_atom.get(field)
            )
            if actual != final_atom.get(field):
                errors.append(
                    {
                        "code": "atomization-materialization-mismatch",
                        "atom_id": atom_id,
                        "field": field,
                    }
                )
    return errors


def validate_organizer_review(
    manifest: dict[str, Any],
    source_markdown_sha256: str | None,
    node_keys: set[str],
) -> list[dict[str, Any]]:
    """Validate optional evidence that activity headings were demoted safely."""
    binding = manifest.get("organizer_review")
    if binding is None:
        return []
    if not isinstance(binding, dict) or binding.get("status") != "passed":
        return [{"code": "organizer-review-invalid"}]
    path = Path(str(binding.get("path", ""))).expanduser().resolve()
    if not path.is_file():
        return [{"code": "organizer-review-missing", "path": str(path)}]
    try:
        review = load_json(path)
    except Exception as exc:
        return [{"code": "organizer-review-invalid", "detail": str(exc)}]
    errors: list[dict[str, Any]] = []
    digest = artifact_digest(review)
    if review.get("kind") != "organizer-review" or review.get("status") != "passed":
        errors.append({"code": "organizer-review-not-passed"})
    if review.get("artifact_sha256") != digest or binding.get("sha256") != digest:
        errors.append({"code": "organizer-review-digest-mismatch"})
    if review.get("source_markdown_sha256") != source_markdown_sha256:
        errors.append({"code": "organizer-review-source-digest-mismatch"})
    demoted = set(binding.get("demoted_organizer_keys", []))
    synthesized = set(binding.get("synthesized_organizer_keys", []))
    if demoted.intersection(node_keys):
        errors.append({"code": "organizer-review-demotion-not-applied", "nodes": sorted(demoted.intersection(node_keys))})
    if not synthesized.issubset(node_keys):
        errors.append({"code": "organizer-review-topic-missing", "nodes": sorted(synthesized-node_keys)})
    return errors


def validate_dual_layer_graph(manifest: dict[str, Any], nodes: dict[str, dict[str, Any]], relation_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate canonical concepts, instructional links, and concept relations."""
    errors: list[dict[str, Any]] = []
    concepts = manifest.get("concepts")
    links = manifest.get("atom_concept_links")
    concept_relations = manifest.get("concept_relations")
    if not isinstance(concepts, list) or not isinstance(links, list) or not isinstance(concept_relations, list):
        return [{"code": "dual-layer-fields-missing"}]
    concept_by_key: dict[str, dict[str, Any]] = {}
    evidence_atoms: dict[str, set[str]] = defaultdict(set)
    for index, concept in enumerate(concepts):
        if not isinstance(concept, dict):
            errors.append({"code": "concept-invalid", "index": index})
            continue
        key = concept.get("key")
        if not isinstance(key, str) or not key or key in concept_by_key:
            errors.append({"code": "concept-key-invalid", "index": index})
            continue
        concept_by_key[key] = concept
        if concept.get("kind") not in CONCEPT_KINDS or not isinstance(concept.get("preferred_label"), str) or not concept["preferred_label"].strip() or not isinstance(concept.get("definition"), str) or len(concept["definition"].strip()) < 8:
            errors.append({"code": "concept-description-invalid", "concept": key})
        if not isinstance(concept.get("aliases"), list) or not all(isinstance(item, str) and item.strip() for item in concept.get("aliases", [])):
            errors.append({"code": "concept-aliases-invalid", "concept": key})
        evidence = concept.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append({"code": "concept-evidence-missing", "concept": key})
            evidence = []
        for item in evidence:
            atom_key = item.get("atom_key") if isinstance(item, dict) else None
            source_range = item.get("source_range") if isinstance(item, dict) else None
            atom = nodes.get(str(atom_key))
            atom_range = atom.get("source_range") if isinstance(atom, dict) else None
            if (
                not isinstance(atom, dict) or atom.get("layer") != "atom"
                or not isinstance(source_range, list) or len(source_range) != 2
                or not all(isinstance(value, int) for value in source_range)
                or not isinstance(atom_range, list) or len(atom_range) != 2
                or source_range[0] < atom_range[0] or source_range[1] > atom_range[1] or source_range[0] > source_range[1]
            ):
                errors.append({"code": "concept-evidence-invalid", "concept": key})
            else:
                evidence_atoms[key].add(str(atom_key))
    link_keys: set[str] = set()
    linked_atoms: set[str] = set()
    grounded_concepts: set[str] = set()
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            errors.append({"code": "atom-concept-link-invalid", "index": index})
            continue
        key, atom_key, concept_key = link.get("key"), link.get("atom_key"), link.get("concept_key")
        atom = nodes.get(str(atom_key))
        if not isinstance(key, str) or not key or key in link_keys or not isinstance(atom, dict) or atom.get("layer") != "atom" or concept_key not in concept_by_key or link.get("role") not in ATOM_CONCEPT_ROLES:
            errors.append({"code": "atom-concept-link-invalid", "index": index})
            continue
        link_keys.add(key)
        linked_atoms.add(str(atom_key))
        grounded_concepts.add(str(concept_key))
        confidence = link.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            errors.append({"code": "atom-concept-confidence-invalid", "link": key})
        ranges = link.get("evidence_ranges")
        atom_range = atom.get("source_range")
        if not isinstance(atom_range, list) or len(atom_range) != 2 or not isinstance(ranges, list) or not ranges or any(
            not isinstance(value, list) or len(value) != 2 or not all(isinstance(number, int) for number in value)
            or value[0] < atom_range[0] or value[1] > atom_range[1] or value[0] > value[1]
            for value in ranges
        ):
            errors.append({"code": "atom-concept-evidence-invalid", "link": key})
    atom_keys = {key for key, node in nodes.items() if node.get("layer") == "atom"}
    if linked_atoms != atom_keys:
        errors.append({"code": "atom-concept-coverage-invalid", "missing": sorted(atom_keys - linked_atoms)})
    if grounded_concepts != set(concept_by_key):
        errors.append({"code": "concept-grounding-invalid", "missing": sorted(set(concept_by_key) - grounded_concepts)})
    relation_keys: set[str] = set()
    for index, relation in enumerate(concept_relations):
        if not isinstance(relation, dict):
            errors.append({"code": "concept-relation-invalid", "index": index})
            continue
        key, left, right = relation.get("key"), relation.get("from_key"), relation.get("to_key")
        relation_type, evidence_kind = relation.get("type"), relation.get("evidence_kind")
        if not isinstance(key, str) or not key or key in relation_keys or left not in concept_by_key or right not in concept_by_key or left == right or relation_type not in CONCEPT_RELATION_TYPES or relation.get("tier") not in {"backbone", "supporting"} or evidence_kind not in {"explicit", "pedagogical-inference"}:
            errors.append({"code": "concept-relation-invalid", "index": index})
            continue
        relation_keys.add(key)
        if relation_type in SYMMETRIC_RELATIONS and str(left) > str(right):
            errors.append({"code": "concept-relation-symmetric-order-invalid", "relation": key})
        confidence = relation.get("confidence")
        threshold = float(relation_config.get("explicit_confidence_threshold" if evidence_kind == "explicit" else "inferred_confidence_threshold", 0.90 if evidence_kind == "explicit" else 0.95))
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or float(confidence) < threshold or float(confidence) > 1:
            errors.append({"code": "concept-relation-confidence-invalid", "relation": key})
        evidence = relation.get("evidence")
        covered: set[str] = set()
        if not isinstance(evidence, list) or not evidence:
            errors.append({"code": "concept-relation-evidence-missing", "relation": key})
            evidence = []
        for item in evidence:
            atom_key = item.get("atom_key") if isinstance(item, dict) else None
            source_range = item.get("source_range") if isinstance(item, dict) else None
            atom = nodes.get(str(atom_key))
            atom_range = atom.get("source_range") if isinstance(atom, dict) else None
            if not isinstance(atom, dict) or atom.get("layer") != "atom" or not isinstance(atom_range, list) or len(atom_range) != 2 or not isinstance(source_range, list) or len(source_range) != 2 or not all(isinstance(value, int) for value in source_range) or source_range[0] < atom_range[0] or source_range[1] > atom_range[1] or source_range[0] > source_range[1]:
                errors.append({"code": "concept-relation-evidence-invalid", "relation": key})
            else:
                covered.add(str(atom_key))
        if evidence_kind == "pedagogical-inference" and not (covered & evidence_atoms[str(left)] and covered & evidence_atoms[str(right)]):
            errors.append({"code": "concept-relation-inference-needs-both-endpoints", "relation": key})
        if not isinstance(relation.get("rationale"), str) or len(relation["rationale"].strip()) < 12:
            errors.append({"code": "concept-relation-rationale-invalid", "relation": key})
    for relation in manifest.get("relations", []):
        if isinstance(relation, dict):
            basis = relation.get("basis_keys", [])
            if not isinstance(basis, list) or not all(isinstance(value, str) and value in relation_keys for value in basis):
                errors.append({"code": "relation-concept-basis-invalid", "relation": relation.get("key")})
    return errors


def validate_relation_review(
    manifest: dict[str, Any],
    source_markdown_sha256: str | None,
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate the sealed relation artifact when semantic relations were applied."""
    review = manifest.get("relation_review")
    if review is None:
        return []
    if not isinstance(review, dict):
        return [{"code": "relation-review-invalid"}]
    errors: list[dict[str, Any]] = []
    mode = review.get("mode")
    if review.get("status") != "passed" or mode not in {"llm-two-pass", "llm-three-pass"} or review.get("unresolved_count") != 0:
        errors.append({"code": "relation-review-incomplete"})
    if mode == "llm-three-pass" and review.get("graph_model") != "atom-concept-dual-layer":
        errors.append({"code": "relation-review-graph-model-invalid"})
    final_binding = review.get("final_artifact")
    if not isinstance(final_binding, dict):
        return [*errors, {"code": "relation-final-binding-missing"}]
    final_path = Path(str(final_binding.get("path", ""))).expanduser().resolve()
    if not final_path.is_file():
        return [*errors, {"code": "relation-final-missing", "path": str(final_path)}]
    try:
        final = load_json(final_path)
    except Exception as exc:
        return [*errors, {"code": "relation-final-invalid", "detail": str(exc)}]
    digest = artifact_digest(final)
    if final.get("artifact_sha256") != digest or final_binding.get("sha256") != digest:
        errors.append({"code": "relation-final-digest-mismatch"})
    expected_kind = "relation-final-v2" if mode == "llm-three-pass" else "relation-final"
    if final.get("kind") != expected_kind or final.get("status") != "passed" or final.get("unresolved_count") != 0:
        errors.append({"code": "relation-final-not-passed"})
    if final.get("source_markdown_sha256") != source_markdown_sha256:
        errors.append({"code": "relation-source-digest-mismatch"})
    if final.get("relations") != relations:
        errors.append({"code": "relation-materialization-mismatch"})
    if mode == "llm-three-pass":
        for field in ("concepts", "atom_concept_links", "concept_relations"):
            if final.get(field) != manifest.get(field):
                errors.append({"code": "relation-materialization-mismatch", "field": field})
    categories = {
        str(node.get("key")): str(node.get("category"))
        for node in manifest.get("nodes", [])
        if isinstance(node, dict) and node.get("layer") == "atom"
    }
    role_field = "atom_roles" if mode == "llm-three-pass" else "concept_signatures"
    expected_featured = sorted(
        str(signature.get("atom_key"))
        for signature in final.get(role_field, [])
        if isinstance(signature, dict) and signature.get("role") == "bridge"
        and categories.get(str(signature.get("atom_key"))) == "worked-example"
    )
    featured = review.get("featured_example_keys", [])
    if not isinstance(featured, list) or featured != expected_featured or len(featured) != len(set(featured)):
        errors.append({"code": "relation-featured-examples-mismatch"})
    for name, binding in review.get("bindings", {}).items():
        if not isinstance(binding, dict):
            errors.append({"code": "relation-binding-invalid", "binding": name})
            continue
        path = Path(str(binding.get("path", ""))).expanduser().resolve()
        if not path.is_file():
            errors.append({"code": "relation-binding-missing", "binding": name, "path": str(path)})
            continue
        try:
            artifact = load_json(path)
        except Exception as exc:
            errors.append({"code": "relation-binding-invalid", "binding": name, "detail": str(exc)})
            continue
        if artifact.get("artifact_sha256") != artifact_digest(artifact) or binding.get("sha256") != artifact.get("artifact_sha256"):
            errors.append({"code": "relation-binding-digest-mismatch", "binding": name})
    return errors


def validate_graph(
    manifest_path: Path,
    book_root: Path,
    canvas_index_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.expanduser().resolve()
    book_root = book_root.expanduser().resolve()
    manifest = load_json(manifest_path)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    rendering_contract_enabled = False

    if manifest.get("schema_version") != 1:
        errors.append({"code": "manifest-schema-version"})
    profile_path = Path(str(manifest.get("profile", ""))).expanduser().resolve()
    if not profile_path.is_file():
        errors.append({"code": "profile-missing", "path": str(profile_path)})
        profile: dict[str, Any] = {}
    else:
        profile = load_json(profile_path)
        if profile.get("schema_version") != 1:
            errors.append({"code": "profile-schema-version"})
        configured_root = Path(str(profile.get("paths", {}).get("book_root", ""))).expanduser().resolve()
        if configured_root != book_root:
            errors.append({"code": "book-root-mismatch"})
        source_path = Path(str(profile.get("source", {}).get("path", ""))).expanduser().resolve()
        if not source_path.is_file() or sha256_file(source_path) != profile.get("source", {}).get("sha256"):
            errors.append({"code": "source-identity-mismatch"})
        if manifest.get("source_sha256") != profile.get("source", {}).get("sha256"):
            errors.append({"code": "manifest-source-identity-mismatch"})
        rendering = profile.get("markdown_rendering")
        if isinstance(rendering, dict):
            rendering_contract_enabled = all(
                rendering.get(field) == expected
                for field, expected in MARKDOWN_RENDERING_CONTRACT.items()
            )
            for field, expected in MARKDOWN_RENDERING_CONTRACT.items():
                if rendering.get(field) != expected:
                    errors.append({"code": "markdown-rendering-config-invalid", "field": field})
        elif profile.get("atomization", {}).get("mode") == "llm-two-pass":
            errors.append({"code": "markdown-rendering-config-missing"})
        relation_analysis = profile.get("relation_analysis")
        if relation_analysis is not None:
            if not isinstance(relation_analysis, dict):
                errors.append({"code": "relation-analysis-config-invalid"})
            else:
                mode = relation_analysis.get("mode")
                expected_contract = (
                    {"mode": "llm-two-pass", "mainline": "directed-acyclic-backbone", "cross_chapter": True}
                    if mode == "llm-two-pass" else
                    {"mode": "llm-three-pass", "graph_model": "atom-concept-dual-layer", "concept_scope": "book", "cross_chapter": True, "community_analysis": "wcc-required-leiden-optional"}
                )
                for field, expected in expected_contract.items():
                    if relation_analysis.get(field) != expected:
                        errors.append({"code": "relation-analysis-config-invalid", "field": field})
                for field in ("explicit_confidence_threshold", "inferred_confidence_threshold", *(('concept_merge_threshold',) if mode == 'llm-three-pass' else ())):
                    value = relation_analysis.get(field)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                        errors.append({"code": "relation-analysis-config-invalid", "field": field})
                if mode == "llm-three-pass":
                    retrieval = relation_analysis.get("candidate_retrieval")
                    if not isinstance(retrieval, dict):
                        errors.append({"code": "relation-analysis-config-invalid", "field": "candidate_retrieval"})
                    else:
                        for field in ("source_window", "lexical_top_k", "embedding_top_k", "graph_hops", "max_ranked_candidates_per_atom"):
                            if not isinstance(retrieval.get(field), int) or retrieval[field] < 0:
                                errors.append({"code": "relation-analysis-config-invalid", "field": f"candidate_retrieval.{field}"})
        canvas_config = profile.get("canvas")
        if isinstance(canvas_config, dict) and canvas_config.get("mode") is not None:
            mode = canvas_config.get("mode")
            expected_canvas = {
                "two-level-constellation": {
                    "mode": "two-level-constellation", "theme": "adaptive",
                    "overview_granularity": "chapter", "chapter_granularity": "atom",
                },
                "three-level-constellation": {
                    "mode": "three-level-constellation", "theme": "adaptive",
                    "overview_granularity": "chapter", "chapter_granularity": "core-atom",
                    "section_granularity": "atom-and-exercise-entry",
                },
            }.get(str(mode))
            if expected_canvas is None:
                errors.append({"code": "canvas-config-invalid", "field": "mode"})
                expected_canvas = {}
            for field, expected in expected_canvas.items():
                if canvas_config.get(field) != expected:
                    errors.append({"code": "canvas-config-invalid", "field": field})

    source_markdown = Path(str(manifest.get("source_markdown", ""))).expanduser().resolve()
    if not source_markdown.is_file():
        errors.append({"code": "source-markdown-missing", "path": str(source_markdown)})
        source_lines: list[str] = []
    else:
        if sha256_file(source_markdown) != manifest.get("source_markdown_sha256"):
            errors.append({"code": "source-markdown-identity-mismatch"})
        source_lines = source_markdown.read_text(encoding="utf-8-sig").splitlines()
    line_count = len(source_lines)

    review = manifest.get("review")
    if not isinstance(review, dict):
        errors.append({"code": "review-missing"})
    else:
        for field, expected in {
            "status": "passed",
            "reviewed_entire_book": True,
            "toc_hierarchy": "passed",
            "source_coverage": "passed",
            "atom_link_free": "passed",
        }.items():
            if review.get(field) != expected:
                errors.append({"code": "review-incomplete", "field": field})

    raw_nodes = manifest.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        errors.append({"code": "nodes-missing"})
        raw_nodes = []
    nodes: dict[str, dict[str, Any]] = {}
    filenames: set[str] = set()
    organizers: list[dict[str, Any]] = []
    atoms: list[dict[str, Any]] = []
    ranges: list[tuple[int, int, str]] = []

    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            errors.append({"code": "node-invalid", "index": index})
            continue
        key = node.get("key")
        layer = node.get("layer")
        if not isinstance(key, str) or not key or key in nodes:
            errors.append({"code": "node-key-invalid", "index": index})
            continue
        nodes[key] = node
        if layer not in LAYERS:
            errors.append({"code": "node-layer-invalid", "node": key})
            continue
        try:
            filename = normalize_relative_path(node.get("filename"), f"node {key}.filename")
            node["_filename"] = filename
            folded = filename.casefold()
            if folded in filenames:
                errors.append({"code": "node-filename-duplicate", "node": key})
            filenames.add(folded)
        except Exception as exc:
            errors.append({"code": "node-filename-invalid", "node": key, "detail": str(exc)})
            filename = ""
        if layer == "organizer":
            organizers.append(node)
            if not filename.startswith("组织层/"):
                errors.append({"code": "organizer-path-invalid", "node": key})
            if not isinstance(node.get("organizer_level"), int) or node["organizer_level"] < 1:
                errors.append({"code": "organizer-level-invalid", "node": key})
            children = node.get("children")
            if (
                not isinstance(children, list)
                or not children
                or not all(isinstance(child, str) and child for child in children)
                or len(children) != len(set(children))
            ):
                errors.append({"code": "organizer-children-invalid", "node": key})
                node["_children"] = []
            else:
                node["_children"] = children
            heading_ranges = node.get("heading_ranges", [])
            node["_heading_ranges"] = []
            if not isinstance(heading_ranges, list):
                errors.append({"code": "organizer-heading-ranges-invalid", "node": key})
            else:
                for range_index, value in enumerate(heading_ranges):
                    try:
                        start, end = parse_range(value, f"node {key}.heading_ranges[{range_index}]", line_count)
                        node["_heading_ranges"].append((start, end))
                        ranges.append((start, end, f"organizer:{key}"))
                    except Exception as exc:
                        errors.append({"code": "organizer-heading-range-invalid", "node": key, "detail": str(exc)})
        else:
            atoms.append(node)
            category = node.get("category")
            if category not in ATOM_CATEGORIES:
                errors.append({"code": "atom-category-invalid", "node": key})
            elif not filename.startswith(ATOM_CATEGORIES[category] + "/"):
                errors.append({"code": "atom-path-invalid", "node": key})
            elif rendering_contract_enabled:
                code = ATOM_CATEGORY_CODES[category]
                if re.fullmatch(rf"\d{{4,}}-{code}\.md", PurePosixPath(filename).name) is None:
                    errors.append({"code": "atom-filename-invalid", "node": key, "filename": filename})
            if "children" in node:
                errors.append({"code": "atom-has-children", "node": key})
            try:
                start, end = parse_range(node.get("source_range"), f"node {key}.source_range", line_count)
                node["_source_range"] = (start, end)
                ranges.append((start, end, f"atom:{key}"))
            except Exception as exc:
                errors.append({"code": "atom-source-range-invalid", "node": key, "detail": str(exc)})

    roots = [node for node in organizers if node.get("parent_key") is None]
    if len(roots) != 1 or roots[0].get("organizer_level") != 1:
        errors.append({"code": "root-organizer-invalid"})

    for key, node in nodes.items():
        parent_key = node.get("parent_key")
        if parent_key is None:
            if node not in roots:
                errors.append({"code": "unexpected-parentless-node", "node": key})
            continue
        parent = nodes.get(parent_key)
        if parent is None or parent.get("layer") != "organizer":
            errors.append({"code": "node-parent-invalid", "node": key})
            continue
        if key not in parent.get("_children", []):
            errors.append({"code": "parent-child-mismatch", "node": key})
        if node.get("layer") == "organizer" and node.get("organizer_level") != parent.get("organizer_level", 0) + 1:
            errors.append({"code": "organizer-level-discontinuity", "node": key})

    for organizer in organizers:
        key = str(organizer.get("key"))
        children = organizer.get("_children", [])
        for child_key in children:
            child = nodes.get(child_key)
            if child is None or child.get("parent_key") != key:
                errors.append({"code": "organizer-child-invalid", "node": key, "child": child_key})
        child_layers = {nodes[child].get("layer") for child in children if child in nodes}
        if "organizer" not in child_layers and child_layers != {"atom"}:
            errors.append({"code": "bottom-organizer-must-own-atoms", "node": key})
        if child_layers == {"organizer", "atom"}:
            warnings.append({"code": "mixed-organizer-and-atom-children", "node": key})
        if rendering_contract_enabled and child_layers == {"atom"} and organizer.get("parent_key") is not None:
            parent = nodes.get(str(organizer.get("parent_key")))
            if parent is not None and "_filename" in organizer and "_filename" in parent:
                actual_parent = PurePosixPath(str(organizer["_filename"])).parent
                expected_parent = PurePosixPath(str(parent["_filename"])).parent
                if actual_parent != expected_parent:
                    errors.append({"code": "leaf-organizer-not-flat", "node": key})

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            errors.append({"code": "ownership-cycle", "node": key})
            return
        if key in visited:
            return
        visiting.add(key)
        node = nodes[key]
        if node.get("layer") == "organizer":
            for child in node.get("_children", []):
                if child in nodes:
                    visit(child)
        visiting.remove(key)
        visited.add(key)

    if roots:
        visit(str(roots[0]["key"]))
    unreachable = sorted(set(nodes) - visited)
    if unreachable:
        errors.append({"code": "unreachable-nodes", "nodes": unreachable})

    source_start_cache: dict[str, int | None] = {}

    def first_source_line(key: str, trail: set[str] | None = None) -> int | None:
        if key in source_start_cache:
            return source_start_cache[key]
        current_trail = set() if trail is None else set(trail)
        if key in current_trail or key not in nodes:
            return None
        current_trail.add(key)
        node = nodes[key]
        candidates: list[int] = []
        if node.get("layer") == "atom" and "_source_range" in node:
            candidates.append(int(node["_source_range"][0]))
        if node.get("layer") == "organizer":
            candidates.extend(int(item[0]) for item in node.get("_heading_ranges", []))
            for child in node.get("_children", []):
                child_start = first_source_line(str(child), current_trail)
                if child_start is not None:
                    candidates.append(child_start)
        result = min(candidates) if candidates else None
        source_start_cache[key] = result
        return result

    for organizer in organizers:
        organizer_key = str(organizer.get("key"))
        children = [str(child) for child in organizer.get("_children", []) if str(child) in nodes]
        positions = {child: first_source_line(child) for child in children}
        if any(value is None for value in positions.values()):
            errors.append({"code": "organizer-child-source-anchor-missing", "node": organizer_key})
            continue
        expected_children = sorted(children, key=lambda child: (int(positions[child]), child))
        if children != expected_children:
            errors.append(
                {
                    "code": "organizer-child-source-order",
                    "node": organizer_key,
                    "expected": expected_children,
                    "actual": children,
                }
            )

    expected_order = [
        str(node["key"])
        for node in sorted(
            (node for node in atoms if "_source_range" in node),
            key=lambda item: (item["_source_range"][0], item["_source_range"][1], str(item["key"])),
        )
    ]
    if manifest.get("source_order") != expected_order:
        errors.append({"code": "source-order-invalid", "expected": expected_order})

    exclusions = manifest.get("excluded_ranges", [])
    if not isinstance(exclusions, list):
        errors.append({"code": "excluded-ranges-invalid"})
        exclusions = []
    for index, item in enumerate(exclusions):
        if not isinstance(item, dict) or not isinstance(item.get("reason"), str) or len(item["reason"].strip()) < 8:
            errors.append({"code": "excluded-range-reason-invalid", "index": index})
            continue
        try:
            start, end = parse_range([item.get("start"), item.get("end")], f"excluded_ranges[{index}]", line_count)
            ranges.append((start, end, f"excluded:{index}"))
        except Exception as exc:
            errors.append({"code": "excluded-range-invalid", "index": index, "detail": str(exc)})

    coverage: list[list[str]] = [[] for _ in range(line_count + 1)]
    for start, end, owner in ranges:
        for line_number in range(start, end + 1):
            coverage[line_number].append(owner)
    duplicate_lines = [index for index in range(1, line_count + 1) if len(coverage[index]) > 1]
    uncovered_lines = [index for index, line in enumerate(source_lines, start=1) if line.strip() and not coverage[index]]
    if duplicate_lines:
        errors.append({"code": "source-coverage-overlap", "lines": duplicate_lines[:50]})
    if uncovered_lines:
        errors.append({"code": "source-coverage-gap", "lines": uncovered_lines[:50]})

    for node in raw_nodes:
        if not isinstance(node, dict) or "_filename" not in node:
            continue
        key = str(node["key"])
        path = (book_root / node["_filename"]).resolve()
        try:
            path.relative_to(book_root)
        except ValueError:
            errors.append({"code": "node-path-outside-book", "node": key})
            continue
        if not path.is_file():
            errors.append({"code": "node-file-missing", "node": key, "path": str(path)})
            continue
        text = path.read_text(encoding="utf-8-sig")
        body_lines = strip_frontmatter(text)
        if node.get("layer") == "atom":
            if rendering_contract_enabled and any(ANY_MARKDOWN_HEADING_RE.match(line.strip()) for line in body_lines):
                errors.append({"code": "atom-heading-forbidden", "node": key})
            if WIKILINK_RE.search(text) or MARKDOWN_LINK_RE.search(text) or HTML_ANCHOR_RE.search(text):
                errors.append({"code": "atom-has-outgoing-link", "node": key})
            for match in MARKDOWN_EMBED_RE.finditer(text):
                if is_markdown_note_embed(match.group(1)):
                    errors.append({"code": "atom-has-outgoing-note-embed", "node": key})
                    break
        else:
            nonblank = [(index, line.strip()) for index, line in enumerate(body_lines, start=1) if line.strip()]
            links: list[Path] = []
            if rendering_contract_enabled:
                content = nonblank
                cursor = 0
                for child_key in node.get("_children", []):
                    child = nodes.get(child_key)
                    if child is None:
                        continue
                    if child.get("layer") == "organizer":
                        if cursor >= len(content):
                            errors.append({"code": "organizer-child-heading-missing", "node": key, "child": child_key})
                            continue
                        line_number, line = content[cursor]
                        root_level = int(roots[0].get("organizer_level", 1)) if roots else 1
                        depth = min(max(int(child.get("organizer_level", root_level + 1)) - root_level, 1), 6)
                        expected_heading = f"{'#' * depth} {child.get('title')}"
                        if line != expected_heading:
                            errors.append({"code": "organizer-child-heading-invalid", "node": key, "child": child_key, "line": line_number})
                        cursor += 1
                    if cursor >= len(content):
                        errors.append({"code": "organizer-child-link-missing", "node": key, "child": child_key})
                        continue
                    line_number, line = content[cursor]
                    match = ORGANIZER_LINK_RE.match(line)
                    if match is None or not is_markdown_note_embed(match.group(2)):
                        errors.append({"code": "organizer-child-link-invalid", "node": key, "child": child_key, "line": line_number})
                    else:
                        links.append(resolve_link(match.group(2), path, book_root))
                    cursor += 1
                if cursor != len(content):
                    errors.append({"code": "organizer-contains-extra-body", "node": key})
            else:
                if not nonblank or not HEADING_RE.match(nonblank[0][1]):
                    errors.append({"code": "organizer-heading-missing", "node": key})
                    continue
                content = nonblank[1:]
                for line_number, line in content:
                    match = ORGANIZER_LINK_RE.match(line)
                    if match is None or not is_markdown_note_embed(match.group(2)):
                        errors.append({"code": "organizer-contains-nonlink-body", "node": key, "line": line_number})
                        continue
                    links.append(resolve_link(match.group(2), path, book_root))
            expected_paths = [
                (book_root / nodes[child]["_filename"]).resolve()
                for child in node.get("_children", [])
                if child in nodes and "_filename" in nodes[child]
            ]
            if links != expected_paths:
                errors.append({"code": "organizer-link-order-or-coverage", "node": key, "expected": [str(item) for item in expected_paths], "actual": [str(item) for item in links]})

    relations = manifest.get("relations", [])
    if not isinstance(relations, list):
        errors.append({"code": "relations-invalid"})
        relations = []
    relation_keys: set[str] = set()
    new_relation_schema = any(isinstance(item, dict) and "type" in item for item in relations)
    relation_config = profile.get("relation_analysis") if isinstance(profile.get("relation_analysis"), dict) else {
        "explicit_confidence_threshold": 0.90,
        "inferred_confidence_threshold": 0.95,
    }
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            errors.append({"code": "relation-invalid", "index": index})
            continue
        key = relation.get("key")
        if not isinstance(key, str) or not key or key in relation_keys:
            errors.append({"code": "relation-key-invalid", "index": index})
        else:
            relation_keys.add(key)
        from_key, to_key = relation.get("from_key"), relation.get("to_key")
        if from_key not in nodes or to_key not in nodes:
            errors.append({"code": "relation-endpoint-invalid", "relation": key})
            continue
        if nodes[str(from_key)].get("layer") != "atom" or nodes[str(to_key)].get("layer") != "atom" or from_key == to_key:
            errors.append({"code": "relation-endpoint-invalid", "relation": key})
        if "type" not in relation:
            evidence = relation.get("evidence")
            if not isinstance(evidence, str) or len(evidence.strip()) < 12:
                errors.append({"code": "relation-evidence-invalid", "relation": key})
            continue
        relation_type = relation.get("type")
        tier = relation.get("tier")
        evidence_kind = relation.get("evidence_kind")
        if relation_type not in RELATION_LABELS or tier not in {"backbone", "supporting"} or evidence_kind not in {"explicit", "pedagogical-inference"}:
            errors.append({"code": "relation-classification-invalid", "relation": key})
        if relation_type in SYMMETRIC_RELATIONS and str(from_key) > str(to_key):
            errors.append({"code": "relation-symmetric-order-invalid", "relation": key})
        if tier == "backbone" and (
            relation_type not in {"prerequisite", "develops", "derives", "motivates"}
            or nodes[str(from_key)].get("category") not in {"knowledge", "scenario"}
            or nodes[str(to_key)].get("category") not in {"knowledge", "scenario"}
        ):
            errors.append({"code": "relation-backbone-invalid", "relation": key})
        rationale = relation.get("rationale")
        if not isinstance(rationale, str) or len(rationale.strip()) < 12:
            errors.append({"code": "relation-rationale-invalid", "relation": key})
        confidence = relation.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            errors.append({"code": "relation-confidence-invalid", "relation": key})
        else:
            threshold_field = "explicit_confidence_threshold" if evidence_kind == "explicit" else "inferred_confidence_threshold"
            threshold = float(relation_config.get(threshold_field, 0.90 if evidence_kind == "explicit" else 0.95))
            if float(confidence) < threshold:
                errors.append({"code": "relation-confidence-below-threshold", "relation": key})
        evidence_ranges = relation.get("evidence_ranges")
        covered: set[str] = set()
        if not isinstance(evidence_ranges, list) or not evidence_ranges:
            errors.append({"code": "relation-evidence-invalid", "relation": key})
            evidence_ranges = []
        for item in evidence_ranges:
            if not isinstance(item, dict) or item.get("node_key") not in {from_key, to_key}:
                errors.append({"code": "relation-evidence-invalid", "relation": key})
                continue
            node_key = str(item["node_key"])
            source_range = item.get("source_range")
            atom_range = nodes[node_key].get("source_range")
            if (
                not isinstance(source_range, list) or len(source_range) != 2
                or not all(isinstance(value, int) for value in source_range)
                or not isinstance(atom_range, list) or len(atom_range) != 2
                or source_range[0] < atom_range[0] or source_range[1] > atom_range[1]
                or source_range[0] > source_range[1]
            ):
                errors.append({"code": "relation-evidence-outside-atom", "relation": key, "node": node_key})
            else:
                covered.add(node_key)
        if evidence_kind == "pedagogical-inference" and covered != {str(from_key), str(to_key)}:
            errors.append({"code": "relation-inference-needs-both-endpoints", "relation": key})

    if new_relation_schema and not isinstance(manifest.get("relation_review"), dict):
        errors.append({"code": "relation-review-missing-for-semantic-relations"})
    elif not relations and isinstance(profile.get("relation_analysis"), dict) and not isinstance(manifest.get("relation_review"), dict):
        warnings.append({"code": "relation-review-pending"})

    if isinstance(manifest.get("relation_review"), dict) and manifest["relation_review"].get("mode") == "llm-three-pass":
        errors.extend(validate_dual_layer_graph(manifest, nodes, relation_config))

    errors.extend(
        validate_organizer_review(
            manifest,
            manifest.get("source_markdown_sha256"),
            set(nodes),
        )
    )

    errors.extend(
        validate_atomization_review(
            profile,
            manifest,
            manifest.get("source_markdown_sha256"),
            atoms,
        )
    )

    errors.extend(
        validate_relation_review(
            manifest,
            manifest.get("source_markdown_sha256"),
            [item for item in relations if isinstance(item, dict)],
        )
    )

    if canvas_index_path is not None and not errors:
        errors.extend(
            validate_constellation_bundle(
                canvas_index_path,
                manifest_path,
                book_root,
                nodes,
                organizers,
                atoms,
                [item for item in relations if isinstance(item, dict)],
                manifest.get("relation_review"),
                [item for item in manifest.get("concepts", []) if isinstance(item, dict)],
                [item for item in manifest.get("atom_concept_links", []) if isinstance(item, dict)],
                [item for item in manifest.get("concept_relations", []) if isinstance(item, dict)],
            )
        )

    for node in raw_nodes:
        if isinstance(node, dict):
            node.pop("_filename", None)
            node.pop("_source_range", None)
            node.pop("_children", None)
            node.pop("_heading_ranges", None)
    counts = {
        "nodes": len(nodes),
        "organizers": len(organizers),
        "atoms": len(atoms),
        "atom_categories": {
            category: sum(node.get("category") == category for node in atoms)
            for category in ATOM_CATEGORIES
        },
        "relations": len(relations),
        "source_lines": line_count,
        "covered_nonblank_lines": sum(bool(line.strip()) and bool(coverage[index]) for index, line in enumerate(source_lines, start=1)),
    }
    return {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "manifest": str(manifest_path),
        "book_root": str(book_root),
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--book-root", type=Path, required=True)
    parser.add_argument("--canvas-index", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = validate_graph(args.manifest, args.book_root, args.canvas_index)
    except Exception as exc:
        report = {
            "schema_version": 1,
            "status": "failed",
            "errors": [{"code": "validator-exception", "detail": f"{type(exc).__name__}: {exc}"}],
            "warnings": [],
            "counts": {},
        }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
