#!/usr/bin/env python3
"""Materialize a passed two-pass atomization without rewriting source prose."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any

from semantic_atomization import ATOM_CATEGORY_NAMES, verify_artifact
from validate_book_graph import artifact_digest, load_json, sha256_file


CATEGORY_PATHS = {
    "knowledge": "原子层/知识点", "worked-example": "原子层/例题",
    "exercise": "原子层/习题", "scenario": "原子层/情景引入",
}
ATOM_CATEGORY_CODES = {
    "knowledge": "K", "worked-example": "W", "exercise": "E", "scenario": "S",
}
MARKDOWN_RENDERING = {
    "atom_heading_policy": "omit",
    "atom_filename_policy": "sequence-category-code",
    "leaf_organizer_policy": "flat-note",
    "organizer_self_heading_policy": "omit",
    "organizer_child_heading": "relative-depth",
}
MD_IMAGE_RE = re.compile(r"(!\[[^\]]*\]\()((?:[^()]|\([^()]*\))*)(\))")
HTML_IMAGE_RE = re.compile(r"(<img\b[^>]*?\bsrc=[\"'])([^\"']+)([\"'])", re.I)
ATOM_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s+.*)?$")


class MaterializationError(ValueError):
    pass


def safe_filename(value: str, fallback: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r"[\x00-\x1f<>:\"/\\|?*#]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip(". -")
    return (value or fallback)[:100].rstrip(". -") or fallback


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
    """Render exact source content while omitting source Markdown title lines."""
    start, end = source_range
    rendered = [line for line in lines[start - 1 : end] if not ATOM_HEADING_RE.match(line)]
    while rendered and not rendered[0].strip():
        rendered.pop(0)
    while rendered and not rendered[-1].strip():
        rendered.pop()
    return "\n".join(rendered) + "\n"


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
    nodes[root]["children"] = [str(key) for key in scope]
    atoms = final.get("atoms")
    if not isinstance(atoms, list) or not atoms:
        raise MaterializationError("Final atomization has no atoms")
    atoms = sorted(atoms, key=lambda item: (int(item["source_range"][0]), int(item["source_range"][1])))
    for sequence, atom in enumerate(atoms, start=1):
        if atom.get("category") not in ATOM_CATEGORY_NAMES or str(atom.get("owner_key")) not in nodes:
            raise MaterializationError(f"Invalid category or owner for {atom.get('atom_id')}")
        key = final_key(atom)
        title = str(atom.get("title", "")).strip() or f"Atom {sequence}"
        category_code = ATOM_CATEGORY_CODES[str(atom["category"])]
        filename = f"{CATEGORY_PATHS[atom['category']]}/{sequence:04d}-{category_code}.md"
        nodes[key] = {"key": key, "title": title, "layer": "atom", "parent_key": str(atom["owner_key"]), "category": atom["category"], "filename": filename, "source_range": list(atom["source_range"]), "atomization_id": atom["atom_id"]}
    # Populate every organizer before resolving descendant-based anchors.
    # Synthesized knowledge-topic organizers can legitimately have no printed
    # heading range, so their anchor depends on children that may otherwise be
    # visited later in an arbitrary set-derived dictionary order.
    for key, node in nodes.items():
        if node.get("layer") != "organizer" or key == root:
            continue
        organizer_children = [str(child) for child in base_nodes[key].get("children", []) if str(child) in included and base_nodes.get(str(child), {}).get("layer") == "organizer"]
        atom_children = [final_key(atom) for atom in atoms if str(atom.get("owner_key")) == key]
        node["children"] = organizer_children + atom_children
        if not node["children"]:
            raise MaterializationError(f"Selected organizer has no children: {key}")
    cache: dict[str, int] = {}
    for key, node in nodes.items():
        if node.get("layer") == "organizer" and key != root:
            node["children"] = sorted(node["children"], key=lambda child: (anchor(nodes[child], nodes, cache), child))
    flatten_leaf_organizer_filenames(nodes, root)
    return list(nodes.values()), root


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


def materialize(base_path: Path, final_path: Path, book_root: Path, output_manifest: Path, output_profile: Path | None = None, overwrite: bool = False) -> dict[str, Any]:
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
    source = Path(str(base.get("source_markdown", ""))).expanduser().resolve()
    if not source.is_file() or sha256_file(source) != final.get("source_markdown_sha256"):
        raise MaterializationError("Final atomization source is stale")
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    output_nodes, root = prepare_nodes(base, final)
    by_key = {str(node["key"]): node for node in output_nodes}
    book_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{book_root.name}.materialize-", dir=book_root.parent))
    copied: dict[Path, Path] = {}
    unresolved: list[str] = []
    try:
        for node in output_nodes:
            note = temporary / str(node["filename"])
            note.parent.mkdir(parents=True, exist_ok=True)
            if node["layer"] == "atom":
                source_text = render_atom_source(lines, node["source_range"])
                note.write_text(rewrite_assets(source_text, source, note, temporary, copied, unresolved), encoding="utf-8")
            else:
                links = []
                for child_key in node["children"]:
                    child = by_key[child_key]
                    relative = os.path.relpath(temporary / child["filename"], note.parent).replace("\\", "/")
                    embed = f"![{markdown_label(str(child['title']))}]({encode_href(relative)})"
                    if child.get("layer") == "organizer":
                        depth = organizer_heading_depth(child, by_key, root)
                        embed = f"{'#' * depth} {child['title']}\n\n{embed}"
                    links.append(embed)
                note.write_text("\n\n".join(links) + "\n", encoding="utf-8")
        if unresolved:
            raise MaterializationError(f"Unresolved assets: {sorted(set(unresolved))[:10]}")
        if book_root.exists():
            shutil.rmtree(book_root)
        os.replace(temporary, book_root)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    base_profile = load_json(Path(str(base["profile"])).expanduser().resolve())
    base_profile["paths"] = {**base_profile.get("paths", {}), "staging_root": str(output_manifest.parent), "book_root": str(book_root)}
    base_profile["atomization"] = dict(final["atomization"])
    base_profile["markdown_rendering"] = dict(MARKDOWN_RENDERING)
    output_profile.parent.mkdir(parents=True, exist_ok=True)
    output_profile.write_text(json.dumps(base_profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    covered: list[tuple[int, int]] = []
    for node in output_nodes:
        covered.extend([tuple(node["source_range"])] if node["layer"] == "atom" else [tuple(item) for item in node.get("heading_ranges", [])])
    source_order = [str(node["key"]) for node in sorted((node for node in output_nodes if node["layer"] == "atom"), key=lambda item: (int(item["source_range"][0]), int(item["source_range"][1])))]
    bindings = {name: dict(binding) for name, binding in final.get("bindings", {}).items() if isinstance(binding, dict)}
    manifest = {
        "schema_version": 1, "profile": str(output_profile), "source_sha256": base_profile.get("source", {}).get("sha256"),
        "source_markdown": str(source), "source_markdown_sha256": sha256_file(source),
        "review": {"status": "passed", "reviewed_entire_book": True, "toc_hierarchy": "passed", "source_coverage": "passed", "atom_link_free": "passed", "method": "Two-pass constrained semantic atomization"},
        "atomization_review": {"status": "passed", "mode": "llm-two-pass", "final_artifact": {"path": str(final_path), "sha256": final["artifact_sha256"]}, "bindings": bindings, "reviewer": final.get("reviewer"), "unresolved_count": 0},
        "excluded_ranges": complement_ranges(len(lines), covered), "nodes": output_nodes, "source_order": source_order, "relations": [],
    }
    if isinstance(base.get("organizer_review"), dict):
        manifest["organizer_review"] = dict(base["organizer_review"])
    output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {"organizers": sum(node["layer"] == "organizer" for node in output_nodes), "atoms": len(source_order), "atom_categories": {category: sum(node.get("category") == category for node in output_nodes) for category in CATEGORY_PATHS}, "assets": len(copied)}
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
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report, code = materialize(args.base_manifest, args.atomization_final, args.book_root, args.output_manifest, args.output_profile, args.overwrite), 0
    except Exception as exc:
        report, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
