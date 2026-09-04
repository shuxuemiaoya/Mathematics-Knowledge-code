#!/usr/bin/env python3
"""Apply a digest-bound organizer review before semantic atomization."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from materialize_book import safe_filename
from semantic_atomization import atomic_json, parse_range, verify_artifact
from validate_book_graph import load_json, sha256_file


class OrganizerReviewError(ValueError):
    pass


def _source_anchor(node: dict[str, Any], nodes: dict[str, dict[str, Any]], cache: dict[str, int]) -> int:
    key = str(node["key"])
    if key in cache:
        return cache[key]
    positions: list[int] = []
    if node.get("layer") == "atom":
        positions.append(int(node["source_range"][0]))
    else:
        positions.extend(int(item[0]) for item in node.get("heading_ranges", []))
        positions.extend(_source_anchor(nodes[str(child)], nodes, cache) for child in node.get("children", []) if str(child) in nodes)
    if not positions:
        raise OrganizerReviewError(f"Node has no source anchor: {key}")
    cache[key] = min(positions)
    return cache[key]


def _draft_atom(owner: str, source_range: list[int], source: dict[str, Any]) -> dict[str, Any]:
    identity = f"{owner}:{source_range[0]}:{source_range[1]}:{source.get('key')}"
    key = f"draft-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
    return {
        "key": key,
        "title": str(source.get("title") or f"Source {source_range[0]}-{source_range[1]}"),
        "layer": "atom",
        "parent_key": owner,
        "category": source.get("category") if source.get("category") in {"knowledge", "worked-example", "exercise", "scenario"} else "knowledge",
        "filename": f"_draft/atoms/{key}.md",
        "source_range": source_range,
    }


def _descendants(nodes: dict[str, dict[str, Any]], root: str) -> list[str]:
    result: list[str] = []

    def visit(key: str) -> None:
        if key in result or key not in nodes:
            return
        result.append(key)
        for child in nodes[key].get("children", []):
            if nodes.get(str(child), {}).get("layer") == "organizer":
                visit(str(child))

    visit(root)
    return result


def _rewrite_subtree_directory(nodes: dict[str, dict[str, Any]], root: str, new_directory: PurePosixPath) -> None:
    old_directory = PurePosixPath(str(nodes[root]["filename"])).parent
    for key in _descendants(nodes, root):
        current = PurePosixPath(str(nodes[key]["filename"]))
        try:
            suffix = current.relative_to(old_directory)
        except ValueError as exc:
            raise OrganizerReviewError(f"Organizer subtree filename escapes its directory: {key}") from exc
        nodes[key]["filename"] = str(new_directory / suffix)


def refine_manifest(base_path: Path, review_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    base_path, review_path = base_path.expanduser().resolve(), review_path.expanduser().resolve()
    base, review = load_json(base_path), load_json(review_path)
    verify_artifact(review, "organizer-review")
    if review.get("status") != "passed":
        raise OrganizerReviewError("Organizer review must be passed")
    if review.get("base_manifest_sha256") != sha256_file(base_path):
        raise OrganizerReviewError("Organizer review binds a different base manifest")
    source = Path(str(base.get("source_markdown", ""))).expanduser().resolve()
    if not source.is_file() or review.get("source_markdown_sha256") != sha256_file(source) or base.get("source_markdown_sha256") != sha256_file(source):
        raise OrganizerReviewError("Organizer review source Markdown is missing or stale")
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    raw_nodes = base.get("nodes")
    if not isinstance(raw_nodes, list):
        raise OrganizerReviewError("Base manifest nodes must be an array")
    base_nodes = {str(node["key"]): dict(node) for node in raw_nodes if isinstance(node, dict) and isinstance(node.get("key"), str)}
    if len(base_nodes) != len(raw_nodes):
        raise OrganizerReviewError("Base manifest contains invalid or duplicate nodes")
    roots = [key for key, node in base_nodes.items() if node.get("layer") == "organizer" and node.get("parent_key") is None]
    if len(roots) != 1:
        raise OrganizerReviewError("Base manifest must have one root organizer")

    demoted_raw = review.get("demote_organizer_keys", [])
    if not isinstance(demoted_raw, list) or any(not isinstance(key, str) for key in demoted_raw):
        raise OrganizerReviewError("demote_organizer_keys must be an array of keys")
    demoted = set(demoted_raw)
    if roots[0] in demoted or any(base_nodes.get(key, {}).get("layer") != "organizer" for key in demoted):
        raise OrganizerReviewError("Demoted keys must name non-root organizers")
    for key in demoted:
        for child in base_nodes[key].get("children", []):
            child_node = base_nodes.get(str(child), {})
            if child_node.get("layer") == "organizer" and str(child) not in demoted:
                raise OrganizerReviewError(f"Demoted organizer retains organizer child: {key} -> {child}")

    raw_runs = review.get("content_runs")
    if not isinstance(raw_runs, list) or not raw_runs:
        raise OrganizerReviewError("content_runs must be a nonempty array")
    runs: list[dict[str, Any]] = []
    seen_owners: set[str] = set()
    for index, item in enumerate(raw_runs):
        if not isinstance(item, dict):
            raise OrganizerReviewError(f"content_runs[{index}] must be an object")
        start, end = parse_range(item.get("source_range"), f"content_runs[{index}].source_range", len(lines))
        owner = item.get("owner_key")
        if not isinstance(owner, str) or not owner or owner in seen_owners:
            raise OrganizerReviewError("Every content run needs a unique owner_key")
        seen_owners.add(owner)
        create = bool(item.get("create_organizer", False))
        if create:
            parent = item.get("parent_key")
            title = item.get("title")
            if not isinstance(parent, str) or base_nodes.get(parent, {}).get("layer") != "organizer" or parent in demoted:
                raise OrganizerReviewError(f"Invalid parent for synthesized organizer: {owner}")
            if owner in base_nodes or not isinstance(title, str) or not title.strip():
                raise OrganizerReviewError(f"Invalid synthesized organizer: {owner}")
            reason = item.get("reason")
            if not isinstance(reason, str) or len(reason.strip()) < 12:
                raise OrganizerReviewError(f"Synthesized organizer needs a concrete reason: {owner}")
        elif base_nodes.get(owner, {}).get("layer") != "organizer" or owner in demoted:
            raise OrganizerReviewError(f"Existing content-run owner is invalid: {owner}")
        runs.append({**item, "owner_key": owner, "source_range": [start, end], "create_organizer": create})
    runs.sort(key=lambda item: (item["source_range"][0], item["source_range"][1]))
    for left, right in zip(runs, runs[1:]):
        if left["source_range"][1] >= right["source_range"][0]:
            raise OrganizerReviewError("Content runs must not overlap")

    for key, node in base_nodes.items():
        if key in demoted or node.get("layer") != "organizer":
            continue
        for heading in node.get("heading_ranges", []):
            h_start, h_end = parse_range(heading, f"node {key}.heading_ranges", len(lines))
            if any(run["source_range"][0] <= h_end and h_start <= run["source_range"][1] for run in runs):
                raise OrganizerReviewError(f"Content run crosses retained organizer heading: {key}")
    demoted_headings: list[int] = []
    for key in demoted:
        for heading in base_nodes[key].get("heading_ranges", []):
            start, end = parse_range(heading, f"node {key}.heading_ranges", len(lines))
            demoted_headings.extend(range(start, end + 1))
            if not any(run["source_range"][0] <= start and end <= run["source_range"][1] for run in runs):
                raise OrganizerReviewError(f"Demoted heading is outside reviewed content runs: {key}")

    nodes = {key: dict(node) for key, node in base_nodes.items() if node.get("layer") == "organizer" and key not in demoted}
    for key, node in list(nodes.items()):
        if node.get("parent_key") in demoted:
            raise OrganizerReviewError(f"Retained organizer still belongs to demoted parent: {key}")
        node["children"] = []
    for run in runs:
        if not run["create_organizer"]:
            continue
        parent = nodes[str(run["parent_key"])]
        title = str(run["title"]).strip()
        nodes[run["owner_key"]] = {
            "key": run["owner_key"], "title": title, "layer": "organizer",
            "parent_key": str(run["parent_key"]),
            "organizer_level": int(parent.get("organizer_level", 1)) + 1,
            "filename": str(PurePosixPath(str(parent["filename"])).parent / f"topic-{hashlib.sha256(run['owner_key'].encode()).hexdigest()[:8]}" / f"{safe_filename(title, run['owner_key'])}.md"),
            "heading_ranges": [], "children": [],
        }

    atoms = [node for node in base_nodes.values() if node.get("layer") == "atom"]
    touched: set[str] = set()
    rebuilt_atoms: list[dict[str, Any]] = []
    demoted_heading_set = set(demoted_headings)
    for run in runs:
        start, end = run["source_range"]
        pieces: list[tuple[int, int, dict[str, Any]]] = []
        for atom in atoms:
            a_start, a_end = parse_range(atom.get("source_range"), f"node {atom.get('key')}.source_range", len(lines))
            overlap_start, overlap_end = max(start, a_start), min(end, a_end)
            if overlap_start <= overlap_end:
                touched.add(str(atom["key"]))
                pieces.append((overlap_start, overlap_end, atom))
        if not pieces:
            raise OrganizerReviewError(f"Content run contains no draft atoms: {run['owner_key']}")
        pieces.sort(key=lambda item: (item[0], item[1]))
        for (left_start, left_end, _), (right_start, _, _) in zip(pieces, pieces[1:]):
            if left_end >= right_start:
                raise OrganizerReviewError(f"Overlapping draft atoms in content run: {run['owner_key']}")
        adjusted: list[list[Any]] = [[piece[0], piece[1], piece[2]] for piece in pieces]
        adjusted[0][0] = start
        for index in range(len(adjusted) - 1):
            current, following = adjusted[index], adjusted[index + 1]
            heading_candidates = sorted(line for line in demoted_heading_set if current[1] < line < following[0])
            boundary = heading_candidates[0] if heading_candidates else following[0]
            current[1] = boundary - 1
            following[0] = boundary
        adjusted[-1][1] = end
        for a_start, a_end, source_atom in adjusted:
            rebuilt_atoms.append(_draft_atom(run["owner_key"], [int(a_start), int(a_end)], source_atom))

    for atom in atoms:
        key = str(atom["key"])
        if key in touched:
            a_start, a_end = atom["source_range"]
            uncovered = [number for number in range(int(a_start), int(a_end) + 1) if lines[number - 1].strip() and not any(run["source_range"][0] <= number <= run["source_range"][1] for run in runs)]
            if uncovered:
                raise OrganizerReviewError(f"Reviewed content runs leave nonblank atom lines uncovered: {key} at {uncovered[:5]}")
            continue
        if atom.get("parent_key") in demoted:
            raise OrganizerReviewError(f"Atom under demoted organizer is outside content runs: {key}")
        rebuilt_atoms.append(dict(atom))
    for atom in rebuilt_atoms:
        if str(atom.get("parent_key")) not in nodes:
            raise OrganizerReviewError(f"Atom has no retained owner: {atom.get('key')}")
        nodes[str(atom["key"])] = atom

    cache: dict[str, int] = {}
    for key, node in nodes.items():
        if node.get("parent_key") is not None:
            parent = nodes.get(str(node["parent_key"]))
            if parent is None or parent.get("layer") != "organizer":
                raise OrganizerReviewError(f"Node has invalid parent after review: {key}")
            parent["children"].append(key)
    for node in nodes.values():
        if node.get("layer") == "organizer":
            node["children"].sort(key=lambda child: (_source_anchor(nodes[child], nodes, cache), child))
            if not node["children"]:
                raise OrganizerReviewError(f"Organizer is empty after review: {node['key']}")

    renumber = review.get("renumber_parent_keys", [])
    if not isinstance(renumber, list) or any(not isinstance(key, str) for key in renumber):
        raise OrganizerReviewError("renumber_parent_keys must be an array")
    for parent_key in renumber:
        parent = nodes.get(parent_key)
        if parent is None or parent.get("layer") != "organizer":
            raise OrganizerReviewError(f"Invalid renumber parent: {parent_key}")
        parent_directory = PurePosixPath(str(parent["filename"])).parent
        organizer_children = [key for key in parent["children"] if nodes[key].get("layer") == "organizer"]
        for position, child_key in enumerate(organizer_children, start=1):
            child = nodes[child_key]
            new_directory = parent_directory / f"{position:02d} {safe_filename(str(child['title']), child_key)}"
            _rewrite_subtree_directory(nodes, child_key, new_directory)

    ordered_atoms = sorted((node for node in nodes.values() if node.get("layer") == "atom"), key=lambda node: (int(node["source_range"][0]), int(node["source_range"][1]), str(node["key"])))
    ordered_nodes = sorted(nodes.values(), key=lambda node: (_source_anchor(node, nodes, cache), 0 if node.get("layer") == "organizer" else 1, str(node["key"])))
    refined = {
        **base,
        "review": {**base.get("review", {}), "status": "review_required", "toc_hierarchy": "passed", "method": "Digest-bound organizer review; semantic atomization pending"},
        "organizer_review": {
            "status": "passed", "path": str(review_path), "sha256": review["artifact_sha256"],
            "demoted_organizer_keys": sorted(demoted),
            "synthesized_organizer_keys": sorted(run["owner_key"] for run in runs if run["create_organizer"]),
        },
        "nodes": ordered_nodes,
        "source_order": [str(node["key"]) for node in ordered_atoms],
        "relations": [],
    }
    report = {
        "schema_version": 1, "status": "passed", "base_manifest": str(base_path),
        "organizer_review": str(review_path), "source_markdown": str(source),
        "counts": {
            "demoted_organizers": len(demoted),
            "synthesized_organizers": sum(bool(run["create_organizer"]) for run in runs),
            "content_runs": len(runs),
            "organizers": sum(node.get("layer") == "organizer" for node in nodes.values()),
            "draft_atoms": len(ordered_atoms),
        },
    }
    return refined, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        refined, report = refine_manifest(args.manifest, args.review)
        atomic_json(args.output, refined, args.overwrite)
        if args.report:
            atomic_json(args.report, report, args.overwrite)
        result, code = {**report, "output": str(args.output.expanduser().resolve())}, 0
    except Exception as exc:
        result, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
