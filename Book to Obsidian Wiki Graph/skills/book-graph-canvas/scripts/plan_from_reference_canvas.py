#!/usr/bin/env python3
"""Plan a current graph manifest from a reviewed same-edition canvas layout."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\((.+?\.md)\)")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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


def resolve_link(vault_root: Path, destination: str) -> Path:
    decoded = urllib.parse.unquote(destination.split("#", 1)[0])
    return vault_root / decoded.lstrip("/\\")


def plan(
    reference_canvas: Path,
    profile_path: Path,
    output_manifest: Path,
) -> dict[str, Any]:
    canvas = json.loads(reference_canvas.read_text(encoding="utf-8-sig"))
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    book_root = Path(profile["paths"]["book_root"]).resolve()
    current_by_stem: dict[str, list[Path]] = {}
    current_by_normalized_stem: dict[str, list[Path]] = {}
    for current_note in book_root.rglob("*.md"):
        current_by_stem.setdefault(current_note.stem, []).append(current_note)
        normalized_stem = re.sub(r"\s+", "", current_note.stem).casefold()
        current_by_normalized_stem.setdefault(normalized_stem, []).append(
            current_note
        )
    allowed_node_colors = set(
        str(value) for value in profile["canvas"]["node_colors"].values()
    )
    allowed_edge_colors = set(
        str(value) for value in profile["canvas"]["edge_colors"].values()
    )

    kept_nodes: list[dict[str, Any]] = []
    id_to_key: dict[str, str] = {}
    linked_target_nodes: dict[str, dict[str, Any]] = {}
    skipped_nodes: list[dict[str, Any]] = []
    for index, source in enumerate(canvas.get("nodes", [])):
        node_type = source.get("type")
        if node_type not in {"group", "text"}:
            skipped_nodes.append(
                {"id": source.get("id"), "reason": f"unsupported type {node_type}"}
            )
            continue
        text = str(source.get("text", "")) if node_type == "text" else ""
        if node_type == "text" and not text.strip():
            skipped_nodes.append(
                {"id": source.get("id"), "reason": "empty reference text card"}
            )
            continue
        missing: list[str] = []

        def rebase_link(match: re.Match[str]) -> str:
            label, destination = match.group(1), match.group(2)
            if resolve_link(vault_root, destination).is_file():
                return match.group(0)
            matches = current_by_stem.get(label, [])
            if len(matches) != 1:
                normalized_label = re.sub(r"\s+", "", label).casefold()
                matches = current_by_normalized_stem.get(normalized_label, [])
            if len(matches) != 1:
                missing.append(destination)
                return match.group(0)
            relative = matches[0].relative_to(vault_root).as_posix()
            if profile["links"].get("encode_spaces", False):
                relative = relative.replace(" ", "%20")
            return f"[{label}]({relative})"

        if node_type == "text":
            text = LINK_RE.sub(rebase_link, text)
            # Obsidian's Markdown-link parser can mistake a LaTeX interval
            # followed immediately by ``(k \in ...)`` for a link. A space is
            # mathematically inert and prevents that false positive.
            text = text.replace(r"\right](", r"\right] (")
        if missing:
            skipped_nodes.append(
                {
                    "id": source.get("id"),
                    "reason": "unresolved current note link",
                    "links": missing,
                }
            )
            continue
        source_id = str(source.get("id") or f"node-{index}")
        key = f"reference-{node_type}-{source_id}"
        id_to_key[source_id] = key
        node: dict[str, Any] = {
            "key": key,
            "type": node_type,
            "x": int(source["x"]),
            "y": int(source["y"]),
            "width": int(source["width"]),
            "height": int(source["height"]),
        }
        if node_type == "group":
            if str(source.get("label", "")).strip():
                node["label"] = str(source["label"])
        else:
            node["text"] = text
        color = source.get("color")
        if color is not None and str(color) in allowed_node_colors:
            node["color"] = str(color)
        linked_targets = [match.group(2) for match in LINK_RE.finditer(text)]
        if node_type == "text" and len(set(linked_targets)) == 1:
            linked_target = linked_targets[0]
            existing = linked_target_nodes.get(linked_target)
            if existing is not None:
                id_to_key[source_id] = existing["key"]
                if len(text) > len(str(existing.get("text", ""))):
                    existing["text"] = text
                    existing.update(
                        {
                            "x": node["x"],
                            "y": node["y"],
                            "width": node["width"],
                            "height": node["height"],
                        }
                    )
                    if "color" in node:
                        existing["color"] = node["color"]
                skipped_nodes.append(
                    {
                        "id": source.get("id"),
                        "reason": "duplicate current note link merged",
                        "link": linked_target,
                    }
                )
                continue
            linked_target_nodes[linked_target] = node
        kept_nodes.append(node)

    kept_edges: list[dict[str, Any]] = []
    skipped_edges = 0
    for index, source in enumerate(canvas.get("edges", [])):
        from_key = id_to_key.get(str(source.get("fromNode", "")))
        to_key = id_to_key.get(str(source.get("toNode", "")))
        if not from_key or not to_key:
            skipped_edges += 1
            continue
        edge: dict[str, Any] = {
            "key": f"reference-edge-{source.get('id') or index}",
            "from": from_key,
            "to": to_key,
        }
        for source_field, target_field in (
            ("fromSide", "fromSide"),
            ("toSide", "toSide"),
            ("fromEnd", "fromEnd"),
            ("toEnd", "toEnd"),
            ("label", "label"),
        ):
            if source.get(source_field) is not None:
                edge[target_field] = source[source_field]
        color = source.get("color")
        if color is not None and str(color) in allowed_edge_colors:
            edge["color"] = str(color)
        kept_edges.append(edge)

    manifest = {
        "version": 1,
        "profile": str(profile_path),
        "source_sha256": profile["source"]["sha256"],
        "nodes": kept_nodes,
        "edges": kept_edges,
    }
    atomic_write_json(output_manifest, manifest)
    return {
        "schema_version": 1,
        "stage": "reference-canvas-planning",
        "status": "passed",
        "manifest": str(output_manifest),
        "nodes": len(kept_nodes),
        "groups": sum(node["type"] == "group" for node in kept_nodes),
        "text_nodes": sum(node["type"] == "text" for node in kept_nodes),
        "edges": len(kept_edges),
        "skipped_nodes": len(skipped_nodes),
        "skipped_edges": skipped_edges,
        "skipped_node_details": skipped_nodes,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_canvas", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("output_manifest", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = plan(
        args.reference_canvas.resolve(),
        args.profile.resolve(),
        args.output_manifest.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
