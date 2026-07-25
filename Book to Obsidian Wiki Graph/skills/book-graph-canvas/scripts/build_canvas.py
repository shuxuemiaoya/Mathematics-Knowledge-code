#!/usr/bin/env python3
"""Compile a reviewed semantic manifest into an Obsidian canvas."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any


MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[[^\]]+\]\(((?:[^()]|\([^()]*\))*)\)"
)
EXTERNAL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
NODE_TYPES = {"group", "text"}
DEFAULT_NODE_COLORS = {None, "1", "2", "3", "4", "5", "6", "#c800ff"}
DEFAULT_EDGE_COLORS = {None, "2", "4", "5", "6"}
SIDES = {"top", "right", "bottom", "left"}
ENDS = {"none", "arrow"}


class ManifestError(ValueError):
    """Raised when a canvas manifest violates the compiler contract."""


def stable_id(kind: str, key: str) -> str:
    return hashlib.sha256(f"{kind}:{key}".encode("utf-8")).hexdigest()[:16]


def _require_number(value: Any, field: str, key: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"node {key!r} field {field!r} must be numeric")
    return value


def resolve_link(href: str, source: Path, vault_root: Path | None) -> Path | None:
    raw = href.strip().strip("<>")
    if EXTERNAL_SCHEME_RE.match(raw):
        return None
    path_text = raw.split("#", 1)[0].split("?", 1)[0]
    if not path_text:
        return source

    vault_absolute = path_text.startswith(("/", "\\"))
    decoded = urllib.parse.unquote(path_text).replace("/", os.sep)
    if vault_absolute:
        if vault_root is None:
            raise ManifestError(
                f"vault-root link requires --vault-root: {href}"
            )
        return (vault_root / decoded.lstrip("/\\")).resolve()
    candidate = Path(decoded)
    if candidate.is_absolute():
        return candidate.resolve()

    if vault_root is not None:
        vault_candidate = (vault_root / candidate).resolve()
        first_part = candidate.parts[0] if candidate.parts else ""
        if vault_candidate.exists() or (vault_root / first_part).exists():
            return vault_candidate
    return (source.parent / candidate).resolve()


def validate_canvas_links(
    nodes: list[dict[str, Any]], output: Path, vault_root: Path | None
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for node in nodes:
        if node.get("type") != "text":
            continue
        for href in MARKDOWN_LINK_RE.findall(node.get("text", "")):
            target = resolve_link(href, output, vault_root)
            if target is not None and not target.exists():
                missing.append(
                    {
                        "node_key": node["key"],
                        "href": href,
                        "resolved": str(target),
                    }
                )
    return missing


def compile_manifest(
    manifest: dict[str, Any],
    output: Path,
    vault_root: Path | None = None,
    *,
    node_colors: set[str | None] | None = None,
    edge_colors: set[str | None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    node_colors = node_colors or DEFAULT_NODE_COLORS
    edge_colors = edge_colors or DEFAULT_EDGE_COLORS
    if manifest.get("version") != 1:
        raise ManifestError("manifest version must be 1")
    raw_nodes = manifest.get("nodes")
    raw_edges = manifest.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ManifestError("manifest must contain list fields 'nodes' and 'edges'")

    key_to_id: dict[str, str] = {}
    used_ids: set[str] = set()
    compiled_nodes: list[dict[str, Any]] = []

    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise ManifestError("every node must be an object")
        key = raw.get("key")
        node_type = raw.get("type")
        if not isinstance(key, str) or not key.strip():
            raise ManifestError("every node needs a non-empty string key")
        if key in key_to_id:
            raise ManifestError(f"duplicate node key: {key}")
        if node_type not in NODE_TYPES:
            raise ManifestError(f"node {key!r} has unsupported type {node_type!r}")
        color = raw.get("color")
        if color not in node_colors:
            raise ManifestError(f"node {key!r} has unsupported color {color!r}")

        x = _require_number(raw.get("x"), "x", key)
        y = _require_number(raw.get("y"), "y", key)
        width = _require_number(raw.get("width"), "width", key)
        height = _require_number(raw.get("height"), "height", key)
        if width <= 0 or height <= 0:
            raise ManifestError(f"node {key!r} must have positive dimensions")

        node_id = stable_id("node", key)
        if node_id in used_ids:
            raise ManifestError(f"generated node ID collision for key {key!r}")
        used_ids.add(node_id)
        key_to_id[key] = node_id

        compiled: dict[str, Any] = {
            "id": node_id,
            "type": node_type,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
        if node_type == "group":
            label = raw.get("label")
            if label is not None:
                if not isinstance(label, str):
                    raise ManifestError(f"group {key!r} label must be a string")
                compiled["label"] = label
        else:
            text = raw.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ManifestError(f"text node {key!r} needs non-empty text")
            compiled["text"] = text
        if color is not None:
            compiled["color"] = color
        compiled_nodes.append(compiled)

    missing_links = validate_canvas_links(raw_nodes, output, vault_root)
    if missing_links:
        sample = json.dumps(missing_links[:10], ensure_ascii=False)
        raise ManifestError(f"canvas manifest has unresolved links: {sample}")

    compiled_edges: list[dict[str, Any]] = []
    used_edge_ids: set[str] = set()
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise ManifestError("every edge must be an object")
        from_key = raw.get("from")
        to_key = raw.get("to")
        if from_key not in key_to_id or to_key not in key_to_id:
            raise ManifestError(
                f"edge {index} references missing endpoint: {from_key!r} -> {to_key!r}"
            )
        color = raw.get("color")
        if color not in edge_colors:
            raise ManifestError(f"edge {index} has unsupported color {color!r}")

        edge_key = raw.get("key")
        if edge_key is None:
            edge_key = (
                f"{from_key}|{to_key}|{raw.get('label', '')}|{color or ''}|{index}"
            )
        if not isinstance(edge_key, str) or not edge_key:
            raise ManifestError(f"edge {index} key must be a non-empty string")
        edge_id = stable_id("edge", edge_key)
        if edge_id in used_edge_ids:
            raise ManifestError(f"duplicate or colliding edge key: {edge_key}")
        used_edge_ids.add(edge_id)

        compiled_edge: dict[str, Any] = {
            "id": edge_id,
            "fromNode": key_to_id[from_key],
            "toNode": key_to_id[to_key],
        }
        for field in ("fromSide", "toSide"):
            value = raw.get(field)
            if value is not None:
                if value not in SIDES:
                    raise ManifestError(
                        f"edge {edge_key!r} has invalid {field}: {value!r}"
                    )
                compiled_edge[field] = value
        for field in ("fromEnd", "toEnd"):
            value = raw.get(field)
            if value is not None:
                if value not in ENDS:
                    raise ManifestError(
                        f"edge {edge_key!r} has invalid {field}: {value!r}"
                    )
                compiled_edge[field] = value
        label = raw.get("label")
        if label is not None:
            if not isinstance(label, str):
                raise ManifestError(f"edge {edge_key!r} label must be a string")
            compiled_edge["label"] = label
        if color is not None:
            compiled_edge["color"] = color
        compiled_edges.append(compiled_edge)

    canvas = {"nodes": compiled_nodes, "edges": compiled_edges}
    summary = {
        "nodes": len(compiled_nodes),
        "groups": sum(node["type"] == "group" for node in compiled_nodes),
        "text_nodes": sum(node["type"] == "text" for node in compiled_nodes),
        "edges": len(compiled_edges),
        "node_colors": {
            str(color): sum(node.get("color") == color for node in compiled_nodes)
            for color in sorted(
                {node.get("color") for node in compiled_nodes if node.get("color")},
                key=str,
            )
        },
        "edge_colors": {
            str(color): sum(edge.get("color") == color for edge in compiled_edges)
            for color in sorted(
                {edge.get("color") for edge in compiled_edges if edge.get("color")},
                key=str,
            )
        },
    }
    return canvas, summary


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
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
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile a semantic graph manifest into an Obsidian canvas."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vault-root", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def load_profile(
    profile_path: Path,
    manifest: dict[str, Any],
    vault_root: Path | None,
) -> tuple[set[str | None], set[str | None], Path]:
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    if profile.get("schema_version") != 1:
        raise ManifestError("profile schema_version must be 1")
    if not profile.get("canvas", {}).get("enabled", False):
        raise ManifestError("profile disables canvas generation")

    profile_vault = Path(profile.get("paths", {}).get("vault_root", "")).resolve()
    if vault_root is None:
        vault_root = profile_vault
    elif vault_root != profile_vault:
        raise ManifestError("--vault-root does not match profile paths.vault_root")

    manifest_profile = manifest.get("profile")
    if not isinstance(manifest_profile, str) or (
        Path(manifest_profile).resolve() != profile_path
    ):
        raise ManifestError("manifest profile path does not match --profile")
    expected_sha256 = profile.get("source", {}).get("sha256")
    if manifest.get("source_sha256") != expected_sha256:
        raise ManifestError("manifest source_sha256 does not match profile")

    canvas = profile.get("canvas", {})
    configured_nodes = canvas.get("node_colors")
    configured_edges = canvas.get("edge_colors")
    if not isinstance(configured_nodes, dict) or not isinstance(
        configured_edges, dict
    ):
        raise ManifestError("profile canvas palettes must be objects")
    node_colors: set[str | None] = {None, *configured_nodes.values()}
    edge_colors: set[str | None] = {None, *configured_edges.values()}
    if not all(isinstance(color, str) and color for color in node_colors - {None}):
        raise ManifestError("profile contains an invalid node color")
    if not all(isinstance(color, str) and color for color in edge_colors - {None}):
        raise ManifestError("profile contains an invalid edge color")
    return node_colors, edge_colors, vault_root


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest_path = args.manifest.resolve()
        output = args.output.resolve()
        vault_root = args.vault_root.resolve() if args.vault_root else None
        if not manifest_path.is_file():
            raise FileNotFoundError(f"manifest does not exist: {manifest_path}")
        if output.suffix.lower() != ".canvas":
            raise ManifestError(f"output must end in .canvas: {output}")
        if output.exists() and not args.overwrite and not args.dry_run:
            raise FileExistsError(
                f"output already exists; pass --overwrite explicitly: {output}"
            )
        if vault_root is not None and not vault_root.is_dir():
            raise NotADirectoryError(f"vault root does not exist: {vault_root}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        node_colors = DEFAULT_NODE_COLORS
        edge_colors = DEFAULT_EDGE_COLORS
        if args.profile:
            profile_path = args.profile.resolve()
            if not profile_path.is_file():
                raise FileNotFoundError(f"profile does not exist: {profile_path}")
            node_colors, edge_colors, vault_root = load_profile(
                profile_path, manifest, vault_root
            )
        canvas, summary = compile_manifest(
            manifest,
            output,
            vault_root,
            node_colors=node_colors,
            edge_colors=edge_colors,
        )
        if not args.dry_run:
            atomic_write_json(output, canvas)
        result = {
            "status": "passed",
            "manifest": str(manifest_path),
            "output": str(output),
            "written": not args.dry_run,
            "summary": summary,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        result = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
