#!/usr/bin/env python3
"""Conservatively add nodes/edges to an Obsidian Canvas without reflowing it.

Input additions are JSON with `nodes` and `edges`.  Existing nodes, coordinates,
dimensions, colors, and edges are never removed or moved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]}"


def overlaps(left: Dict[str, Any], right: Dict[str, Any], gap: int = 20) -> bool:
    return not (
        left["x"] + left["width"] + gap <= right["x"]
        or right["x"] + right["width"] + gap <= left["x"]
        or left["y"] + left["height"] + gap <= right["y"]
        or right["y"] + right["height"] + gap <= left["y"]
    )


def place_node(
    nodes: list[Dict[str, Any]],
    parent: Optional[Dict[str, Any]],
    width: int,
    height: int,
    horizontal_gap: int,
    vertical_gap: int,
) -> tuple[int, int]:
    if parent:
        x = int(parent.get("x", 0)) + int(parent.get("width", 400)) + horizontal_gap
        y = int(parent.get("y", 0))
    elif nodes:
        x = max(int(node.get("x", 0)) + int(node.get("width", 400)) for node in nodes) + horizontal_gap
        y = min(int(node.get("y", 0)) for node in nodes)
    else:
        x = y = 0
    candidate = {"x": x, "y": y, "width": width, "height": height}
    for _ in range(max(1000, len(nodes) * 4)):
        collision = next((node for node in nodes if overlaps(candidate, node)), None)
        if not collision:
            return candidate["x"], candidate["y"]
        candidate["y"] = int(collision.get("y", 0)) + int(collision.get("height", height)) + vertical_gap
    raise RuntimeError("无法在局部列中找到无重叠位置")


def update_canvas(
    canvas: Dict[str, Any],
    additions: Dict[str, Any],
    sidecar: Optional[Dict[str, Any]] = None,
    horizontal_gap: int = 220,
    vertical_gap: int = 80,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    sidecar = dict(sidecar or {})
    sidecar.setdefault("version", 1)
    sidecar.setdefault("nodes", {})
    nodes = list(canvas.get("nodes", []))
    edges = list(canvas.get("edges", []))
    by_id = {node.get("id"): node for node in nodes if node.get("id")}
    key_to_id: Dict[str, str] = dict(sidecar["nodes"])
    for node in nodes:
        if node.get("type") == "file" and isinstance(node.get("file"), str):
            key_to_id.setdefault(node["file"].removesuffix(".md"), node["id"])

    added_nodes: list[Dict[str, Any]] = []
    for spec in additions.get("nodes", []):
        key = spec.get("key") or spec.get("file")
        if not isinstance(key, str):
            raise ValueError("每个 Canvas node addition 必须包含 key 或 file")
        existing_id = key_to_id.get(key)
        if existing_id and existing_id in by_id:
            continue
        node_id = stable_id("mmn", key)
        if node_id in by_id:
            key_to_id[key] = node_id
            continue
        width = int(spec.get("width", 400))
        height = int(spec.get("height", 240))
        parent_id = key_to_id.get(spec.get("parent_key"))
        parent = by_id.get(parent_id)
        x, y = place_node(nodes, parent, width, height, horizontal_gap, vertical_gap)
        node: Dict[str, Any] = {
            "id": node_id,
            "type": "file" if spec.get("file") else "text",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
        if spec.get("file"):
            node["file"] = spec["file"]
        else:
            node["text"] = str(spec.get("text", key))
        if spec.get("color") is not None:
            node["color"] = str(spec["color"])
        nodes.append(node)
        by_id[node_id] = node
        key_to_id[key] = node_id
        added_nodes.append({"key": key, "id": node_id, "x": x, "y": y})

    existing_edge_keys = {
        (edge.get("fromNode"), edge.get("toNode"), edge.get("label")) for edge in edges
    }
    added_edges: list[Dict[str, Any]] = []
    for spec in additions.get("edges", []):
        from_id = key_to_id.get(spec.get("from_key"))
        to_id = key_to_id.get(spec.get("to_key"))
        if not from_id or not to_id:
            raise ValueError(f"Canvas edge 引用了未知节点: {spec}")
        label = spec.get("label")
        edge_key = (from_id, to_id, label)
        if edge_key in existing_edge_keys:
            continue
        edge: Dict[str, Any] = {
            "id": stable_id("mme", f"{from_id}:{to_id}:{label or ''}"),
            "fromNode": from_id,
            "fromSide": spec.get("from_side", "right"),
            "toNode": to_id,
            "toSide": spec.get("to_side", "left"),
        }
        if label:
            edge["label"] = label
        edges.append(edge)
        existing_edge_keys.add(edge_key)
        added_edges.append(edge)

    updated = dict(canvas)
    updated["nodes"] = nodes
    updated["edges"] = edges
    sidecar["nodes"] = key_to_id
    sidecar["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report = {"added_nodes": added_nodes, "added_edges": added_edges, "moved_existing_nodes": 0}
    return updated, sidecar, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Obsidian Canvas 保守增量更新（默认 dry-run）")
    parser.add_argument("canvas")
    parser.add_argument("additions", help="包含 nodes/edges 的 JSON")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--sidecar", help="节点稳定 ID sidecar；默认 <canvas>.mathmap-linker.json")
    parser.add_argument("--horizontal-gap", type=int, default=220)
    parser.add_argument("--vertical-gap", type=int, default=80)
    args = parser.parse_args()

    canvas_path = Path(args.canvas)
    additions_path = Path(args.additions)
    sidecar_path = Path(args.sidecar) if args.sidecar else Path(f"{canvas_path}.mathmap-linker.json")
    canvas = json.loads(canvas_path.read_text(encoding="utf-8-sig"))
    additions = json.loads(additions_path.read_text(encoding="utf-8-sig"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8-sig")) if sidecar_path.is_file() else None
    updated, updated_sidecar, report = update_canvas(
        canvas,
        additions,
        sidecar,
        horizontal_gap=args.horizontal_gap,
        vertical_gap=args.vertical_gap,
    )
    report["mode"] = "apply" if args.apply else "dry-run"
    if args.apply:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = canvas_path.with_suffix(canvas_path.suffix + f".{stamp}.bak")
        shutil.copy2(canvas_path, backup_path)
        canvas_path.write_text(json.dumps(updated, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        sidecar_path.write_text(json.dumps(updated_sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["backup"] = str(backup_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
