#!/usr/bin/env python3
"""Validate reviewed textbook node ownership and rendered organizer pages."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


ATOM_TYPES = {
    "scenario",
    "knowledge",
    "worked-example",
    "practice-question",
    "section-exercise-question",
    "concept",
    "reading",
    "history",
    "method",
    "tool",
}
ORGANIZER_TYPES = {
    "book",
    "chapter",
    "section",
    "knowledge-theme",
    "practice",
    "section-exercise",
}
SECOND_LAYER_ORGANIZERS = {
    "knowledge-theme",
    "practice",
    "section-exercise",
}
PHYSICAL_FOLDER_ORGANIZERS = {
    "chapter",
    "section",
    "knowledge-theme",
    "practice",
    "section-exercise",
}
GENERIC_ORGANIZER_TITLE_RE = re.compile(
    r"^(?:组织|主题|知识点|分组|group|topic)\s*\d*$", re.IGNORECASE
)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
LINK_LINE_RE = re.compile(
    r"^!\[([^\]]+)\]\(((?:[^()]|\([^()]*\))*)\)\s*$"
)
EXERCISE_GROUP_HEADING_RE = re.compile(
    r"^#{4,6}\s+(?:复习巩固|综合运用|拓广探索)\s*$"
)
MARKDOWN_IMAGE_LINE_RE = re.compile(
    r"^!\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)\s*$"
)


class ArchitectureError(ValueError):
    pass


def architecture_required(profile: dict[str, Any]) -> bool:
    kind = str(profile.get("book", {}).get("kind", "")).casefold()
    decomposition = profile.get("decomposition", {})
    return bool(
        "textbook" in kind
        and isinstance(decomposition, dict)
        and decomposition.get("require_textbook_node_architecture", False)
    )


def _nodes(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw_nodes = manifest.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ArchitectureError("split manifest needs a non-empty nodes array")
    lookup: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            raise ArchitectureError(f"split node {index} must be an object")
        key = node.get("key")
        if not isinstance(key, str) or not key:
            raise ArchitectureError(f"split node {index}.key is required")
        if key in lookup:
            raise ArchitectureError(f"duplicate split node key: {key}")
        lookup[key] = node
    return raw_nodes, lookup


def _children(
    node_key: str,
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        (node for node in nodes if node.get("parent_key") == node_key),
        key=lambda node: (
            int(node.get("start_line", 0)),
            int(node.get("end_line", 0)),
            str(node.get("key", "")),
        ),
    )


def _organizer_type(node: dict[str, Any]) -> str | None:
    value = node.get("organizer_type")
    return value if isinstance(value, str) else None


def _node_type(node: dict[str, Any]) -> str:
    value = node.get("node_type")
    return value if isinstance(value, str) else ""


def _require_children_of_type(
    node: dict[str, Any],
    children: list[dict[str, Any]],
    allowed: set[str],
) -> None:
    wrong = [
        f"{child.get('key')}:{_node_type(child)}"
        for child in children
        if _node_type(child) not in allowed
    ]
    if wrong:
        raise ArchitectureError(
            f"{node.get('key')} owns invalid child types: {', '.join(wrong)}"
        )


def _leaf_filename(node: dict[str, Any]) -> str:
    raw = str(node.get("filename") or f"{node.get('title')}.md").replace(
        "\\", "/"
    )
    leaf = raw.rsplit("/", 1)[-1].strip()
    if not leaf:
        raise ArchitectureError(f"node {node.get('key')} needs a filename")
    return leaf


def _folder_name(node: dict[str, Any]) -> str:
    stem = Path(_leaf_filename(node)).stem.strip()
    if not stem:
        raise ArchitectureError(
            f"node {node.get('key')} needs a non-empty folder name"
        )
    return stem


def _owns_same_category_child(
    node: dict[str, Any], nodes: list[dict[str, Any]]
) -> bool:
    category = str(node.get("category", "root"))
    return any(
        str(child.get("category", "root")) == category
        for child in _children(str(node["key"]), nodes)
    )


def _is_physical_folder_owner(
    node: dict[str, Any], nodes: list[dict[str, Any]]
) -> bool:
    return bool(
        _organizer_type(node) in PHYSICAL_FOLDER_ORGANIZERS
        or _owns_same_category_child(node, nodes)
    )


def _ancestor_chain(
    node: dict[str, Any], lookup: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    parent_key = node.get("parent_key")
    while parent_key is not None:
        key = str(parent_key)
        if key in seen:
            raise ArchitectureError(f"node ownership cycle reaches {key}")
        seen.add(key)
        parent = lookup.get(key)
        if parent is None:
            raise ArchitectureError(
                f"node {node.get('key')} has missing parent {key}"
            )
        chain.append(parent)
        parent_key = parent.get("parent_key")
    chain.reverse()
    return chain


def hierarchical_filenames(manifest: dict[str, Any]) -> dict[str, str]:
    """Derive category-relative paths that mirror reviewed note ownership.

    A physical owner is represented as a same-named folder-index note.  Leaf
    notes live in their nearest physical owner's folder.  Cross-category
    children restart below their category root but retain the chapter folder.
    Links remain authoritative for source order.
    """

    nodes, lookup = _nodes(manifest)
    expected: dict[str, str] = {}
    targets: set[tuple[str, str]] = set()
    for node in nodes:
        key = str(node["key"])
        category = str(node.get("category", "root"))
        leaf = _leaf_filename(node)
        if category == "root":
            relative = leaf
        else:
            directories: list[str] = []
            for ancestor in _ancestor_chain(node, lookup):
                ancestor_category = str(ancestor.get("category", "root"))
                organizer_type = _organizer_type(ancestor)
                if organizer_type == "book":
                    continue
                if organizer_type == "chapter" or (
                    ancestor_category == category
                    and _is_physical_folder_owner(ancestor, nodes)
                ):
                    directories.append(_folder_name(ancestor))
            if _is_physical_folder_owner(node, nodes):
                directories.append(_folder_name(node))
            relative = Path(*directories, leaf).as_posix()
        target = (category, relative.casefold())
        if target in targets:
            raise ArchitectureError(
                f"physical hierarchy creates duplicate target: {category}/{relative}"
            )
        targets.add(target)
        expected[key] = relative
    return expected


def apply_hierarchical_filenames(manifest: dict[str, Any]) -> dict[str, Any]:
    """Rewrite node filenames to the deterministic physical hierarchy."""

    expected = hierarchical_filenames(manifest)
    nodes, _ = _nodes(manifest)
    changed: list[dict[str, str]] = []
    for node in nodes:
        key = str(node["key"])
        previous = str(node.get("filename") or f"{node.get('title')}.md").replace(
            "\\", "/"
        )
        current = expected[key]
        if previous != current:
            changed.append({"key": key, "from": previous, "to": current})
            node["filename"] = current
    return {
        "status": "passed",
        "changed_count": len(changed),
        "changes": changed,
    }


def validate_manifest(
    manifest: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Validate the reviewed architecture metadata in one split manifest."""

    if not architecture_required(profile):
        return {"status": "not_required", "node_count": 0}

    review = manifest.get("node_architecture")
    if not isinstance(review, dict):
        raise ArchitectureError("textbook split requires node_architecture")
    if review.get("status") != "passed":
        raise ArchitectureError("node_architecture.status must be passed")
    if review.get("reviewed_entire_book") is not True:
        raise ArchitectureError("node architecture needs complete book review")
    for check in (
        "source_order_expansion",
        "source_content_preservation",
        "source_names_preserved",
        "physical_hierarchy",
    ):
        if review.get(check) != "passed":
            raise ArchitectureError(f"node_architecture.{check} must pass")

    nodes, lookup = _nodes(manifest)
    expected_filenames = hierarchical_filenames(manifest)
    roots = [node for node in nodes if node.get("parent_key") is None]
    if len(roots) != 1:
        raise ArchitectureError("node architecture needs exactly one root")

    atom_count = 0
    organizer_count = 0
    for node in nodes:
        key = str(node["key"])
        actual_filename = str(
            node.get("filename") or f"{node.get('title')}.md"
        ).replace("\\", "/")
        if actual_filename != expected_filenames[key]:
            raise ArchitectureError(
                f"node {key} must use hierarchical filename "
                f"{expected_filenames[key]!r}, got {actual_filename!r}"
            )
        node_type = _node_type(node)
        organizer_type = _organizer_type(node)
        children = _children(key, nodes)

        if node_type == "organizer":
            organizer_count += 1
            if organizer_type not in ORGANIZER_TYPES:
                raise ArchitectureError(
                    f"organizer {key} needs a valid organizer_type"
                )
            if not children:
                raise ArchitectureError(f"organizer {key} has no owned children")
            if organizer_type in SECOND_LAYER_ORGANIZERS:
                if node.get("emit_title") is not False:
                    raise ArchitectureError(
                        f"second-layer organizer {key} must set emit_title false"
                    )
            if organizer_type == "knowledge-theme":
                if GENERIC_ORGANIZER_TITLE_RE.fullmatch(
                    str(node.get("title", "")).strip()
                ):
                    raise ArchitectureError(
                        f"knowledge-theme {key} needs a semantic title"
                    )
                if len(children) < 2:
                    raise ArchitectureError(
                        f"knowledge-theme {key} must group at least two atoms"
                    )
                _require_children_of_type(
                    node, children, {"scenario", "knowledge"}
                )
            elif organizer_type == "practice":
                _require_children_of_type(node, children, {"practice-question"})
            elif organizer_type == "section-exercise":
                _require_children_of_type(
                    node, children, {"section-exercise-question"}
                )
                numbers = [child.get("question_number") for child in children]
                if numbers != list(range(1, len(children) + 1)):
                    raise ArchitectureError(
                        f"section-exercise {key} needs complete sequential "
                        "question_number values starting at 1"
                    )
            elif organizer_type == "section":
                forbidden = {
                    "worked-example",
                    "practice-question",
                    "section-exercise-question",
                }
                direct_forbidden = [
                    str(child.get("key"))
                    for child in children
                    if _node_type(child) in forbidden
                ]
                if direct_forbidden:
                    raise ArchitectureError(
                        f"section {key} directly owns raw question/example atoms: "
                        + ", ".join(direct_forbidden)
                    )
                invalid_organizers = [
                    str(child.get("key"))
                    for child in children
                    if _node_type(child) == "organizer"
                    and _organizer_type(child)
                    not in {
                        "knowledge-theme",
                        "practice",
                        "section-exercise",
                    }
                ]
                if invalid_organizers:
                    raise ArchitectureError(
                        f"section {key} owns invalid organizer types: "
                        + ", ".join(invalid_organizers)
                    )
        elif node_type in ATOM_TYPES:
            atom_count += 1
            if organizer_type is not None:
                raise ArchitectureError(f"atom {key} cannot set organizer_type")
            if node_type in {
                "scenario",
                "knowledge",
                "worked-example",
                "practice-question",
                "section-exercise-question",
            } and node.get("emit_title") is not False:
                raise ArchitectureError(f"source atom {key} must set emit_title false")
            if node_type == "concept" and node.get("emit_title") is not True:
                raise ArchitectureError(f"concept {key} must set emit_title true")
            if node_type in {"reading", "history", "method", "tool"} and not isinstance(
                node.get("emit_title"), bool
            ):
                raise ArchitectureError(f"auxiliary atom {key} needs emit_title")
            if node_type == "knowledge":
                _require_children_of_type(node, children, {"worked-example"})
            elif children:
                raise ArchitectureError(f"atom {key} cannot own child nodes")
        else:
            raise ArchitectureError(f"node {key} needs a reviewed node_type")

        previous_end: int | None = None
        for child in children:
            start = child.get("start_line")
            end = child.get("end_line")
            if not isinstance(start, int) or not isinstance(end, int):
                raise ArchitectureError(f"child of {key} needs integer source bounds")
            if previous_end is not None and start <= previous_end:
                raise ArchitectureError(
                    f"children of {key} overlap or leave source order"
                )
            previous_end = end

    root = roots[0]
    if _node_type(root) != "organizer" or _organizer_type(root) != "book":
        raise ArchitectureError("root node must be the book organizer")

    for node in nodes:
        key = str(node["key"])
        node_type = _node_type(node)
        parent = lookup.get(str(node.get("parent_key")))
        parent_type = _node_type(parent) if parent else ""
        parent_organizer = _organizer_type(parent) if parent else None
        if parent is not None and (
            parent_organizer
            in {"knowledge-theme", "practice", "section-exercise"}
            or (parent_type == "knowledge" and node_type == "worked-example")
        ) and str(node.get("category")) != str(parent.get("category")):
            raise ArchitectureError(
                f"node {key} must share category with its physical owner "
                f"{parent.get('key')}"
            )
        if node_type == "worked-example" and parent_type != "knowledge":
            raise ArchitectureError(
                f"worked example {key} must be owned by a knowledge atom"
            )
        if node_type == "practice-question" and parent_organizer != "practice":
            raise ArchitectureError(
                f"practice question {key} must be owned by a practice organizer"
            )
        if (
            node_type == "section-exercise-question"
            and parent_organizer != "section-exercise"
        ):
            raise ArchitectureError(
                f"section exercise question {key} must be owned by its aggregate"
            )
        if node_type == "scenario" and parent_organizer not in {
            "knowledge-theme",
            "section",
        }:
            raise ArchitectureError(
                f"scenario {key} must introduce a knowledge theme or section"
            )

    expected_order = [
        str(node["key"])
        for node in sorted(
            (node for node in nodes if _node_type(node) in ATOM_TYPES),
            key=lambda node: (
                int(node.get("start_line", 0)),
                -int(node.get("end_line", 0)),
                str(node.get("key", "")),
            ),
        )
    ]
    recorded_order = review.get("atomic_source_order")
    if recorded_order != expected_order:
        raise ArchitectureError(
            "node_architecture.atomic_source_order must equal source-range order"
        )

    return {
        "status": "passed",
        "node_count": len(nodes),
        "organizer_count": organizer_count,
        "atom_count": atom_count,
        "physical_hierarchy": "passed",
        "atomic_source_order": expected_order,
    }


def category_map(profile: dict[str, Any]) -> dict[str, str]:
    return {
        str(item["role"]): str(item["directory"])
        for item in profile.get("categories", [])
        if isinstance(item, dict)
        and item.get("enabled", True)
        and isinstance(item.get("role"), str)
        and isinstance(item.get("directory"), str)
    }


def node_path(
    node: dict[str, Any],
    book_root: Path,
    categories: dict[str, str],
) -> Path:
    filename = str(node.get("filename") or f"{node.get('title')}.md")
    category = str(node.get("category", "root"))
    if category == "root":
        return book_root / filename
    return book_root / categories[category] / filename


def _without_frontmatter(lines: list[str]) -> list[str]:
    if not lines or lines[0].strip() != "---":
        return lines
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[index + 1 :]
    return lines


def _normalize_link_target(href: str, source: Path, vault_root: Path) -> Path:
    raw = urllib.parse.unquote(href.strip().strip("<>").split("#", 1)[0])
    if raw.startswith(("/", "\\")):
        return (vault_root / raw.lstrip("/\\")).resolve()
    return (source.parent / raw.replace("/", os.sep)).resolve()


def audit_corpus(
    book_root: Path,
    vault_root: Path,
    manifest: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Audit rendered headings, organizer bodies, and direct-child link order."""

    summary = validate_manifest(manifest, profile)
    if summary["status"] == "not_required":
        return {**summary, "errors": [], "title_violations": 0}

    nodes, _ = _nodes(manifest)
    categories = category_map(profile)
    expected_paths = {
        str(node["key"]): node_path(node, book_root, categories).resolve()
        for node in nodes
    }
    errors: list[dict[str, Any]] = []
    title_violations = 0

    for node in nodes:
        key = str(node["key"])
        path = expected_paths[key]
        if not path.is_file():
            errors.append({"code": "architecture-note-missing", "node": key})
            continue
        lines = _without_frontmatter(
            path.read_text(encoding="utf-8-sig").splitlines()
        )
        first = next((line.strip() for line in lines if line.strip()), "")
        heading = HEADING_RE.match(first)
        if node.get("emit_title") is False and heading:
            title = str(node.get("title", "")).strip()
            if heading.group(1).strip() in {title, path.stem}:
                title_violations += 1
                errors.append(
                    {
                        "code": "redundant-atomic-or-organizer-title",
                        "node": key,
                        "path": str(path),
                    }
                )

        children = _children(key, nodes)
        organizer_type = _organizer_type(node)
        ownership_page = organizer_type in {
            "section",
            "knowledge-theme",
            "practice",
            "section-exercise",
        }
        if not ownership_page and _node_type(node) != "knowledge":
            continue

        links: list[tuple[str, Path]] = []
        unexpected_body: list[int] = []
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped == "---":
                continue
            if ownership_page and organizer_type == "section" and HEADING_RE.match(
                stripped
            ):
                continue
            match = LINK_LINE_RE.match(stripped)
            if match:
                links.append(
                    (
                        match.group(1),
                        _normalize_link_target(match.group(2), path, vault_root),
                    )
                )
            elif (
                ownership_page
                and organizer_type == "section-exercise"
                and (
                    EXERCISE_GROUP_HEADING_RE.match(stripped)
                    or MARKDOWN_IMAGE_LINE_RE.match(stripped)
                )
            ):
                continue
            elif ownership_page:
                unexpected_body.append(line_number)

        if unexpected_body:
            errors.append(
                {
                    "code": "organizer-contains-source-body",
                    "node": key,
                    "lines": unexpected_body[:20],
                }
            )
        expected_child_paths = [
            expected_paths[str(child["key"])] for child in children
        ]
        actual_child_paths = [
            target
            for _, target in links
            if target in set(expected_child_paths)
        ]
        if actual_child_paths != expected_child_paths:
            errors.append(
                {
                    "code": "child-link-order-or-coverage",
                    "node": key,
                    "expected": [str(path) for path in expected_child_paths],
                    "actual": [str(path) for path in actual_child_paths],
                }
            )

    return {
        **summary,
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "title_violations": title_violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_root", type=Path)
    parser.add_argument("split_manifest", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--vault-root", type=Path)
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        manifest = json.loads(
            args.split_manifest.read_text(encoding="utf-8-sig")
        )
        vault_root = (
            args.vault_root.resolve()
            if args.vault_root
            else Path(profile["paths"]["vault_root"]).resolve()
        )
        report = audit_corpus(
            args.book_root.resolve(), vault_root, manifest, profile
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] in {"passed", "not_required"} else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "errors": [
                        {
                            "code": "architecture-audit-crashed",
                            "detail": f"{type(exc).__name__}: {exc}",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
