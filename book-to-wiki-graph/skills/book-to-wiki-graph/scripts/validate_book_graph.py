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
from pathlib import Path
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
ORGANIZER_COLOR = "1"
LAYERS = {"organizer", "atom"}
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
ORGANIZER_LINK_RE = re.compile(
    r"^!\[([^\]]+)\]\(((?:[^()]|\([^()]*\))*)\)\s*$"
)
MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)"
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
            if len(links) != 1:
                errors.append({"code": "canvas-card-link-invalid", "path": str(canvas_path), "node": node.get("id")})
                continue
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
            if WIKILINK_RE.search(text) or MARKDOWN_LINK_RE.search(text) or HTML_ANCHOR_RE.search(text):
                errors.append({"code": "atom-has-outgoing-link", "node": key})
            for match in MARKDOWN_EMBED_RE.finditer(text):
                if is_markdown_note_embed(match.group(1)):
                    errors.append({"code": "atom-has-outgoing-note-embed", "node": key})
                    break
        else:
            nonblank = [(index, line.strip()) for index, line in enumerate(body_lines, start=1) if line.strip()]
            if not nonblank or not HEADING_RE.match(nonblank[0][1]):
                errors.append({"code": "organizer-heading-missing", "node": key})
                continue
            links: list[Path] = []
            for line_number, line in nonblank[1:]:
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
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            errors.append({"code": "relation-invalid", "index": index})
            continue
        key = relation.get("key")
        if not isinstance(key, str) or not key or key in relation_keys:
            errors.append({"code": "relation-key-invalid", "index": index})
        else:
            relation_keys.add(key)
        if relation.get("from_key") not in nodes or relation.get("to_key") not in nodes:
            errors.append({"code": "relation-endpoint-invalid", "relation": key})
        evidence = relation.get("evidence")
        if not isinstance(evidence, str) or len(evidence.strip()) < 12:
            errors.append({"code": "relation-evidence-invalid", "relation": key})

    if canvas_index_path is not None and not errors:
        errors.extend(
            validate_canvas_bundle(
                canvas_index_path,
                manifest_path,
                book_root,
                nodes,
                organizers,
                atoms,
                [item for item in relations if isinstance(item, dict)],
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
