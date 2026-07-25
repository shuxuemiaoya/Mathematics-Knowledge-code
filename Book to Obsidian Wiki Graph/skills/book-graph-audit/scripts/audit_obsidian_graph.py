#!/usr/bin/env python3
"""Audit a corpus produced by the Book to Obsidian Wiki Graph agent."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any


MARKDOWN_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\(((?:[^()]|\([^()]*\))*)\)"
)
MARKDOWN_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)"
)
HTML_IMAGE_RE = re.compile(
    r"""<img\b[^>]*?\bsrc=["']([^"']+)["']""", re.IGNORECASE
)
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
FENCE_RE = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
EXTERNAL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
CALLOUT_RE = re.compile(r"^>\s*\[!([^\]]+)\]")
TOP_LEVEL_CALLOUT_PREFIX_RE = re.compile(r"^>\s*\[!")
FUNCTIONAL_HEADING_RE = re.compile(
    r"^#{4,6}\s+"
    r"(?:观察|思考|探究|问题|实验|尝试|讨论|情景引入|分析|提示|"
    r"解答?|证明|归纳|结论|小结|注意|警告|定理|性质)"
    r"(?:\s|[：:，。]|$)"
)
WORKED_EXAMPLE_RE = re.compile(r"^例\s*\d+(?:\s|[：:，。]|$)")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
ALLOWED_NODE_TYPES = {"group", "text", "file", "link"}
DEFAULT_NODE_COLORS = {None, "1", "2", "3", "4", "5", "6", "#c800ff"}
DEFAULT_EDGE_COLORS = {None, "2", "4", "5", "6"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_fenced_code(text: str) -> str:
    return FENCE_RE.sub("", text)


def category(path: Path, book_root: Path) -> str:
    try:
        relative = path.relative_to(book_root)
    except ValueError:
        return "<external-vault>"
    return relative.parts[0] if len(relative.parts) > 1 else "<root>"


def resolve_href(href: str, source: Path, vault_root: Path) -> Path | None:
    raw = href.strip().strip("<>")
    if EXTERNAL_SCHEME_RE.match(raw):
        return None
    path_text = raw.split("#", 1)[0].split("?", 1)[0]
    if not path_text:
        return source.resolve()

    vault_absolute = path_text.startswith(("/", "\\"))
    decoded = urllib.parse.unquote(path_text).replace("/", os.sep)
    if vault_absolute:
        return (vault_root / decoded.lstrip("/\\")).resolve()
    candidate = Path(decoded)
    if candidate.is_absolute():
        return candidate.resolve()

    relative_candidate = (source.parent / candidate).resolve()
    vault_candidate = (vault_root / candidate).resolve()
    first_part = candidate.parts[0] if candidate.parts else ""

    if relative_candidate.exists():
        return relative_candidate
    if vault_candidate.exists() or (vault_root / first_part).exists():
        return vault_candidate
    return relative_candidate


def target_exists(path: Path) -> bool:
    if path.exists():
        return True
    if not path.suffix and path.with_suffix(".md").exists():
        return True
    return False


def validate_callouts(
    path: Path, text: str, require_blank: bool = True
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    malformed: list[dict[str, Any]] = []
    missing_blank: list[dict[str, Any]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not TOP_LEVEL_CALLOUT_PREFIX_RE.match(line):
            continue
        if not CALLOUT_RE.match(line):
            malformed.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "text": line[:200],
                }
            )
            continue
        if require_blank and index > 0 and lines[index - 1].strip():
            missing_blank.append(
                {
                    "file": str(path),
                    "line": index + 1,
                    "previous": lines[index - 1][:200],
                }
            )
    return malformed, missing_blank


def audit_coverage(
    coverage_path: Path | None,
    expected_source_sha256: str | None,
    *,
    expected_profile: Path | None = None,
    book_root: Path | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if coverage_path is None:
        return None, []
    errors: list[dict[str, Any]] = []
    try:
        data = json.loads(coverage_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, [
            {
                "code": "coverage-invalid-json",
                "path": str(coverage_path),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        ]

    units = data.get("units")
    if not isinstance(units, list):
        return None, [
            {
                "code": "coverage-missing-units",
                "path": str(coverage_path),
            }
        ]
    if (
        expected_source_sha256
        and data.get("source_sha256") != expected_source_sha256
    ):
        errors.append(
            {
                "code": "coverage-source-hash-mismatch",
                "expected": expected_source_sha256,
                "actual": data.get("source_sha256"),
            }
        )
    if expected_profile is not None:
        raw_profile = data.get("profile")
        if not isinstance(raw_profile, str) or (
            Path(raw_profile).resolve() != expected_profile
        ):
            errors.append(
                {
                    "code": "coverage-profile-mismatch",
                    "expected": str(expected_profile),
                    "actual": raw_profile,
                }
            )

    keys: set[str] = set()
    orders: set[int] = set()
    unresolved = 0
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            errors.append({"code": "coverage-unit-not-object", "index": index})
            continue
        key = unit.get("source_key")
        order = unit.get("source_order")
        status = unit.get("status")
        target = unit.get("target")
        if not isinstance(key, str) or not key:
            errors.append({"code": "coverage-missing-key", "index": index})
        elif key in keys:
            errors.append({"code": "coverage-duplicate-key", "source_key": key})
        else:
            keys.add(key)
        if not isinstance(order, int):
            errors.append({"code": "coverage-invalid-order", "source_key": key})
        elif order in orders:
            errors.append({"code": "coverage-duplicate-order", "source_order": order})
        else:
            orders.add(order)
        if status not in {"assigned", "retained"}:
            unresolved += 1
            errors.append(
                {
                    "code": "coverage-unresolved-unit",
                    "source_key": key,
                    "status": status,
                }
            )
        if not isinstance(target, str) or not target:
            errors.append({"code": "coverage-missing-target", "source_key": key})
        elif book_root is not None:
            decoded = urllib.parse.unquote(target.split("#", 1)[0])
            target_path = (book_root / decoded.replace("/", os.sep)).resolve()
            if not target_exists(target_path):
                errors.append(
                    {
                        "code": "coverage-target-missing",
                        "source_key": key,
                        "target": target,
                        "resolved": str(target_path),
                    }
                )

    summary = {
        "path": str(coverage_path),
        "units": len(units),
        "assigned": sum(unit.get("status") == "assigned" for unit in units if isinstance(unit, dict)),
        "retained": sum(unit.get("status") == "retained" for unit in units if isinstance(unit, dict)),
        "unresolved": unresolved,
    }
    return summary, errors


def audit_canvas(
    canvas_path: Path,
    vault_root: Path,
    book_root: Path,
    *,
    allowed_node_colors: set[str | None] | None = None,
    allowed_edge_colors: set[str | None] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    allowed_node_colors = allowed_node_colors or DEFAULT_NODE_COLORS
    allowed_edge_colors = allowed_edge_colors or DEFAULT_EDGE_COLORS
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        canvas = json.loads(canvas_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return (
            {"path": str(canvas_path), "parsed": False},
            [
                {
                    "code": "canvas-invalid-json",
                    "path": str(canvas_path),
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            ],
            warnings,
        )

    nodes = canvas.get("nodes")
    edges = canvas.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return (
            {"path": str(canvas_path), "parsed": True},
            [
                {
                    "code": "canvas-invalid-shape",
                    "path": str(canvas_path),
                }
            ],
            warnings,
        )

    node_ids: list[str] = []
    node_by_id: dict[str, dict[str, Any]] = {}
    linked_targets: collections.Counter[str] = collections.Counter()
    missing_links = 0
    node_colors: collections.Counter[str] = collections.Counter()
    edge_colors: collections.Counter[str] = collections.Counter()

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append({"code": "canvas-node-not-object", "index": index})
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        color = node.get("color")
        if not isinstance(node_id, str) or not node_id:
            errors.append({"code": "canvas-node-missing-id", "index": index})
            continue
        node_ids.append(node_id)
        node_by_id[node_id] = node
        if node_type not in ALLOWED_NODE_TYPES:
            errors.append(
                {
                    "code": "canvas-node-invalid-type",
                    "id": node_id,
                    "type": node_type,
                }
            )
        if color not in allowed_node_colors:
            errors.append(
                {
                    "code": "canvas-node-invalid-color",
                    "id": node_id,
                    "color": color,
                }
            )
        node_colors[str(color) if color is not None else "<none>"] += 1

        text = node.get("text", "")
        if isinstance(text, str):
            for _, href in MARKDOWN_LINK_RE.findall(remove_fenced_code(text)):
                target = resolve_href(href, canvas_path, vault_root)
                if target is not None:
                    linked_targets[str(target).casefold()] += 1
                    if not target_exists(target):
                        missing_links += 1
                        errors.append(
                            {
                                "code": "canvas-missing-link",
                                "canvas": str(canvas_path),
                                "node": node_id,
                                "href": href,
                                "resolved": str(target),
                            }
                        )
        if node_type == "file" and isinstance(node.get("file"), str):
            target = resolve_href(node["file"], canvas_path, vault_root)
            if target is not None and not target_exists(target):
                missing_links += 1
                errors.append(
                    {
                        "code": "canvas-missing-file-node",
                        "canvas": str(canvas_path),
                        "node": node_id,
                        "file": node["file"],
                        "resolved": str(target),
                    }
                )

    duplicate_ids = sorted(
        node_id for node_id, count in collections.Counter(node_ids).items() if count > 1
    )
    for node_id in duplicate_ids:
        errors.append({"code": "canvas-duplicate-node-id", "id": node_id})

    edge_ids: list[str] = []
    bad_endpoints = 0
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append({"code": "canvas-edge-not-object", "index": index})
            continue
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id:
            errors.append({"code": "canvas-edge-missing-id", "index": index})
        else:
            edge_ids.append(edge_id)
        for field in ("fromNode", "toNode"):
            if edge.get(field) not in node_by_id:
                bad_endpoints += 1
                errors.append(
                    {
                        "code": "canvas-edge-missing-endpoint",
                        "edge": edge_id,
                        "field": field,
                        "value": edge.get(field),
                    }
                )
        color = edge.get("color")
        if color not in allowed_edge_colors:
            errors.append(
                {
                    "code": "canvas-edge-invalid-color",
                    "edge": edge_id,
                    "color": color,
                }
            )
        edge_colors[str(color) if color is not None else "<none>"] += 1

    duplicate_edge_ids = sorted(
        edge_id
        for edge_id, count in collections.Counter(edge_ids).items()
        if count > 1
    )
    for edge_id in duplicate_edge_ids:
        errors.append({"code": "canvas-duplicate-edge-id", "id": edge_id})

    duplicate_targets = sum(count - 1 for count in linked_targets.values() if count > 1)
    if duplicate_targets:
        warnings.append(
            {
                "code": "canvas-duplicate-linked-targets",
                "count": duplicate_targets,
            }
        )

    summary = {
        "path": str(canvas_path),
        "parsed": True,
        "nodes": len(nodes),
        "groups": sum(
            isinstance(node, dict) and node.get("type") == "group" for node in nodes
        ),
        "edges": len(edges),
        "duplicate_node_ids": len(duplicate_ids),
        "duplicate_edge_ids": len(duplicate_edge_ids),
        "bad_edge_endpoints": bad_endpoints,
        "missing_links": missing_links,
        "node_colors": dict(sorted(node_colors.items())),
        "edge_colors": dict(sorted(edge_colors.items())),
    }
    return summary, errors, warnings


def load_profile(
    profile_path: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, [
            {
                "code": "profile-invalid-json",
                "path": str(profile_path),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        ]
    errors: list[dict[str, Any]] = []
    if profile.get("schema_version") != 1:
        errors.append({"code": "profile-invalid-schema-version"})
    for section in ("book", "source", "paths", "links", "workspace"):
        if not isinstance(profile.get(section), dict):
            errors.append({"code": "profile-invalid-section", "section": section})
    categories = profile.get("categories")
    if not isinstance(categories, list):
        errors.append({"code": "profile-invalid-categories"})
    return profile, errors


def profile_category(
    profile: dict[str, Any] | None, role: str
) -> dict[str, Any] | None:
    if profile is None:
        return None
    for item in profile.get("categories", []):
        if isinstance(item, dict) and item.get("role") == role:
            return item
    return None


def audit_concept_manifest(
    manifest_path: Path | None,
    *,
    expected_source_sha256: str | None,
    expected_profile: Path | None,
    book_root: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if manifest_path is None:
        return None, []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return None, [
            {
                "code": "concept-manifest-invalid-json",
                "path": str(manifest_path),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        ]
    errors: list[dict[str, Any]] = []
    if expected_source_sha256 and (
        data.get("source_sha256") != expected_source_sha256
    ):
        errors.append(
            {
                "code": "concept-manifest-source-hash-mismatch",
                "expected": expected_source_sha256,
                "actual": data.get("source_sha256"),
            }
        )
    if expected_profile is not None:
        raw_profile = data.get("profile")
        if not isinstance(raw_profile, str) or (
            Path(raw_profile).resolve() != expected_profile
        ):
            errors.append(
                {
                    "code": "concept-manifest-profile-mismatch",
                    "expected": str(expected_profile),
                    "actual": raw_profile,
                }
            )
    concepts = data.get("concepts")
    if not isinstance(concepts, list):
        return None, [
            *errors,
            {
                "code": "concept-manifest-missing-concepts",
                "path": str(manifest_path),
            },
        ]
    targets: set[str] = set()
    for index, concept in enumerate(concepts):
        if not isinstance(concept, dict):
            errors.append(
                {"code": "concept-manifest-item-not-object", "index": index}
            )
            continue
        target = concept.get("target")
        if not isinstance(target, str) or not target:
            errors.append(
                {"code": "concept-manifest-target-missing", "index": index}
            )
            continue
        if target in targets:
            errors.append(
                {"code": "concept-manifest-target-duplicate", "target": target}
            )
        targets.add(target)
        decoded = urllib.parse.unquote(target.split("#", 1)[0])
        resolved = (book_root / decoded.replace("/", os.sep)).resolve()
        if not target_exists(resolved):
            errors.append(
                {
                    "code": "concept-manifest-target-missing-on-disk",
                    "target": target,
                    "resolved": str(resolved),
                }
            )
        linked_from = concept.get("linked_from")
        if not isinstance(linked_from, list) or not linked_from:
            errors.append(
                {
                    "code": "concept-manifest-missing-definition-link",
                    "target": target,
                }
            )
    return {
        "path": str(manifest_path),
        "concepts": len(concepts),
        "unique_targets": len(targets),
    }, errors


def audit_book(
    book_root: Path,
    vault_root: Path,
    *,
    source: Path | None = None,
    expected_source_sha256: str | None = None,
    allow_wikilinks: bool = False,
    require_canvas: bool = False,
    coverage_manifest: Path | None = None,
    concept_manifest: Path | None = None,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    profile: dict[str, Any] | None = None
    concept_directory = "概念"
    require_callout_blank = True
    allowed_node_colors = DEFAULT_NODE_COLORS
    allowed_edge_colors = DEFAULT_EDGE_COLORS

    if profile_path is not None:
        profile, profile_errors = load_profile(profile_path)
        errors.extend(profile_errors)
        if profile is not None:
            profile_paths = profile.get("paths", {})
            profile_book_root = Path(
                profile_paths.get("book_root", "")
            ).resolve()
            profile_vault_root = Path(
                profile_paths.get("vault_root", "")
            ).resolve()
            if profile_book_root != book_root:
                errors.append(
                    {
                        "code": "profile-book-root-mismatch",
                        "expected": str(profile_book_root),
                        "actual": str(book_root),
                    }
                )
            if profile_vault_root != vault_root:
                errors.append(
                    {
                        "code": "profile-vault-root-mismatch",
                        "expected": str(profile_vault_root),
                        "actual": str(vault_root),
                    }
                )
            profile_sha256 = profile.get("source", {}).get("sha256")
            if expected_source_sha256 is None:
                expected_source_sha256 = profile_sha256
            elif expected_source_sha256 != profile_sha256:
                errors.append(
                    {
                        "code": "profile-source-hash-mismatch",
                        "expected": expected_source_sha256,
                        "actual": profile_sha256,
                    }
                )
            if source is None:
                raw_source = profile.get("source", {}).get("path")
                if isinstance(raw_source, str) and raw_source:
                    source = Path(raw_source).resolve()
            links = profile.get("links", {})
            if links.get("markdown_only") is False:
                allow_wikilinks = True
            require_callout_blank = profile.get("formatting", {}).get(
                "blank_before_top_level_callout", True
            )
            concept_config = profile_category(profile, "concept")
            if concept_config and concept_config.get("enabled", True):
                concept_directory = str(concept_config.get("directory", "概念"))
            elif concept_config and not concept_config.get("enabled", True):
                concept_directory = ""
            canvas_profile = profile.get("canvas", {})
            node_palette = canvas_profile.get("node_colors")
            edge_palette = canvas_profile.get("edge_colors")
            if isinstance(node_palette, dict):
                allowed_node_colors = {None, *node_palette.values()}
            if isinstance(edge_palette, dict):
                allowed_edge_colors = {None, *edge_palette.values()}
            if require_canvas and not canvas_profile.get("enabled", False):
                errors.append({"code": "canvas-required-but-profile-disabled"})

    if not book_root.is_dir():
        return {
            "status": "failed",
            "errors": [{"code": "book-root-missing", "path": str(book_root)}],
            "warnings": [],
        }
    if not vault_root.is_dir():
        return {
            "status": "failed",
            "errors": [{"code": "vault-root-missing", "path": str(vault_root)}],
            "warnings": [],
        }
    try:
        book_root.relative_to(vault_root)
    except ValueError:
        errors.append(
            {
                "code": "book-root-outside-vault",
                "book_root": str(book_root),
                "vault_root": str(vault_root),
            }
        )

    source_summary = None
    if source is not None:
        if not source.is_file():
            errors.append({"code": "source-missing", "path": str(source)})
        else:
            actual_hash = sha256_file(source)
            source_summary = {
                "path": str(source),
                "sha256": actual_hash,
                "unchanged": (
                    expected_source_sha256 is None
                    or actual_hash == expected_source_sha256
                ),
            }
            if expected_source_sha256 and actual_hash != expected_source_sha256:
                errors.append(
                    {
                        "code": "source-hash-changed",
                        "expected": expected_source_sha256,
                        "actual": actual_hash,
                    }
                )
    elif expected_source_sha256:
        errors.append({"code": "expected-source-hash-without-source"})

    coverage_summary, coverage_errors = audit_coverage(
        coverage_manifest,
        expected_source_sha256,
        expected_profile=profile_path,
        book_root=book_root,
    )
    errors.extend(coverage_errors)
    if coverage_manifest is None:
        if profile_path is not None:
            errors.append({"code": "coverage-manifest-not-provided"})
        else:
            warnings.append({"code": "coverage-manifest-not-provided"})

    concept_summary, concept_manifest_errors = audit_concept_manifest(
        concept_manifest,
        expected_source_sha256=expected_source_sha256,
        expected_profile=profile_path,
        book_root=book_root,
    )
    errors.extend(concept_manifest_errors)
    if concept_directory and concept_manifest is None:
        if profile_path is not None:
            errors.append({"code": "concept-manifest-not-provided"})
        else:
            warnings.append({"code": "concept-manifest-not-provided"})

    markdown_files = sorted(book_root.rglob("*.md"))
    all_images = sorted(
        path
        for path in book_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    category_files: collections.Counter[str] = collections.Counter()
    transitions: collections.Counter[str] = collections.Counter()
    referenced_images: set[str] = set()
    referenced_concepts: set[str] = set()
    concept_root = book_root / concept_directory if concept_directory else None
    concept_files = (
        sorted(concept_root.rglob("*.md"))
        if concept_root is not None and concept_root.is_dir()
        else []
    )
    standard_links = 0
    wikilinks = 0
    image_references = 0
    missing_markdown_links = 0
    missing_images = 0
    malformed_callouts = 0
    callouts_without_blank = 0
    callouts = 0
    unstandardized_functional_blocks = 0
    empty_notes = 0
    empty_concepts = 0

    for path in markdown_files:
        source_category = category(path, book_root)
        category_files[source_category] += 1
        text = path.read_text(encoding="utf-8-sig")
        if not text.strip():
            empty_notes += 1
            errors.append(
                {
                    "code": "empty-markdown-note",
                    "path": str(path.relative_to(book_root)),
                }
            )
        sanitized = remove_fenced_code(text)
        found_wikilinks = WIKILINK_RE.findall(sanitized)
        wikilinks += len(found_wikilinks)
        if found_wikilinks and not allow_wikilinks:
            errors.append(
                {
                    "code": "residual-wikilinks",
                    "path": str(path.relative_to(book_root)),
                    "count": len(found_wikilinks),
                    "samples": found_wikilinks[:10],
                }
            )

        malformed, no_blank = validate_callouts(
            path.relative_to(book_root),
            text,
            require_blank=require_callout_blank,
        )
        malformed_callouts += len(malformed)
        callouts_without_blank += len(no_blank)
        for item in malformed:
            errors.append({"code": "malformed-callout", **item})
        for item in no_blank:
            errors.append({"code": "callout-missing-blank-line", **item})
        callouts += sum(
            1 for line in text.splitlines() if CALLOUT_RE.match(line)
        )

        if profile_path is not None and source_category != concept_directory:
            candidates: list[dict[str, Any]] = []
            for index, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if (
                    FUNCTIONAL_HEADING_RE.match(stripped)
                    or WORKED_EXAMPLE_RE.match(stripped)
                ):
                    candidates.append(
                        {"line": index, "text": stripped[:160]}
                    )
            if candidates:
                unstandardized_functional_blocks += len(candidates)
                errors.append(
                    {
                        "code": "unstandardized-functional-blocks",
                        "path": str(path.relative_to(book_root)),
                        "count": len(candidates),
                        "samples": candidates[:20],
                    }
                )

        for _, href in MARKDOWN_LINK_RE.findall(sanitized):
            standard_links += 1
            target = resolve_href(href, path, vault_root)
            if target is None:
                transitions[f"{source_category}-><external-url>"] += 1
                continue
            transitions[f"{source_category}->{category(target, book_root)}"] += 1
            if not target_exists(target):
                missing_markdown_links += 1
                errors.append(
                    {
                        "code": "missing-markdown-link",
                        "source": str(path.relative_to(book_root)),
                        "href": href,
                        "resolved": str(target),
                    }
                )
            if (
                concept_directory
                and source_category != concept_directory
                and category(target, book_root) == concept_directory
            ):
                referenced_concepts.add(str(target).casefold())

        image_hrefs = MARKDOWN_IMAGE_RE.findall(sanitized) + HTML_IMAGE_RE.findall(
            sanitized
        )
        image_references += len(image_hrefs)
        for href in image_hrefs:
            target = resolve_href(href, path, vault_root)
            if target is None:
                continue
            referenced_images.add(str(target).casefold())
            if not target.exists():
                missing_images += 1
                errors.append(
                    {
                        "code": "missing-image",
                        "source": str(path.relative_to(book_root)),
                        "href": href,
                        "resolved": str(target),
                    }
                )

    for concept in concept_files:
        text = concept.read_text(encoding="utf-8-sig").strip()
        semantic_text = MARKDOWN_LINK_RE.sub("", remove_fenced_code(text))
        semantic_text = re.sub(r"^#{1,6}\s+.*$", "", semantic_text, flags=re.MULTILINE)
        semantic_text = re.sub(r"\s+", "", semantic_text)
        if len(semantic_text) < 4:
            empty_concepts += 1
            errors.append(
                {
                    "code": "empty-or-link-only-concept",
                    "path": str(concept.relative_to(book_root)),
                }
            )
        if str(concept.resolve()).casefold() not in referenced_concepts:
            errors.append(
                {
                    "code": "orphan-concept",
                    "path": str(concept.relative_to(book_root)),
                }
            )

    unreferenced_images = [
        str(path.relative_to(book_root))
        for path in all_images
        if str(path.resolve()).casefold() not in referenced_images
    ]
    if unreferenced_images:
        warnings.append(
            {
                "code": "unreferenced-images",
                "count": len(unreferenced_images),
                "samples": unreferenced_images[:30],
            }
        )

    canvas_paths = sorted(book_root.glob("*.canvas"))
    if require_canvas and not canvas_paths:
        errors.append({"code": "required-canvas-missing"})
    if len(canvas_paths) > 1:
        warnings.append(
            {
                "code": "multiple-book-root-canvases",
                "count": len(canvas_paths),
                "paths": [str(path) for path in canvas_paths],
            }
        )
    canvas_summaries: list[dict[str, Any]] = []
    for canvas_path in canvas_paths:
        summary, canvas_errors, canvas_warnings = audit_canvas(
            canvas_path,
            vault_root,
            book_root,
            allowed_node_colors=allowed_node_colors,
            allowed_edge_colors=allowed_edge_colors,
        )
        canvas_summaries.append(summary)
        errors.extend(canvas_errors)
        warnings.extend(canvas_warnings)

    report = {
        "status": "passed" if not errors else "failed",
        "book_root": str(book_root),
        "vault_root": str(vault_root),
        "source": source_summary,
        "profile": str(profile_path) if profile_path else None,
        "coverage": coverage_summary,
        "concept_manifest": concept_summary,
        "counts": {
            "markdown_files": len(markdown_files),
            "category_files": dict(sorted(category_files.items())),
            "concept_files": len(concept_files),
            "images": len(all_images),
            "standard_links": standard_links,
            "wikilinks": wikilinks,
            "image_references": image_references,
            "missing_markdown_links": missing_markdown_links,
            "missing_images": missing_images,
            "empty_notes": empty_notes,
            "empty_concepts": empty_concepts,
            "malformed_callouts": malformed_callouts,
            "callouts_without_blank": callouts_without_blank,
            "callouts": callouts,
            "unstandardized_functional_blocks": (
                unstandardized_functional_blocks
            ),
            "unreferenced_images": len(unreferenced_images),
        },
        "transitions": dict(sorted(transitions.items())),
        "canvases": canvas_summaries,
        "errors": errors,
        "warnings": warnings,
    }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit linked Markdown, assets, concepts, and canvases."
    )
    parser.add_argument("book_root", type=Path)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--expected-source-sha256")
    parser.add_argument("--allow-wikilinks", action="store_true")
    parser.add_argument("--require-canvas", action="store_true")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--coverage-manifest", type=Path)
    parser.add_argument("--concept-manifest", type=Path)
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = audit_book(
            args.book_root.resolve(),
            args.vault_root.resolve(),
            source=args.source.resolve() if args.source else None,
            expected_source_sha256=args.expected_source_sha256,
            allow_wikilinks=args.allow_wikilinks,
            require_canvas=args.require_canvas,
            coverage_manifest=(
                args.coverage_manifest.resolve() if args.coverage_manifest else None
            ),
            concept_manifest=(
                args.concept_manifest.resolve() if args.concept_manifest else None
            ),
            profile_path=args.profile.resolve() if args.profile else None,
        )
        output = json.dumps(report, ensure_ascii=False, indent=2)
        print(output)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(output + "\n", encoding="utf-8")
        return 0 if report["status"] == "passed" else 1
    except Exception as exc:
        report = {
            "status": "failed",
            "errors": [
                {
                    "code": "audit-crashed",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            ],
            "warnings": [],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
