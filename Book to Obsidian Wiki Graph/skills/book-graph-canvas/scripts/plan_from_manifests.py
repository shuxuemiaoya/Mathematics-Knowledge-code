#!/usr/bin/env python3
"""Plan a reviewable semantic canvas from split, concept, and domain manifests.

The script is corpus-independent.  Book-specific domain placement and semantic
relations live only in the reviewed ``canvas-plan.json`` passed by the caller.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any


CARD_WIDTH = 300
CARD_HEIGHT = 92
CARD_GAP_X = 36
CARD_GAP_Y = 34
CHAPTER_PADDING_X = 80
CHAPTER_PADDING_Y = 110
CHAPTER_GAP = 100
DOMAIN_PADDING_X = 100
DOMAIN_PADDING_Y = 120
DOMAIN_GAP_X = 180
DOMAIN_GAP_Y = 180


class PlanError(ValueError):
    """Raised when a reviewed canvas plan is incomplete or inconsistent."""


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PlanError(f"expected a JSON object: {path}")
    return payload


def encoded_vault_link(vault_root: Path, target: Path) -> str:
    relative = target.resolve().relative_to(vault_root.resolve()).as_posix()
    return "/" + urllib.parse.quote(relative, safe="/._-~()（）【】")


def category_directories(profile: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in profile.get("categories", []):
        if isinstance(item, dict) and item.get("enabled", True):
            result[str(item.get("role"))] = str(item.get("directory"))
    return result


def note_target(
    node: dict[str, Any], book_root: Path, category_dirs: dict[str, str]
) -> Path:
    filename = str(node["filename"])
    category = str(node.get("category", "root"))
    directory = category_dirs.get(category)
    return book_root / directory / filename if directory else book_root / filename


def descendants(
    chapter_key: str,
    children: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def visit(parent: str) -> None:
        for node in children.get(parent, []):
            result.append(node)
            visit(str(node["key"]))

    visit(chapter_key)
    return result


def color_for(category: str, profile: dict[str, Any], *, chapter: bool = False) -> str | None:
    colors = profile.get("canvas", {}).get("node_colors", {})
    role = {
        "knowledge": "knowledge_or_concept",
        "concept": "knowledge_or_concept",
        "exercise": "question_type",
        "method": "method",
        "reading": "reading",
        "tool": "tool",
    }.get(category)
    if chapter:
        role = "super_core"
    value = colors.get(role) if role else None
    return str(value) if value is not None else None


def add_text_node(
    nodes: list[dict[str, Any]],
    *,
    key: str,
    label: str,
    link: str,
    x: int,
    y: int,
    color: str | None,
) -> None:
    item: dict[str, Any] = {
        "key": key,
        "type": "text",
        "text": f"[{label}]({link})",
        "x": x,
        "y": y,
        "width": CARD_WIDTH,
        "height": CARD_HEIGHT,
    }
    if color:
        item["color"] = color
    nodes.append(item)


def plan_manifest(
    profile_path: Path,
    split_path: Path,
    concept_path: Path,
    plan_path: Path,
) -> dict[str, Any]:
    profile = read_json(profile_path)
    split = read_json(split_path)
    concepts = read_json(concept_path)
    plan = read_json(plan_path)

    if plan.get("version") != 1:
        raise PlanError("canvas plan version must be 1")
    source_sha = str(profile.get("source", {}).get("sha256", ""))
    for name, payload in (("split", split), ("concept", concepts)):
        if payload.get("source_sha256") != source_sha:
            raise PlanError(f"{name} manifest source digest does not match profile")

    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    book_root = Path(profile["paths"]["book_root"]).resolve()
    category_dirs = category_directories(profile)
    split_nodes = split.get("nodes", [])
    by_key = {str(item["key"]): item for item in split_nodes}
    if "book-root" not in by_key:
        raise PlanError("split manifest has no book-root")

    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in split_nodes:
        parent = item.get("parent_key")
        if parent is not None:
            children[str(parent)].append(item)

    planned_chapters = [
        str(key)
        for domain in plan.get("domains", [])
        for key in domain.get("chapters", [])
    ]
    available_chapters = {
        str(item["key"])
        for item in children["book-root"]
        if item.get("category") == "knowledge"
    }
    if set(planned_chapters) != available_chapters:
        missing = sorted(available_chapters - set(planned_chapters))
        extra = sorted(set(planned_chapters) - available_chapters)
        raise PlanError(f"domain chapter coverage mismatch; missing={missing}, extra={extra}")
    if len(planned_chapters) != len(set(planned_chapters)):
        raise PlanError("a chapter appears in more than one domain")

    extras = [
        str(key)
        for domain in plan.get("domains", [])
        for key in domain.get("extras", [])
    ]
    if any(key not in by_key for key in extras):
        raise PlanError("domain extras contain an unknown split node key")

    concepts_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for concept in concepts.get("concepts", []):
        concepts_by_source[str(concept["definition_source"]).replace("\\", "/")].append(concept)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    placed_split_keys: set[str] = set()
    split_card_keys: dict[str, str] = {}
    concept_card_keys: dict[str, str] = {}

    root = by_key["book-root"]
    add_text_node(
        nodes,
        key="book-overview",
        label=str(root["title"]),
        link=encoded_vault_link(vault_root, note_target(root, book_root, category_dirs)),
        x=-430,
        y=40,
        color=color_for("knowledge", profile, chapter=True),
    )

    domain_specs = plan.get("domains", [])
    domain_columns = 2 if len(domain_specs) > 1 else 1
    column_y = [0 for _ in range(domain_columns)]

    for domain_index, domain in enumerate(domain_specs):
        column = domain_index % domain_columns
        domain_x = column * 2600
        domain_y = column_y[column]
        chapter_layouts: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]], int, int]] = []
        domain_width = 0
        domain_height = DOMAIN_PADDING_Y

        for chapter_key in domain.get("chapters", []):
            chapter = by_key[str(chapter_key)]
            split_items = [chapter] + descendants(str(chapter_key), children)
            source_paths = {
                str(note_target(item, book_root, category_dirs).relative_to(book_root)).replace("\\", "/"): item
                for item in split_items
            }
            concept_items = [
                concept
                for source in source_paths
                for concept in concepts_by_source.get(source, [])
            ]
            card_count = len(split_items) + len(concept_items)
            columns = max(3, min(6, math.ceil(math.sqrt(max(card_count, 1) * 1.8))))
            rows = math.ceil(card_count / columns)
            chapter_width = CHAPTER_PADDING_X * 2 + columns * CARD_WIDTH + (columns - 1) * CARD_GAP_X
            chapter_height = CHAPTER_PADDING_Y + rows * CARD_HEIGHT + max(rows - 1, 0) * CARD_GAP_Y + 60
            chapter_layouts.append((str(chapter_key), split_items, concept_items, chapter_width, chapter_height))
            domain_width = max(domain_width, chapter_width + DOMAIN_PADDING_X * 2)
            domain_height += chapter_height + CHAPTER_GAP

        domain_height -= CHAPTER_GAP
        for extra_key in domain.get("extras", []):
            if str(extra_key) not in placed_split_keys:
                domain_height += CARD_HEIGHT + CARD_GAP_Y

        domain_key = f"domain-{domain['key']}"
        nodes.append(
            {
                "key": domain_key,
                "type": "group",
                "label": str(domain["label"]),
                "x": domain_x,
                "y": domain_y,
                "width": domain_width,
                "height": domain_height,
            }
        )

        cursor_y = domain_y + DOMAIN_PADDING_Y
        first_chapter_card: str | None = None
        for chapter_key, split_items, concept_items, chapter_width, chapter_height in chapter_layouts:
            chapter = by_key[chapter_key]
            chapter_group_key = f"group-{chapter_key}"
            chapter_x = domain_x + DOMAIN_PADDING_X
            nodes.append(
                {
                    "key": chapter_group_key,
                    "type": "group",
                    "label": str(chapter["title"]),
                    "x": chapter_x,
                    "y": cursor_y,
                    "width": chapter_width,
                    "height": chapter_height,
                }
            )

            all_cards: list[tuple[str, str, str, str, str | None]] = []
            for item in split_items:
                split_key = str(item["key"])
                card_key = f"note-{split_key}"
                split_card_keys[split_key] = card_key
                placed_split_keys.add(split_key)
                all_cards.append(
                    (
                        card_key,
                        str(item["title"]),
                        encoded_vault_link(vault_root, note_target(item, book_root, category_dirs)),
                        str(item.get("category", "root")),
                        split_key,
                    )
                )
            for concept in concept_items:
                target = str(concept["target"]).replace("\\", "/")
                card_key = "concept-" + urllib.parse.quote(target, safe="").replace("%", "_")
                concept_card_keys[target] = card_key
                all_cards.append(
                    (
                        card_key,
                        str(concept["name"]),
                        encoded_vault_link(vault_root, book_root / Path(target)),
                        "concept",
                        target,
                    )
                )

            columns = max(3, min(6, math.ceil(math.sqrt(max(len(all_cards), 1) * 1.8))))
            for index, (card_key, label, link, category, _) in enumerate(all_cards):
                row, col = divmod(index, columns)
                add_text_node(
                    nodes,
                    key=card_key,
                    label=label,
                    link=link,
                    x=chapter_x + CHAPTER_PADDING_X + col * (CARD_WIDTH + CARD_GAP_X),
                    y=cursor_y + CHAPTER_PADDING_Y + row * (CARD_HEIGHT + CARD_GAP_Y),
                    color=color_for(category, profile, chapter=card_key == f"note-{chapter_key}"),
                )
            first_chapter_card = first_chapter_card or split_card_keys[chapter_key]
            cursor_y += chapter_height + CHAPTER_GAP

        for extra_key in domain.get("extras", []):
            extra = by_key[str(extra_key)]
            card_key = f"note-{extra_key}"
            split_card_keys[str(extra_key)] = card_key
            placed_split_keys.add(str(extra_key))
            add_text_node(
                nodes,
                key=card_key,
                label=str(extra["title"]),
                link=encoded_vault_link(vault_root, note_target(extra, book_root, category_dirs)),
                x=domain_x + DOMAIN_PADDING_X,
                y=cursor_y,
                color=color_for(str(extra.get("category", "method")), profile),
            )
            cursor_y += CARD_HEIGHT + CARD_GAP_Y

        if first_chapter_card:
            edges.append(
                {
                    "key": f"book-to-{domain_key}",
                    "from": "book-overview",
                    "to": first_chapter_card,
                    "fromSide": "right",
                    "toSide": "left",
                }
            )
        column_y[column] = domain_y + domain_height + DOMAIN_GAP_Y

    for item in split_nodes:
        key = str(item["key"])
        parent = item.get("parent_key")
        if key not in placed_split_keys or parent not in placed_split_keys:
            continue
        edges.append(
            {
                "key": f"hierarchy-{parent}-to-{key}",
                "from": split_card_keys[str(parent)],
                "to": split_card_keys[key],
                "fromSide": "bottom",
                "toSide": "top",
            }
        )

    for concept in concepts.get("concepts", []):
        target = str(concept["target"]).replace("\\", "/")
        source_key = str(concept.get("definition_unit", ""))
        if source_key in split_card_keys and target in concept_card_keys:
            edges.append(
                {
                    "key": f"definition-{source_key}-{concept_card_keys[target]}",
                    "from": split_card_keys[source_key],
                    "to": concept_card_keys[target],
                    "label": "定义",
                    "fromSide": "right",
                    "toSide": "left",
                }
            )

    edge_colors = profile.get("canvas", {}).get("edge_colors", {})
    relation_color_keys = {
        "reasoning": "reasoning",
        "method_transfer": "method_transfer",
        "calculation": "calculation",
        "application": "application",
    }
    for index, relation in enumerate(plan.get("relations", []), start=1):
        source = str(relation["from"])
        target = str(relation["to"])
        if source not in split_card_keys or target not in split_card_keys:
            raise PlanError(f"relation endpoint is not placed: {source} -> {target}")
        edge: dict[str, Any] = {
            "key": str(relation.get("key", f"semantic-{index:03d}")),
            "from": split_card_keys[source],
            "to": split_card_keys[target],
            "label": str(relation["label"]),
            "fromSide": str(relation.get("fromSide", "right")),
            "toSide": str(relation.get("toSide", "left")),
        }
        color_role = relation.get("color")
        if color_role:
            profile_key = relation_color_keys.get(str(color_role), str(color_role))
            if profile_key not in edge_colors:
                raise PlanError(f"relation uses an unavailable edge color role: {color_role}")
            edge["color"] = str(edge_colors[profile_key])
        edges.append(edge)

    return {
        "version": 1,
        "profile": str(profile_path.resolve()),
        "source_sha256": source_sha,
        "planning_basis": {
            "split_manifest": str(split_path.resolve()),
            "concept_manifest": str(concept_path.resolve()),
            "reviewed_canvas_plan": str(plan_path.resolve()),
            "domain_count": len(domain_specs),
            "placed_split_notes": len(placed_split_keys),
            "placed_concepts": len(concept_card_keys),
            "semantic_relations": len(plan.get("relations", [])),
        },
        "nodes": nodes,
        "edges": edges,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan a semantic canvas from reviewed domain assignments and manifests."
    )
    parser.add_argument("profile", type=Path)
    parser.add_argument("split_manifest", type=Path)
    parser.add_argument("concept_manifest", type=Path)
    parser.add_argument("canvas_plan", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"output already exists: {args.output}")
    manifest = plan_manifest(
        args.profile.resolve(),
        args.split_manifest.resolve(),
        args.concept_manifest.resolve(),
        args.canvas_plan.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "planned",
                "output": str(args.output.resolve()),
                "nodes": len(manifest["nodes"]),
                "groups": sum(1 for item in manifest["nodes"] if item["type"] == "group"),
                "edges": len(manifest["edges"]),
                "planning_basis": manifest["planning_basis"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
