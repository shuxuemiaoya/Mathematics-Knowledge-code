from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .common import adapter_output_policy, ConfigurationError, load_json, load_profile, require_reviewed_adapter, write_json_atomic


def stable_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def link_text(title: str, note: Path, vault_root: Path) -> str:
    try:
        relative = note.resolve().relative_to(vault_root.resolve()).as_posix()
    except ValueError as exc:
        raise ConfigurationError(f"Canvas note is outside vault root: {note}") from exc
    return f"[{title}]({quote(relative, safe='/%._-~')})"


def build_canvas(
    profile_path: Path,
    hierarchy_manifest_path: Path,
    content_manifest_path: Path,
    graph_manifest_path: Path,
    canvas_path: Path,
    overwrite: bool,
) -> dict[str, Any]:
    profile = load_profile(profile_path)
    if profile.get("canvas", {}).get("enabled") is not True:
        raise ConfigurationError("Canvas is disabled in the profile")
    adapter = require_reviewed_adapter(
        profile, Path(profile["format"]["adapter"])
    )
    if not adapter_output_policy(adapter)["generate_canvas"]:
        raise ConfigurationError("Canvas is disabled by the reviewed adapter")
    hierarchy = load_json(hierarchy_manifest_path)
    content = load_json(content_manifest_path)
    if hierarchy.get("status") != "passed" or content.get("status") != "passed":
        raise ConfigurationError("Hierarchy and content manifests must pass before Canvas")
    vault_root = Path(profile["paths"]["vault_root"])
    graph_root = Path(profile["paths"]["graph_root"])
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    key_to_id: dict[str, str] = {}
    ordered_entries = hierarchy.get("entries", [])
    row_by_level: dict[int, int] = {}
    for entry in ordered_entries:
        key = f"hierarchy:{entry['key']}"
        node_id = stable_id(key)
        key_to_id[entry["key"]] = node_id
        level = int(entry["level"])
        row = row_by_level.get(level, 0)
        row_by_level[level] = row + 1
        note = graph_root / entry["output"]
        if level == 1:
            nodes.append({"id": node_id, "type": "group", "label": entry["title"], "role": entry.get("role", "hierarchy"), "x": row * 1900, "y": 0, "width": 1700, "height": 1500})
        else:
            nodes.append({"id": node_id, "type": "text", "text": link_text(entry["title"], note, vault_root), "role": entry.get("role", "hierarchy"), "x": row * 340, "y": level * 220, "width": 300, "height": 90})
        parent = entry.get("parent")
        if parent and parent in key_to_id:
            edges.append({"id": stable_id(f"edge:{parent}:{entry['key']}"), "fromNode": key_to_id[parent], "toNode": node_id})

    functional = content.get("functional_nodes", [])
    question_ids = {question["id"] for question in content.get("questions", [])}
    role_color = str(profile.get("canvas", {}).get("question_type_color", "6"))
    for index, node in enumerate(functional):
        key = node["key"]
        node_id = stable_id(f"functional:{key}")
        key_to_id[key] = node_id
        canvas_node: dict[str, Any] = {
            "id": node_id,
            "type": "text",
            "text": link_text(node["title"], Path(node["output"]), vault_root),
            "x": (index % 6) * 340,
            "y": 850 + (index // 6) * 150,
            "width": 300,
            "height": 90,
            "role": node.get("role", "neutral-context"),
        }
        if node.get("role") in {"question-type", "subtype"}:
            canvas_node["color"] = role_color
        nodes.append(canvas_node)
        parent = node.get("parent") or node.get("source_note_key")
        if parent in key_to_id:
            edges.append({"id": stable_id(f"edge:{parent}:{key}"), "fromNode": key_to_id[parent], "toNode": node_id})

    if any(key in question_ids for key in key_to_id):
        raise ConfigurationError("Atomic question leaked into Canvas node keys")
    graph_manifest = {
        "schema_version": 1,
        "stage": "question-type-canvas",
        "status": "passed",
        "profile": profile["_profile_path"],
        "knowledge_linking": "deferred",
        "atomic_questions_included": False,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
    if (graph_manifest_path.exists() or canvas_path.exists()) and not overwrite:
        raise ConfigurationError("Canvas output exists; explicit --overwrite required")
    write_json_atomic(graph_manifest_path, graph_manifest, overwrite=overwrite)
    canvas_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(canvas_path, {"nodes": nodes, "edges": edges}, overwrite=overwrite)
    return graph_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a structural Question Type Graph Canvas.")
    parser.add_argument("profile", type=Path)
    parser.add_argument("hierarchy_manifest", type=Path)
    parser.add_argument("content_manifest", type=Path)
    parser.add_argument("graph_manifest", type=Path)
    parser.add_argument("canvas", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_canvas(args.profile, args.hierarchy_manifest, args.content_manifest, args.graph_manifest, args.canvas, args.overwrite)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "stage": "question-type-canvas", "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
