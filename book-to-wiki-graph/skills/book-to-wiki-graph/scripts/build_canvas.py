#!/usr/bin/env python3
"""Build organization-first Obsidian Canvas files from a validated book graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any, Iterable

from validate_book_graph import load_json, validate_graph


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
CARD_WIDTH = 300
CARD_HEIGHT = 92
COLUMN_GAP = 420
ROW_GAP = 74
GROUP_PADDING_X = 54
GROUP_PADDING_Y = 48


def stable_id(kind: str, key: str) -> str:
    return hashlib.sha256(f"{kind}:{key}".encode("utf-8")).hexdigest()[:16]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encode_href(value: str) -> str:
    return urllib.parse.quote(value.replace("\\", "/"), safe="/._-~")


def escape_label(value: str) -> str:
    return value.replace("[", "&#91;").replace("]", "&#93;")


def safe_filename(value: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "-", normalized)
    normalized = re.sub(r"\s+", "-", normalized).strip(". -")
    return (normalized or fallback)[:80].rstrip(". -") or fallback


def atomic_json(path: Path, payload: dict[str, Any], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite explicitly: {path}")
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


def descendants(nodes: dict[str, dict[str, Any]], root_key: str) -> list[str]:
    ordered: list[str] = []

    def visit(key: str) -> None:
        ordered.append(key)
        node = nodes[key]
        if node.get("layer") == "organizer":
            for child in node.get("children", []):
                visit(str(child))

    visit(root_key)
    return ordered


def node_source_start(
    nodes: dict[str, dict[str, Any]], key: str, memo: dict[str, int]
) -> int:
    if key in memo:
        return memo[key]
    node = nodes[key]
    candidates: list[int] = []
    if node.get("layer") == "atom":
        candidates.append(int(node["source_range"][0]))
    else:
        candidates.extend(int(item[0]) for item in node.get("heading_ranges", []))
        candidates.extend(
            node_source_start(nodes, str(child), memo)
            for child in node.get("children", [])
        )
    if not candidates:
        raise ValueError(f"Node has no source anchor: {key}")
    memo[key] = min(candidates)
    return memo[key]


class TreeLayout:
    """Place a visible ownership tree left-to-right and in source order top-to-bottom."""

    def __init__(
        self,
        nodes: dict[str, dict[str, Any]],
        root_key: str,
        visible_keys: Iterable[str],
    ) -> None:
        self.nodes = nodes
        self.root_key = root_key
        self.visible = set(visible_keys)
        if root_key not in self.visible:
            raise ValueError("Layout root must be visible")
        self.positions: dict[str, tuple[int, int]] = {}
        self._row = 0

    def visible_children(self, key: str) -> list[str]:
        node = self.nodes[key]
        if node.get("layer") != "organizer":
            return []
        return [str(child) for child in node.get("children", []) if str(child) in self.visible]

    def place(self, key: str, depth: int) -> int:
        children = self.visible_children(key)
        child_y = [self.place(child, depth + 1) for child in children]
        if child_y:
            y = (child_y[0] + child_y[-1]) // 2
        else:
            y = self._row * (CARD_HEIGHT + ROW_GAP)
            self._row += 1
        self.positions[key] = (depth * COLUMN_GAP, y)
        return y

    def build(self) -> dict[str, tuple[int, int]]:
        self.place(self.root_key, 0)
        return self.positions


class CanvasBundleBuilder:
    def __init__(
        self,
        manifest: dict[str, Any],
        manifest_path: Path,
        book_root: Path,
        output_dir: Path,
    ) -> None:
        self.manifest = manifest
        self.manifest_path = manifest_path
        self.book_root = book_root
        self.output_dir = output_dir
        self.nodes = {
            str(node["key"]): node
            for node in manifest["nodes"]
            if isinstance(node, dict) and isinstance(node.get("key"), str)
        }
        roots = [node for node in self.nodes.values() if node.get("parent_key") is None]
        if len(roots) != 1:
            raise ValueError("Canvas bundle needs exactly one root organizer")
        self.root_key = str(roots[0]["key"])
        self.source_starts: dict[str, int] = {}
        for key in self.nodes:
            node_source_start(self.nodes, key, self.source_starts)
        root_children = [str(key) for key in self.nodes[self.root_key].get("children", [])]
        direct_atoms = [key for key in root_children if self.nodes[key].get("layer") == "atom"]
        if direct_atoms:
            raise ValueError(
                "Canvas bundle requires every atom to belong to a top-level organizer; "
                f"root owns atoms directly: {direct_atoms}"
            )
        self.chapter_keys = [
            key for key in root_children if self.nodes[key].get("layer") == "organizer"
        ]
        if not self.chapter_keys:
            raise ValueError("Canvas bundle needs at least one top-level organizer")
        self.chapter_paths = self._chapter_paths()

    def _chapter_paths(self) -> dict[str, Path]:
        width = max(2, len(str(len(self.chapter_keys))))
        result: dict[str, Path] = {}
        for index, key in enumerate(self.chapter_keys, start=1):
            title = safe_filename(str(self.nodes[key]["title"]), "section")
            suffix = stable_id("chapter", key)[:6]
            result[key] = self.output_dir / "chapters" / f"{index:0{width}d}-{title}-{suffix}.canvas"
        return result

    def link_text(self, label: str, target: Path, canvas_path: Path) -> str:
        href = os.path.relpath(target.resolve(), canvas_path.parent).replace("\\", "/")
        return f"[{escape_label(label)}]({encode_href(href)})"

    def note_target(self, key: str) -> Path:
        return (self.book_root / str(self.nodes[key]["filename"])).resolve()

    def card(
        self,
        key: str,
        canvas_path: Path,
        position: tuple[int, int],
        target: Path | None = None,
    ) -> dict[str, Any]:
        node = self.nodes[key]
        label = str(node["title"])
        color = ORGANIZER_COLOR
        if node.get("layer") == "atom":
            category = str(node["category"])
            label = f"{ATOM_LABELS[category]} · {label}"
            color = ATOM_COLORS[category]
        return {
            "id": stable_id("card", key),
            "type": "text",
            "text": self.link_text(label, target or self.note_target(key), canvas_path),
            "x": position[0],
            "y": position[1],
            "width": CARD_WIDTH,
            "height": CARD_HEIGHT,
            "color": color,
        }

    def ownership_edge(self, parent: str, child: str) -> dict[str, Any]:
        return {
            "id": stable_id("edge", f"ownership:{parent}:{child}"),
            "fromNode": stable_id("card", parent),
            "toNode": stable_id("card", child),
            "fromSide": "right",
            "toSide": "left",
        }

    def group(
        self,
        key: str,
        member_keys: Iterable[str],
        positions: dict[str, tuple[int, int]],
        scope: str,
    ) -> dict[str, Any]:
        members = list(member_keys)
        min_x = min(positions[item][0] for item in members)
        min_y = min(positions[item][1] for item in members)
        max_x = max(positions[item][0] + CARD_WIDTH for item in members)
        max_y = max(positions[item][1] + CARD_HEIGHT for item in members)
        return {
            "id": stable_id("group", f"{scope}:{key}"),
            "type": "group",
            "label": str(self.nodes[key]["title"]),
            "x": min_x - GROUP_PADDING_X,
            "y": min_y - GROUP_PADDING_Y,
            "width": max_x - min_x + GROUP_PADDING_X * 2,
            "height": max_y - min_y + GROUP_PADDING_Y * 2,
        }

    def organization_canvas(
        self,
        canvas_path: Path,
        root_key: str,
        visible_keys: list[str],
        group_roots: list[str],
        overview: bool,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        layout = TreeLayout(self.nodes, root_key, visible_keys)
        positions = layout.build()
        visible = set(visible_keys)
        groups: list[dict[str, Any]] = []
        for group_root in group_roots:
            members = [key for key in descendants(self.nodes, group_root) if key in visible]
            groups.append(self.group(group_root, members, positions, "overview" if overview else root_key))

        cards: list[dict[str, Any]] = []
        for key in visible_keys:
            target = self.note_target(key)
            if overview and key in self.chapter_paths:
                target = self.chapter_paths[key]
            cards.append(self.card(key, canvas_path, positions[key], target))

        edges: list[dict[str, Any]] = []
        for parent in visible_keys:
            for child in self.nodes[parent].get("children", []):
                child_key = str(child)
                if child_key in visible:
                    edges.append(self.ownership_edge(parent, child_key))

        canvas = {"nodes": [*groups, *cards], "edges": edges}
        counts = {
            "cards": len(cards),
            "groups": len(groups),
            "edges": len(edges),
            "ownership_edges": len(edges),
            "relation_edges": 0,
            "organizers": sum(self.nodes[key].get("layer") == "organizer" for key in visible_keys),
            "atoms": sum(self.nodes[key].get("layer") == "atom" for key in visible_keys),
        }
        return canvas, counts

    def semantic_canvas(self, canvas_path: Path) -> tuple[dict[str, Any], dict[str, int]]:
        relations = list(self.manifest.get("relations", []))
        participant_keys = {
            str(relation[field])
            for relation in relations
            for field in ("from_key", "to_key")
        }
        ordered = sorted(participant_keys, key=lambda key: (self.source_starts[key], str(key)))
        positions: dict[str, tuple[int, int]] = {}
        for row, key in enumerate(ordered):
            node = self.nodes[key]
            depth = int(node.get("organizer_level", 0))
            if node.get("layer") == "atom":
                parent = self.nodes[str(node["parent_key"])]
                depth = int(parent.get("organizer_level", 0)) + 1
            positions[key] = (depth * COLUMN_GAP, row * (CARD_HEIGHT + ROW_GAP))
        cards = [self.card(key, canvas_path, positions[key]) for key in ordered]
        edges: list[dict[str, Any]] = []
        for relation in relations:
            edge: dict[str, Any] = {
                "id": stable_id("edge", f"relation:{relation['key']}"),
                "fromNode": stable_id("card", str(relation["from_key"])),
                "toNode": stable_id("card", str(relation["to_key"])),
                "fromSide": "right",
                "toSide": "left",
            }
            label = relation.get("label")
            if isinstance(label, str) and label.strip():
                edge["label"] = label.strip()
            if relation.get("color") in {"1", "2", "3", "4", "5", "6"}:
                edge["color"] = relation["color"]
            edges.append(edge)
        canvas = {"nodes": cards, "edges": edges}
        counts = {
            "cards": len(cards),
            "groups": 0,
            "edges": len(edges),
            "ownership_edges": 0,
            "relation_edges": len(edges),
            "organizers": sum(self.nodes[key].get("layer") == "organizer" for key in ordered),
            "atoms": sum(self.nodes[key].get("layer") == "atom" for key in ordered),
        }
        return canvas, counts

    def build(self) -> tuple[dict[Path, dict[str, Any]], dict[str, Any]]:
        payloads: dict[Path, dict[str, Any]] = {}
        organizer_keys = [
            key for key, node in self.nodes.items() if node.get("layer") == "organizer"
        ]
        organizer_keys.sort(
            key=lambda key: (
                self.source_starts[key],
                int(self.nodes[key]["organizer_level"]),
                key,
            )
        )
        overview_path = self.output_dir / "overview.canvas"
        overview, overview_counts = self.organization_canvas(
            overview_path,
            self.root_key,
            organizer_keys,
            self.chapter_keys,
            overview=True,
        )
        payloads[overview_path] = overview

        chapter_entries: list[dict[str, Any]] = []
        for chapter_key in self.chapter_keys:
            chapter_path = self.chapter_paths[chapter_key]
            visible = descendants(self.nodes, chapter_key)
            group_roots = [
                str(child)
                for child in self.nodes[chapter_key].get("children", [])
                if self.nodes[str(child)].get("layer") == "organizer"
            ]
            canvas, counts = self.organization_canvas(
                chapter_path,
                chapter_key,
                visible,
                group_roots,
                overview=False,
            )
            payloads[chapter_path] = canvas
            chapter_entries.append(
                {
                    "role": "chapter",
                    "root_key": chapter_key,
                    "path": chapter_path.relative_to(self.output_dir).as_posix(),
                    "counts": counts,
                }
            )

        semantic_entry: dict[str, Any] | None = None
        if self.manifest.get("relations"):
            semantic_path = self.output_dir / "semantics.canvas"
            semantic, counts = self.semantic_canvas(semantic_path)
            payloads[semantic_path] = semantic
            semantic_entry = {
                "role": "semantics",
                "path": semantic_path.relative_to(self.output_dir).as_posix(),
                "counts": counts,
            }

        index = {
            "schema_version": 1,
            "manifest": str(self.manifest_path),
            "manifest_sha256": sha256_file(self.manifest_path),
            "book_root": str(self.book_root),
            "layout": {
                "hierarchy_direction": "left-to-right",
                "sibling_order": "source-top-to-bottom",
                "atom_grouping": "none",
            },
            "overview": {
                "role": "overview",
                "root_key": self.root_key,
                "path": overview_path.relative_to(self.output_dir).as_posix(),
                "counts": overview_counts,
            },
            "chapters": chapter_entries,
            "semantics": semantic_entry,
        }
        return payloads, index


def build_canvas_bundle(
    manifest_path: Path,
    output_dir: Path,
    book_root: Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    manifest_path = manifest_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    book_root = book_root.expanduser().resolve()
    validation = validate_graph(manifest_path, book_root)
    if validation["status"] != "passed":
        raise ValueError(
            "Book graph must pass before Canvas build: "
            + json.dumps(validation["errors"][:5], ensure_ascii=False)
        )
    manifest = load_json(manifest_path)
    builder = CanvasBundleBuilder(manifest, manifest_path, book_root, output_dir)
    payloads, index = builder.build()
    index_path = output_dir / "canvas-index.json"
    planned = [*payloads, index_path]
    if not overwrite:
        existing = [str(path) for path in planned if path.exists()]
        if existing:
            raise FileExistsError(
                "Canvas bundle output exists; pass --overwrite explicitly: "
                + ", ".join(existing)
            )
    for path, payload in payloads.items():
        atomic_json(path, payload, overwrite=True)
    atomic_json(index_path, index, overwrite=True)
    return {
        "status": "passed",
        "canvas_index": str(index_path),
        "canvases": len(payloads),
        "overview": str(output_dir / index["overview"]["path"]),
        "chapters": len(index["chapters"]),
        "semantics": index["semantics"] is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--book-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report = build_canvas_bundle(
            args.manifest,
            args.output_dir,
            args.book_root,
            overwrite=args.overwrite,
        )
        code = 0
    except Exception as exc:
        report = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        code = 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
