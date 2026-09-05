#!/usr/bin/env python3
"""Build a level-of-detail learning constellation from a reviewed book graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from validate_book_graph import load_json, validate_graph


ATOM_COLORS = {"knowledge": "2", "worked-example": "4", "exercise": "6", "scenario": "5"}
ATOM_LABELS = {"knowledge": "知识点", "worked-example": "例题", "exercise": "习题", "scenario": "情景引入"}
RELATION_LABELS = {
    "prerequisite": "先修", "develops": "发展", "derives": "推导",
    "motivates": "引发", "illustrates": "例证", "applies": "应用",
    "practices": "练习", "contrasts": "对比", "analogous": "类比",
}
RELATION_COLORS = {
    "prerequisite": "1", "develops": "2", "derives": "4",
    "motivates": "5", "illustrates": "4", "applies": "4",
    "practices": "6", "contrasts": "1", "analogous": "5",
}
CONCEPT_RELATION_LABELS = {
    "prerequisite": "先修", "develops": "发展", "derives": "推导",
    "broader": "上位", "part_of": "组成", "contrasts": "对比", "analogous": "类比",
}
CONCEPT_ROLE_LABELS = {
    "introduces": "引入", "explains": "解释", "derives": "推导",
    "triggered_by": "触发", "motivates": "引发", "illustrates": "例证",
    "applies": "应用", "practices": "练习", "assumes": "前置",
}
SYMMETRIC_RELATIONS = {"contrasts", "analogous"}
ORGANIZER_COLOR = "1"
BACKBONE_COLOR = "3"
SOURCE_ORDER_COLOR = "#7A7A7A"
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))

CHAPTER_WIDTH, CHAPTER_HEIGHT = 360, 120
ATOM_WIDTH, ATOM_HEIGHT = 250, 66
CORE_WIDTH, CORE_HEIGHT = 280, 78
LANDMARK_WIDTH, LANDMARK_HEIGHT = 220, 60
PORTAL_WIDTH, PORTAL_HEIGHT = 250, 66
EXERCISE_WIDTH, EXERCISE_HEIGHT = 260, 72
JUNCTION_WIDTH, JUNCTION_HEIGHT = 210, 60
CONCEPT_WIDTH, CONCEPT_HEIGHT = 230, 76
GROUP_PADDING = 130
NODE_MARGIN = 72


def stable_id(kind: str, key: str) -> str:
    return hashlib.sha256(f"{kind}:{key}".encode("utf-8")).hexdigest()[:16]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encode_href(value: str) -> str:
    return urllib.parse.quote(value.replace("\\", "/"), safe="/._-~,")


def escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


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
        mode="w", encoding="utf-8", newline="\n", prefix=f".{path.name}.",
        suffix=".tmp", dir=path.parent, delete=False,
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


def node_source_start(nodes: dict[str, dict[str, Any]], key: str, memo: dict[str, int]) -> int:
    if key in memo:
        return memo[key]
    node = nodes[key]
    candidates: list[int] = []
    if node.get("layer") == "atom":
        candidates.append(int(node["source_range"][0]))
    else:
        candidates.extend(int(item[0]) for item in node.get("heading_ranges", []))
        candidates.extend(node_source_start(nodes, str(child), memo) for child in node.get("children", []))
    if not candidates:
        raise ValueError(f"Node has no source anchor: {key}")
    memo[key] = min(candidates)
    return memo[key]


def rectangle(position: tuple[int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    return position[0], position[1], position[0] + size[0], position[1] + size[1]


def overlaps(left: tuple[int, int, int, int], right: tuple[int, int, int, int], margin: int = NODE_MARGIN) -> bool:
    return not (left[2] + margin <= right[0] or right[2] + margin <= left[0] or left[3] + margin <= right[1] or right[3] + margin <= left[1])


def collision_free(preferred: tuple[float, float], size: tuple[int, int], occupied: list[tuple[int, int, int, int]], seed_index: int) -> tuple[int, int]:
    for attempt in range(900):
        if attempt == 0:
            x, y = preferred
        else:
            radius = 110 + 70 * math.sqrt(attempt)
            angle = (seed_index + attempt) * GOLDEN_ANGLE
            x = preferred[0] + radius * math.cos(angle)
            y = preferred[1] + radius * math.sin(angle)
        candidate = rectangle((round(x), round(y)), size)
        if not any(overlaps(candidate, existing) for existing in occupied):
            occupied.append(candidate)
            return round(x), round(y)
    raise ValueError("Could not place Canvas node without overlap")


def bounds_for(nodes: Iterable[dict[str, Any]]) -> dict[str, int | float]:
    items = [node for node in nodes if node.get("type") in {"text", "group", "file", "link"}]
    if not items:
        return {"x": 0, "y": 0, "width": 0, "height": 0, "aspect_ratio": 1.0}
    min_x = min(int(node["x"]) for node in items)
    min_y = min(int(node["y"]) for node in items)
    max_x = max(int(node["x"]) + int(node["width"]) for node in items)
    max_y = max(int(node["y"]) + int(node["height"]) for node in items)
    width, height = max_x - min_x, max_y - min_y
    return {"x": min_x, "y": min_y, "width": width, "height": height, "aspect_ratio": round(width / height, 4) if height else 1.0}


class CanvasBundleBuilder:
    def __init__(self, manifest: dict[str, Any], manifest_path: Path, book_root: Path, output_dir: Path) -> None:
        self.manifest, self.manifest_path, self.book_root, self.output_dir = manifest, manifest_path, book_root, output_dir
        self.nodes = {str(node["key"]): node for node in manifest["nodes"] if isinstance(node, dict) and isinstance(node.get("key"), str)}
        roots = [node for node in self.nodes.values() if node.get("parent_key") is None]
        if len(roots) != 1 or roots[0].get("layer") != "organizer":
            raise ValueError("Canvas bundle needs exactly one root organizer")
        self.root_key = str(roots[0]["key"])
        self.source_starts: dict[str, int] = {}
        for key in self.nodes:
            node_source_start(self.nodes, key, self.source_starts)
        root_children = [str(key) for key in self.nodes[self.root_key].get("children", [])]
        root_atoms = [key for key in root_children if self.nodes[key].get("layer") == "atom"]
        if root_atoms:
            raise ValueError(f"Canvas atlas requires chapter ownership for every atom: {root_atoms}")
        self.chapter_keys = [key for key in root_children if self.nodes[key].get("layer") == "organizer"]
        if not self.chapter_keys:
            raise ValueError("Canvas bundle needs at least one chapter organizer")
        self.chapter_paths = self._chapter_paths()
        review = manifest.get("relation_review")
        self.semantic_ready = isinstance(review, dict) and review.get("status") == "passed" and review.get("unresolved_count") == 0
        self.relations = list(manifest.get("relations", [])) if self.semantic_ready else []
        self.concepts = {
            str(item["key"]): item for item in manifest.get("concepts", [])
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        } if self.semantic_ready else {}
        self.atom_concept_links = list(manifest.get("atom_concept_links", [])) if self.semantic_ready else []
        self.concept_relations = list(manifest.get("concept_relations", [])) if self.semantic_ready else []
        self.dual_layer = bool(
            self.concepts and isinstance(review, dict)
            and review.get("graph_model") == "atom-concept-dual-layer"
        )
        featured = review.get("featured_example_keys", []) if isinstance(review, dict) else []
        self.featured_examples = {
            str(key) for key in featured
            if str(key) in self.nodes and self.nodes[str(key)].get("category") == "worked-example"
        }
        self.atom_chapter = {key: self._chapter_for(key) for key, node in self.nodes.items() if node.get("layer") == "atom"}
        self.links_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for link in self.atom_concept_links:
            if str(link.get("concept_key")) in self.concepts and str(link.get("atom_key")) in self.atom_chapter:
                self.links_by_concept[str(link["concept_key"])].append(link)
        self.concept_relation_by_key = {
            str(item["key"]): item for item in self.concept_relations if isinstance(item, dict) and item.get("key")
        }

    def _chapter_paths(self) -> dict[str, Path]:
        width = max(2, len(str(len(self.chapter_keys))))
        result: dict[str, Path] = {}
        for index, key in enumerate(self.chapter_keys, start=1):
            title = safe_filename(str(self.nodes[key]["title"]), "chapter")
            result[key] = self.output_dir / "chapters" / f"{index:0{width}d}-{title}-{stable_id('chapter', key)[:6]}.canvas"
        return result

    def _chapter_for(self, key: str) -> str:
        cursor = key
        parent = self.nodes[cursor].get("parent_key")
        while parent is not None and str(parent) != self.root_key:
            cursor = str(parent)
            parent = self.nodes[cursor].get("parent_key")
        if parent is None:
            raise ValueError(f"Node is outside chapter ownership: {key}")
        return cursor

    def link_text(self, label: str, target: Path, canvas_path: Path) -> str:
        href = os.path.relpath(target.resolve(), canvas_path.parent).replace("\\", "/")
        return f"[{escape_label(label)}]({encode_href(href)})"

    def note_target(self, key: str) -> Path:
        return (self.book_root / str(self.nodes[key]["filename"])).resolve()

    def visible_atom(self, key: str) -> bool:
        category = self.nodes[key].get("category")
        return category in {"knowledge", "scenario"} or key in self.featured_examples

    def descendant_atoms(self, organizer_key: str) -> list[str]:
        return [
            key for key in descendants(self.nodes, organizer_key)[1:]
            if self.nodes[key].get("layer") == "atom"
        ]

    def exercise_owners(self, chapter_key: str, exercise_atoms: list[str]) -> tuple[dict[str, str], dict[str, list[str]]]:
        """Collapse every exercise atom into the highest exercise-only organizer available."""
        categories: dict[str, set[str]] = {}

        def organizer_categories(key: str) -> set[str]:
            if key not in categories:
                categories[key] = {
                    str(self.nodes[atom].get("category"))
                    for atom in self.descendant_atoms(key)
                }
            return categories[key]

        owner_by_atom: dict[str, str] = {}
        atoms_by_owner: dict[str, list[str]] = defaultdict(list)
        for atom_key in exercise_atoms:
            cursor = str(self.nodes[atom_key]["parent_key"])
            owner = cursor
            while cursor != chapter_key and organizer_categories(cursor) == {"exercise"}:
                owner = cursor
                parent = self.nodes[cursor].get("parent_key")
                if parent is None or str(parent) == chapter_key:
                    break
                cursor = str(parent)
            owner_by_atom[atom_key] = owner
            atoms_by_owner[owner].append(atom_key)
        for values in atoms_by_owner.values():
            values.sort(key=lambda key: (self.source_starts[key], key))
        return owner_by_atom, dict(atoms_by_owner)

    def is_core(self, key: str) -> bool:
        return any(relation.get("tier") == "backbone" and key in {relation.get("from_key"), relation.get("to_key")} for relation in self.relations)

    def atom_card(self, key: str, canvas_path: Path, position: tuple[int, int], external: bool = False) -> dict[str, Any]:
        node = self.nodes[key]
        category = str(node["category"])
        core = self.is_core(key)
        width, height = (CORE_WIDTH, CORE_HEIGHT) if core and not external else ((PORTAL_WIDTH, PORTAL_HEIGHT) if external else (ATOM_WIDTH, ATOM_HEIGHT))
        prefix = "↗ 外章" if external else ("✦" if core else "·")
        return {
            "id": stable_id("external" if external else "card", key), "type": "text",
            "text": self.link_text(f"{prefix} {ATOM_LABELS[category]} · {node['title']}", self.note_target(key), canvas_path),
            "x": position[0], "y": position[1], "width": width, "height": height,
            "color": ATOM_COLORS[category] if not external else SOURCE_ORDER_COLOR,
        }

    def landmark_card(self, key: str, canvas_path: Path, position: tuple[int, int]) -> dict[str, Any]:
        return {
            "id": stable_id("landmark", key), "type": "text",
            "text": self.link_text(f"§ {self.nodes[key]['title']}", self.note_target(key), canvas_path),
            "x": position[0], "y": position[1], "width": LANDMARK_WIDTH, "height": LANDMARK_HEIGHT,
            "color": ORGANIZER_COLOR,
        }

    def exercise_card(self, key: str, atom_count: int, canvas_path: Path, position: tuple[int, int]) -> dict[str, Any]:
        return {
            "id": stable_id("exercise-organizer", key), "type": "text",
            "text": self.link_text(f"练习星群 · {self.nodes[key]['title']}", self.note_target(key), canvas_path) + f"\n\n共 {atom_count} 个练习原子",
            "x": position[0], "y": position[1], "width": EXERCISE_WIDTH, "height": EXERCISE_HEIGHT,
            "color": ATOM_COLORS["exercise"],
        }

    def junction_card(self, owner_key: str, knowledge_count: int, exercise_count: int, position: tuple[int, int]) -> dict[str, Any]:
        return {
            "id": stable_id("junction", owner_key), "type": "text",
            "text": f"✧ 综合练习汇合\n\n{knowledge_count} 个知识点 · {exercise_count} 题",
            "x": position[0], "y": position[1], "width": JUNCTION_WIDTH, "height": JUNCTION_HEIGHT,
            "color": ATOM_COLORS["exercise"],
        }

    def concept_card(self, key: str, position: tuple[int, int]) -> dict[str, Any]:
        concept = self.concepts[key]
        return {
            "id": stable_id("concept", key), "type": "text",
            "text": f"✦ 规范概念\n\n**{concept['preferred_label']}**\n`{concept['kind']}`",
            "x": position[0], "y": position[1], "width": CONCEPT_WIDTH, "height": CONCEPT_HEIGHT,
            "color": BACKBONE_COLOR,
        }

    def concept_is_hub(self, key: str) -> bool:
        links = self.links_by_concept.get(key, [])
        visible_atoms = {
            str(link["atom_key"]) for link in links
            if self.nodes[str(link["atom_key"])].get("category") != "worked-example"
            or str(link["atom_key"]) in self.featured_examples
        }
        degree = sum(key in {str(item.get("from_key")), str(item.get("to_key"))} for item in self.concept_relations)
        regions = {
            (self.atom_chapter[atom], self.section_for(self.atom_chapter[atom], atom))
            for atom in visible_atoms
        }
        chapters = {self.atom_chapter[atom] for atom in visible_atoms}
        cross_chapter = len(chapters) >= 2 or any(
            key in {str(item.get("from_key")), str(item.get("to_key"))}
            and self.concept_chapters(str(item.get("from_key"))) != self.concept_chapters(str(item.get("to_key")))
            for item in self.concept_relations
        )
        return len(visible_atoms) >= 2 or degree >= 3 or len(regions) >= 2 or cross_chapter

    def concept_chapters(self, key: str) -> set[str]:
        return {
            self.atom_chapter[str(link["atom_key"])]
            for link in self.links_by_concept.get(key, [])
            if str(link.get("atom_key")) in self.atom_chapter
        }

    def concept_edge(self, relation: dict[str, Any], from_id: str, to_id: str, scope: str) -> dict[str, Any]:
        relation_type, tier = str(relation["type"]), str(relation["tier"])
        vertical = relation_type in {"broader", "part_of", "contrasts", "analogous"}
        return {
            "id": stable_id("edge", f"{scope}:concept:{relation['key']}:{from_id}:{to_id}"),
            "fromNode": from_id, "toNode": to_id,
            "fromSide": "bottom" if vertical else "right", "toSide": "top" if vertical else "left",
            "label": ("主线 · " if tier == "backbone" else "") + CONCEPT_RELATION_LABELS[relation_type],
            "color": BACKBONE_COLOR if tier == "backbone" else RELATION_COLORS.get(relation_type, ORGANIZER_COLOR),
            "fromEnd": "none", "toEnd": "none" if relation_type in SYMMETRIC_RELATIONS else "arrow",
        }

    def concept_membership_edge(self, chapter_key: str, concept_key: str, endpoint_id: str, role: str, atom_key: str) -> dict[str, Any]:
        producer = role in {"introduces", "explains", "derives", "motivates"}
        return {
            "id": stable_id("edge", f"{chapter_key}:concept-link:{concept_key}:{endpoint_id}:{role}:{atom_key}"),
            "fromNode": endpoint_id if producer else stable_id("concept", concept_key),
            "toNode": stable_id("concept", concept_key) if producer else endpoint_id,
            "fromSide": "bottom", "toSide": "top",
            "label": CONCEPT_ROLE_LABELS[role], "color": SOURCE_ORDER_COLOR,
            "fromEnd": "none", "toEnd": "arrow",
        }

    def relation_edge(self, relation: dict[str, Any], from_id: str, to_id: str, scope: str) -> dict[str, Any]:
        relation_type, tier = str(relation["type"]), str(relation["tier"])
        if relation_type == "motivates":
            from_side, to_side = "right", "top"
        elif relation_type in {"illustrates", "applies", "practices", "contrasts", "analogous"}:
            from_side, to_side = "bottom", "top"
        else:
            from_side, to_side = "right", "left"
        return {
            "id": stable_id("edge", f"{scope}:relation:{relation['key']}"),
            "fromNode": from_id, "toNode": to_id,
            "fromSide": from_side, "toSide": to_side,
            "label": ("主线 · " if tier == "backbone" else "") + RELATION_LABELS[relation_type],
            "color": BACKBONE_COLOR if tier == "backbone" else RELATION_COLORS[relation_type],
            "fromEnd": "none", "toEnd": "none" if relation_type in SYMMETRIC_RELATIONS else "arrow",
        }

    def exercise_edge(self, chapter_key: str, owner_key: str, from_id: str, to_id: str, label: str, suffix: str) -> dict[str, Any]:
        return {
            "id": stable_id("edge", f"{chapter_key}:exercise:{owner_key}:{suffix}"),
            "fromNode": from_id, "toNode": to_id,
            "fromSide": "bottom", "toSide": "top",
            "label": label, "color": ATOM_COLORS["exercise"],
            "fromEnd": "none", "toEnd": "arrow",
        }

    def landmark_edge(self, chapter_key: str, landmark_key: str, target_id: str) -> dict[str, Any]:
        return {
            "id": stable_id("edge", f"{chapter_key}:landmark:{landmark_key}:{target_id}"),
            "fromNode": stable_id("landmark", landmark_key), "toNode": target_id,
            "fromSide": "bottom", "toSide": "top",
            "label": "包含", "color": SOURCE_ORDER_COLOR,
            "fromEnd": "none", "toEnd": "arrow",
        }

    def overview_canvas(self, canvas_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        cards: list[dict[str, Any]] = [{
            "id": stable_id("atlas", self.root_key), "type": "text",
            "text": f"# ✦ {self.nodes[self.root_key]['title']}\n\n全书知识星图",
            "x": -190, "y": -80, "width": 380, "height": 160, "color": ORGANIZER_COLOR,
        }]
        count = len(self.chapter_keys)
        for index, key in enumerate(self.chapter_keys):
            ring, within = index // 12, index % 12
            ring_count = min(12, count - ring * 12)
            angle = -math.pi / 2 + (2 * math.pi * within / max(ring_count, 1)) + ring * 0.19
            radius = 720 + ring * 620
            x, y = round(radius * math.cos(angle) - CHAPTER_WIDTH / 2), round(radius * math.sin(angle) - CHAPTER_HEIGHT / 2)
            ready_label = "" if self.semantic_ready else " · 关系待复核"
            target = self.chapter_paths[key] if self.semantic_ready else self.note_target(key)
            cards.append({
                "id": stable_id("chapter", key), "type": "text",
                "text": self.link_text(f"## ✦ {self.nodes[key]['title']}{ready_label}", target, canvas_path),
                "x": x, "y": y, "width": CHAPTER_WIDTH, "height": CHAPTER_HEIGHT, "color": ORGANIZER_COLOR,
            })
        cards.append({
            "id": stable_id("utility", "atlas-legend"), "type": "text",
            "text": "**图例**\n\n黄色：主学习路线  ·  灰色：原书顺序\n彩色：跨章知识联系",
            "x": -180, "y": 150, "width": 360, "height": 180,
        })
        edges: list[dict[str, Any]] = []
        for left, right in zip(self.chapter_keys, self.chapter_keys[1:]):
            edges.append({
                "id": stable_id("edge", f"atlas:source-order:{left}:{right}"),
                "fromNode": stable_id("chapter", left), "toNode": stable_id("chapter", right),
                "fromSide": "right", "toSide": "left",
                "label": "书序", "color": SOURCE_ORDER_COLOR, "fromEnd": "none", "toEnd": "arrow",
            })
        aggregation: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for relation in self.relations:
            if not self.visible_atom(str(relation["from_key"])) or not self.visible_atom(str(relation["to_key"])):
                continue
            left, right = self.atom_chapter[str(relation["from_key"])], self.atom_chapter[str(relation["to_key"])]
            if left != right:
                aggregation[(left, right, str(relation["tier"]))].append(relation)
        for (left, right, tier), relations in sorted(aggregation.items()):
            types = sorted({RELATION_LABELS[str(relation["type"])] for relation in relations})
            edges.append({
                "id": stable_id("edge", f"atlas:aggregate:{left}:{right}:{tier}"),
                "fromNode": stable_id("chapter", left), "toNode": stable_id("chapter", right),
                "fromSide": "right", "toSide": "top" if any(item["type"] == "motivates" for item in relations) else "left",
                "label": ("主线 · " if tier == "backbone" else "") + "/".join(types) + f" ×{len(relations)}",
                "color": BACKBONE_COLOR if tier == "backbone" else RELATION_COLORS[str(relations[0]["type"])],
                "fromEnd": "none", "toEnd": "arrow",
            })
        counts = {
            "cards": len(cards), "groups": 0, "edges": len(edges), "organizers": 1 + len(self.chapter_keys),
            "atoms": 0, "internal_atoms": 0, "external_portals": 0, "landmarks": 0,
            "navigation_nodes": 2, "regions": 0,
            "backbone_edges": sum("主线" in str(edge.get("label")) for edge in edges),
            "supporting_edges": sum(edge.get("label") != "书序" and "主线" not in str(edge.get("label")) for edge in edges),
            "source_order_edges": sum(edge.get("label") == "书序" for edge in edges),
            "semantic_edges": sum(edge.get("label") != "书序" for edge in edges), "landmark_edges": 0,
        }
        return {"nodes": cards, "edges": edges}, {"counts": counts, "bounds": bounds_for(cards)}

    def section_for(self, chapter_key: str, key: str) -> str:
        if key == chapter_key:
            return "__chapter_intro__"
        cursor = key
        parent = self.nodes[cursor].get("parent_key")
        if parent is not None and str(parent) == chapter_key and self.nodes[cursor].get("layer") == "atom":
            return "__chapter_intro__"
        while parent is not None and str(parent) != chapter_key:
            cursor = str(parent)
            parent = self.nodes[cursor].get("parent_key")
        return cursor if parent is not None else "__chapter_intro__"

    def topological_core_order(self, atom_keys: list[str], relations: list[dict[str, Any]]) -> list[str]:
        core = {key for key in atom_keys if self.nodes[key].get("category") in {"knowledge", "scenario"}}
        indegree = {key: 0 for key in core}
        adjacency: dict[str, list[str]] = defaultdict(list)
        for relation in relations:
            left, right = str(relation["from_key"]), str(relation["to_key"])
            if relation.get("tier") == "backbone" and left in core and right in core:
                adjacency[left].append(right)
                indegree[right] += 1
        queue = sorted((key for key in core if indegree[key] == 0), key=lambda key: (self.source_starts[key], key))
        result: list[str] = []
        while queue:
            key = queue.pop(0)
            result.append(key)
            for child in sorted(adjacency.get(key, []), key=lambda item: (self.source_starts[item], item)):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
                    queue.sort(key=lambda item: (self.source_starts[item], item))
        result.extend(sorted(core - set(result), key=lambda key: (self.source_starts[key], key)))
        return result

    def layout_region(
        self,
        atom_keys: list[str],
        landmark_keys: list[str],
        relations: list[dict[str, Any]],
        exercise_anchors: dict[str, list[str]],
        exercise_counts: dict[str, int],
    ) -> tuple[
        dict[str, tuple[int, int]],
        dict[str, tuple[int, int]],
        dict[str, tuple[int, int]],
        dict[str, tuple[int, int]],
        tuple[int, int, int, int],
    ]:
        atom_positions: dict[str, tuple[int, int]] = {}
        landmark_positions: dict[str, tuple[int, int]] = {}
        exercise_positions: dict[str, tuple[int, int]] = {}
        junction_positions: dict[str, tuple[int, int]] = {}
        occupied: list[tuple[int, int, int, int]] = []
        core_order = self.topological_core_order(atom_keys, relations)
        core_set = set(core_order)
        for index, key in enumerate(core_order):
            radius, angle = 90 + 145 * math.sqrt(index), index * GOLDEN_ANGLE
            atom_positions[key] = collision_free((radius * math.cos(angle), radius * math.sin(angle)), (CORE_WIDTH, CORE_HEIGHT), occupied, index)
        anchors: dict[str, list[str]] = defaultdict(list)
        for relation in relations:
            left, right = str(relation["from_key"]), str(relation["to_key"])
            if left in core_set and right in atom_keys and right not in core_set:
                anchors[right].append(left)
            if right in core_set and left in atom_keys and left not in core_set:
                anchors[left].append(right)
        satellites = sorted((key for key in atom_keys if key not in core_set), key=lambda key: (self.source_starts[key], key))
        for index, key in enumerate(satellites):
            candidates = anchors.get(key, [])
            if candidates:
                anchor = min(candidates, key=lambda item: abs(self.source_starts[item] - self.source_starts[key]))
                base = atom_positions[anchor]
                angle = (index + int(stable_id("angle", key)[:4], 16)) * GOLDEN_ANGLE
                preferred = (base[0] + 270 * math.cos(angle), base[1] + 270 * math.sin(angle))
            else:
                offset = len(core_order) + index
                radius, angle = 260 + 150 * math.sqrt(offset), offset * GOLDEN_ANGLE
                preferred = (radius * math.cos(angle), radius * math.sin(angle))
            atom_positions[key] = collision_free(preferred, (ATOM_WIDTH, ATOM_HEIGHT), occupied, len(core_order) + index)
        for index, owner_key in enumerate(sorted(exercise_counts, key=lambda key: (self.source_starts[key], key))):
            raw_anchors = list(dict.fromkeys(exercise_anchors.get(owner_key, [])))
            anchors_for_owner = [key for key in raw_anchors if key in atom_positions]
            anchors_for_owner = list(dict.fromkeys(anchors_for_owner))
            seed_index = len(atom_keys) + index * 2
            if anchors_for_owner:
                center_x = sum(atom_positions[key][0] for key in anchors_for_owner) / len(anchors_for_owner)
                center_y = sum(atom_positions[key][1] for key in anchors_for_owner) / len(anchors_for_owner)
            else:
                angle = seed_index * GOLDEN_ANGLE
                center_x, center_y = 430 * math.cos(angle), 430 * math.sin(angle)
            if len(raw_anchors) > 1:
                junction = collision_free((center_x, center_y + 230), (JUNCTION_WIDTH, JUNCTION_HEIGHT), occupied, seed_index)
                junction_positions[owner_key] = junction
                preferred = (junction[0], junction[1] + JUNCTION_HEIGHT + 150)
            else:
                preferred = (center_x, center_y + 260)
            exercise_positions[owner_key] = collision_free(preferred, (EXERCISE_WIDTH, EXERCISE_HEIGHT), occupied, seed_index + 1)
        for index, key in enumerate(sorted(landmark_keys, key=lambda item: (self.source_starts[item], item))):
            member_set = set(descendants(self.nodes, key))
            members = [atom for atom in atom_keys if atom in member_set and atom in atom_positions]
            if members:
                x = sum(atom_positions[item][0] for item in members) / len(members)
                y = sum(atom_positions[item][1] for item in members) / len(members)
                preferred = (x - LANDMARK_WIDTH / 2, y - 190)
            else:
                angle = (index + len(atom_keys)) * GOLDEN_ANGLE
                preferred = (360 * math.cos(angle), 360 * math.sin(angle))
            landmark_positions[key] = collision_free(preferred, (LANDMARK_WIDTH, LANDMARK_HEIGHT), occupied, len(atom_keys) + index)
        min_x = min(item[0] for item in occupied) - GROUP_PADDING if occupied else -GROUP_PADDING
        min_y = min(item[1] for item in occupied) - GROUP_PADDING if occupied else -GROUP_PADDING
        max_x = max(item[2] for item in occupied) + GROUP_PADDING if occupied else GROUP_PADDING
        max_y = max(item[3] for item in occupied) + GROUP_PADDING if occupied else GROUP_PADDING
        return atom_positions, landmark_positions, exercise_positions, junction_positions, (min_x, min_y, max_x, max_y)

    def chapter_canvas(self, canvas_path: Path, chapter_key: str, overview_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        chapter_descendants = descendants(self.nodes, chapter_key)[1:]
        source_atoms = sorted((key for key in chapter_descendants if self.nodes[key].get("layer") == "atom"), key=lambda key: (self.source_starts[key], key))
        source_atom_set = set(source_atoms)
        internal_atoms = [key for key in source_atoms if self.visible_atom(key)]
        internal_set = set(internal_atoms)
        exercise_atoms = [key for key in source_atoms if self.nodes[key].get("category") == "exercise"]
        owner_by_exercise, exercises_by_owner = self.exercise_owners(chapter_key, exercise_atoms)
        local_links_by_concept: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for link in self.atom_concept_links:
            if str(link.get("atom_key")) in source_atom_set:
                local_links_by_concept[str(link.get("concept_key"))].append(link)
        local_hub_keys = {
            key for key in local_links_by_concept
            if key in self.concepts and self.concept_is_hub(key)
        } if self.dual_layer else set()
        chapter_concept_relations = [
            relation for relation in self.concept_relations
            if chapter_key in self.concept_chapters(str(relation.get("from_key")))
            or chapter_key in self.concept_chapters(str(relation.get("to_key")))
        ] if self.dual_layer else []
        chapter_relations_all = [relation for relation in self.relations if str(relation["from_key"]) in source_atom_set or str(relation["to_key"]) in source_atom_set]
        chapter_relations = [
            relation for relation in chapter_relations_all
            if self.visible_atom(str(relation["from_key"])) and self.visible_atom(str(relation["to_key"]))
            and (str(relation["from_key"]) in internal_set or str(relation["to_key"]) in internal_set)
        ]
        exercise_anchors: dict[str, list[str]] = defaultdict(list)
        exercise_anchor_counts: dict[tuple[str, str], int] = defaultdict(int)
        for relation in chapter_relations_all:
            left, right = str(relation["from_key"]), str(relation["to_key"])
            if right in owner_by_exercise and left in internal_set and self.nodes[left].get("category") == "knowledge":
                owner = owner_by_exercise[right]
                exercise_anchors[owner].append(left)
                exercise_anchor_counts[(owner, left)] += 1
            elif left in owner_by_exercise and right in internal_set and self.nodes[right].get("category") == "knowledge":
                owner = owner_by_exercise[left]
                exercise_anchors[owner].append(right)
                exercise_anchor_counts[(owner, right)] += 1
        for owner in exercises_by_owner:
            exercise_anchors[owner] = list(dict.fromkeys(exercise_anchors.get(owner, [])))
        direct_sections: list[str] = []
        for child in self.nodes[chapter_key].get("children", []):
            child_key = str(child)
            section = child_key if self.nodes[child_key].get("layer") == "organizer" else "__chapter_intro__"
            if section not in direct_sections:
                direct_sections.append(section)
        for owner_key in exercises_by_owner:
            section = self.section_for(chapter_key, owner_key)
            if section not in direct_sections:
                direct_sections.append(section)
        exercise_subtree_organizers = {
            key
            for owner in exercises_by_owner
            if owner != chapter_key
            and {self.nodes[atom].get("category") for atom in self.descendant_atoms(owner)} == {"exercise"}
            for key in descendants(self.nodes, owner)
            if self.nodes[key].get("layer") == "organizer"
        }
        region_payloads: list[dict[str, Any]] = []
        for section in direct_sections:
            atom_keys = [key for key in internal_atoms if self.section_for(chapter_key, key) == section]
            exercise_keys = [key for key in exercises_by_owner if self.section_for(chapter_key, key) == section]
            if section == "__chapter_intro__":
                organizer_keys, label = [], "章引入"
            else:
                section_desc = descendants(self.nodes, section)
                candidate_organizers = [
                    key for key in section_desc[1:]
                    if self.nodes[key].get("layer") == "organizer" and key not in exercise_subtree_organizers
                ]
                organizer_keys = []
                for key in candidate_organizers:
                    subtree = set(descendants(self.nodes, key))
                    if any(descendant in internal_set for descendant in subtree) or any(owner in subtree for owner in exercises_by_owner):
                        organizer_keys.append(key)
                label = str(self.nodes[section]["title"])
            local_relations = [relation for relation in chapter_relations if str(relation["from_key"]) in atom_keys and str(relation["to_key"]) in atom_keys]
            local_anchors = {owner: list(exercise_anchors[owner]) for owner in exercise_keys}
            local_counts = {owner: len(exercises_by_owner[owner]) for owner in exercise_keys}
            atom_positions, landmark_positions, exercise_positions, junction_positions, local_bounds = self.layout_region(
                atom_keys, organizer_keys, local_relations, local_anchors, local_counts
            )
            region_payloads.append({
                "key": section, "label": label, "atoms": atom_keys, "landmarks": organizer_keys,
                "exercises": exercise_keys, "atom_positions": atom_positions,
                "landmark_positions": landmark_positions, "exercise_positions": exercise_positions,
                "junction_positions": junction_positions, "bounds": local_bounds,
            })
        if not region_payloads:
            raise ValueError(f"Chapter has no atoms: {chapter_key}")
        max_dimension = max(max(item["bounds"][2] - item["bounds"][0], item["bounds"][3] - item["bounds"][1]) for item in region_payloads)
        radius = 0.0 if len(region_payloads) == 1 else max(900.0, max_dimension * len(region_payloads) / (2 * math.pi) + 500)
        for _ in range(12):
            placed: list[tuple[int, int, int, int]] = []
            collision = False
            for index, item in enumerate(region_payloads):
                angle = (-3 * math.pi / 4 if len(region_payloads) == 2 else -math.pi / 2) + 2 * math.pi * index / max(len(region_payloads), 1)
                center = (radius * math.cos(angle), radius * math.sin(angle))
                width, height = item["bounds"][2] - item["bounds"][0], item["bounds"][3] - item["bounds"][1]
                rect = (round(center[0] - width / 2), round(center[1] - height / 2), round(center[0] + width / 2), round(center[1] + height / 2))
                if any(overlaps(rect, other, margin=180) for other in placed):
                    collision = True
                placed.append(rect)
                item["placement"] = rect
            if not collision:
                break
            radius = max(900, radius * 1.22)
        groups: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        for order, item in enumerate(region_payloads, start=1):
            rect, local = item["placement"], item["bounds"]
            offset_x, offset_y = rect[0] - local[0], rect[1] - local[1]
            groups.append({"id": stable_id("region", f"{chapter_key}:{item['key']}"), "type": "group", "label": f"{order:02d} · {item['label']}", "x": rect[0], "y": rect[1], "width": rect[2] - rect[0], "height": rect[3] - rect[1]})
            for key, position in item["atom_positions"].items():
                cards.append(self.atom_card(key, canvas_path, (position[0] + offset_x, position[1] + offset_y)))
            for key, position in item["landmark_positions"].items():
                cards.append(self.landmark_card(key, canvas_path, (position[0] + offset_x, position[1] + offset_y)))
            for key, position in item["exercise_positions"].items():
                cards.append(self.exercise_card(key, len(exercises_by_owner[key]), canvas_path, (position[0] + offset_x, position[1] + offset_y)))
            for key, position in item["junction_positions"].items():
                cards.append(self.junction_card(key, len(exercise_anchors[key]), len(exercises_by_owner[key]), (position[0] + offset_x, position[1] + offset_y)))
        region_bounds = bounds_for(groups)
        header_y = int(region_bounds["y"]) - 320
        cards.extend([
            {"id": stable_id("utility", f"{chapter_key}:title"), "type": "text", "text": f"# ✦ {self.nodes[chapter_key]['title']}\n\n由中心向外阅读主学习路线", "x": int(region_bounds["x"]), "y": header_y, "width": 440, "height": 180, "color": ORGANIZER_COLOR},
            {"id": stable_id("utility", f"{chapter_key}:back"), "type": "text", "text": self.link_text("← 返回全书知识星图", overview_path, canvas_path), "x": int(region_bounds["x"]) + 500, "y": header_y, "width": 300, "height": 86},
            {"id": stable_id("utility", f"{chapter_key}:legend"), "type": "text", "text": "**图例**\n\n✦ 主线知识  ·  彩色卡片表示原子类别\n黄色为主线；其他颜色和标签表示支线关系", "x": int(region_bounds["x"]) + 850, "y": header_y, "width": 430, "height": 180},
        ])
        def representative_atom(concept_key: str, prefer_local: bool = True) -> str | None:
            candidates = []
            for link in self.links_by_concept.get(concept_key, []):
                atom_key = str(link["atom_key"])
                category = self.nodes[atom_key].get("category")
                displayable = self.visible_atom(atom_key) or (atom_key in owner_by_exercise)
                if not displayable:
                    continue
                priority = (
                    0 if prefer_local and atom_key in source_atom_set else 1,
                    0 if link.get("role") == "introduces" and category == "knowledge" else 1,
                    0 if category == "knowledge" else 1,
                    self.source_starts[atom_key], atom_key,
                )
                candidates.append((priority, atom_key))
            return min(candidates)[1] if candidates else None

        concept_representatives: dict[str, str] = {}
        for relation in chapter_concept_relations:
            for concept_key in (str(relation["from_key"]), str(relation["to_key"])):
                if concept_key not in local_hub_keys:
                    representative = representative_atom(concept_key)
                    if representative is not None:
                        concept_representatives[concept_key] = representative
        external_from_concepts = {
            atom_key for atom_key in concept_representatives.values()
            if atom_key not in source_atom_set and self.visible_atom(atom_key)
        }
        external_keys = sorted(
            {
                str(endpoint) for relation in chapter_relations
                for endpoint in (relation["from_key"], relation["to_key"])
                if str(endpoint) not in internal_set
            } | external_from_concepts,
            key=lambda key: (self.source_starts[key], key),
        )
        right_x = int(region_bounds["x"] + region_bounds["width"]) + 360
        for index, key in enumerate(external_keys):
            cards.append(self.atom_card(key, canvas_path, (right_x, int(region_bounds["y"]) + index * (PORTAL_HEIGHT + 100)), external=True))
        card_by_id = {str(card["id"]): card for card in cards}

        def atom_display_id(atom_key: str) -> str | None:
            if atom_key in internal_set:
                return stable_id("card", atom_key)
            if atom_key in owner_by_exercise:
                return stable_id("exercise-organizer", owner_by_exercise[atom_key])
            if atom_key in external_keys:
                return stable_id("external", atom_key)
            return None

        occupied = [
            rectangle((int(card["x"]), int(card["y"])), (int(card["width"]), int(card["height"])))
            for card in cards if card.get("type") == "text"
        ]
        for index, concept_key in enumerate(sorted(local_hub_keys, key=lambda key: (int(self.concepts[key].get("first_source_order", 0)), key))):
            endpoint_cards = []
            for link in local_links_by_concept[concept_key]:
                endpoint_id = atom_display_id(str(link["atom_key"]))
                if endpoint_id in card_by_id:
                    endpoint_cards.append(card_by_id[endpoint_id])
            if endpoint_cards:
                preferred = (
                    sum(int(item["x"]) + int(item["width"]) / 2 for item in endpoint_cards) / len(endpoint_cards) - CONCEPT_WIDTH / 2,
                    sum(int(item["y"]) + int(item["height"]) / 2 for item in endpoint_cards) / len(endpoint_cards) - CONCEPT_HEIGHT / 2,
                )
            else:
                preferred = (int(region_bounds["x"]) + index * 280, int(region_bounds["y"]) - 170)
            position = collision_free(preferred, (CONCEPT_WIDTH, CONCEPT_HEIGHT), occupied, index + len(cards))
            card = self.concept_card(concept_key, position)
            cards.append(card)
            card_by_id[str(card["id"])] = card
        edges: list[dict[str, Any]] = []
        rendered_concept_relations: list[tuple[dict[str, Any], str, str]] = []
        for relation in chapter_concept_relations:
            endpoints: list[str] = []
            for concept_key in (str(relation["from_key"]), str(relation["to_key"])):
                if concept_key in local_hub_keys:
                    endpoints.append(stable_id("concept", concept_key))
                else:
                    atom_key = concept_representatives.get(concept_key)
                    endpoint_id = atom_display_id(atom_key) if atom_key is not None else None
                    if endpoint_id is not None:
                        endpoints.append(endpoint_id)
            if len(endpoints) == 2 and endpoints[0] != endpoints[1]:
                rendered_concept_relations.append((relation, endpoints[0], endpoints[1]))
        rendered_basis_keys = {str(item[0]["key"]) for item in rendered_concept_relations}
        rendered_chapter_relations = [
            relation for relation in chapter_relations
            if not set(str(value) for value in relation.get("basis_keys", [])).intersection(rendered_basis_keys)
        ]
        for relation in rendered_chapter_relations:
            left, right = str(relation["from_key"]), str(relation["to_key"])
            left_id = stable_id("card", left) if left in internal_set else stable_id("external", left)
            right_id = stable_id("card", right) if right in internal_set else stable_id("external", right)
            edges.append(self.relation_edge(relation, left_id, right_id, chapter_key))
        concept_relation_edge_count = 0
        for relation, left_id, right_id in rendered_concept_relations:
            edges.append(self.concept_edge(relation, left_id, right_id, chapter_key))
            concept_relation_edge_count += 1
        concept_membership_edge_count = 0
        seen_membership: set[tuple[str, str, str]] = set()
        for concept_key in sorted(local_hub_keys):
            for link in local_links_by_concept[concept_key]:
                atom_key, role = str(link["atom_key"]), str(link["role"])
                endpoint_id = atom_display_id(atom_key)
                identity = concept_key, str(endpoint_id), role
                if endpoint_id is None or identity in seen_membership:
                    continue
                seen_membership.add(identity)
                edges.append(self.concept_membership_edge(chapter_key, concept_key, endpoint_id, role, atom_key))
                concept_membership_edge_count += 1
        for owner_key in sorted(exercises_by_owner, key=lambda key: (self.source_starts[key], key)):
            anchors_for_owner = exercise_anchors.get(owner_key, [])
            owner_id = stable_id("exercise-organizer", owner_key)
            if len(anchors_for_owner) > 1:
                junction_id = stable_id("junction", owner_key)
                for anchor in anchors_for_owner:
                    count = exercise_anchor_counts[(owner_key, anchor)]
                    edges.append(self.exercise_edge(chapter_key, owner_key, stable_id("card", anchor), junction_id, f"练习 ×{count}", f"anchor:{anchor}"))
                edges.append(self.exercise_edge(chapter_key, owner_key, junction_id, owner_id, f"包含 ×{len(exercises_by_owner[owner_key])}", "contains"))
            elif anchors_for_owner:
                anchor = anchors_for_owner[0]
                count = exercise_anchor_counts[(owner_key, anchor)]
                edges.append(self.exercise_edge(chapter_key, owner_key, stable_id("card", anchor), owner_id, f"练习 ×{count}", f"anchor:{anchor}"))
        landmark_keys = {
            key for item in region_payloads for key in item["landmarks"]
        }

        def first_rendered_descendant(organizer_key: str) -> str | None:
            for raw_child in self.nodes[organizer_key].get("children", []):
                child = str(raw_child)
                child_node = self.nodes[child]
                if child in internal_set:
                    return stable_id("card", child)
                if child_node.get("layer") == "atom":
                    owner = owner_by_exercise.get(child)
                    if owner in exercises_by_owner:
                        return stable_id("exercise-organizer", owner)
                    continue
                if child in landmark_keys:
                    return stable_id("landmark", child)
                if child in exercises_by_owner:
                    return stable_id("exercise-organizer", child)
                nested = first_rendered_descendant(child)
                if nested is not None:
                    return nested
            return None

        landmark_edge_count = 0
        for landmark_key in sorted(landmark_keys, key=lambda key: (self.source_starts[key], key)):
            target_id = first_rendered_descendant(landmark_key)
            if target_id is None:
                raise ValueError(f"Rendered landmark has no rendered descendant: {landmark_key}")
            edges.append(self.landmark_edge(chapter_key, landmark_key, target_id))
            landmark_edge_count += 1
        all_nodes = [*groups, *cards]
        exercise_edges = sum(
            len(anchors) + 1 if len(anchors) > 1 else (1 if anchors else 0)
            for anchors in exercise_anchors.values()
        )
        counts = {
            "cards": len(cards), "groups": len(groups), "edges": len(edges),
            "organizers": 1 + sum(self.nodes[key].get("layer") == "organizer" for key in chapter_descendants),
            "atoms": len(internal_atoms), "source_atoms": len(source_atoms), "internal_atoms": len(internal_atoms),
            "exercise_atoms_collapsed": len(exercise_atoms), "featured_examples": len(self.featured_examples.intersection(source_atom_set)),
            "hidden_examples": sum(self.nodes[key].get("category") == "worked-example" and key not in self.featured_examples for key in source_atoms),
            "exercise_organizers": len(exercises_by_owner), "virtual_nodes": sum(len(item["junction_positions"]) for item in region_payloads),
            "concept_hubs": len(local_hub_keys), "concept_membership_edges": concept_membership_edge_count,
            "concept_relation_edges": concept_relation_edge_count,
            "external_portals": len(external_keys), "landmarks": sum(len(item["landmarks"]) for item in region_payloads), "navigation_nodes": 3,
            "regions": len(groups), "backbone_edges": sum(relation.get("tier") == "backbone" for relation in rendered_chapter_relations) + sum(item[0].get("tier") == "backbone" for item in rendered_concept_relations),
            "supporting_edges": sum(relation.get("tier") == "supporting" for relation in rendered_chapter_relations) + sum(item[0].get("tier") == "supporting" for item in rendered_concept_relations) + exercise_edges + concept_membership_edge_count,
            "source_order_edges": 0, "semantic_edges": len(rendered_chapter_relations) + concept_relation_edge_count + concept_membership_edge_count, "exercise_aggregate_edges": exercise_edges,
            "landmark_edges": landmark_edge_count,
        }
        return {"nodes": all_nodes, "edges": edges}, {"counts": counts, "bounds": bounds_for(all_nodes)}

    def build(self) -> tuple[dict[Path, dict[str, Any]], dict[str, Any]]:
        payloads: dict[Path, dict[str, Any]] = {}
        overview_path = self.output_dir / "overview.canvas"
        overview, overview_meta = self.overview_canvas(overview_path)
        payloads[overview_path] = overview
        chapter_entries: list[dict[str, Any]] = []
        for chapter_key in self.chapter_keys:
            if self.semantic_ready:
                chapter_path = self.chapter_paths[chapter_key]
                canvas, meta = self.chapter_canvas(chapter_path, chapter_key, overview_path)
                payloads[chapter_path] = canvas
                chapter_entries.append({"role": "chapter-knowledge-map", "root_key": chapter_key, "status": "ready", "path": chapter_path.relative_to(self.output_dir).as_posix(), **meta})
            else:
                chapter_entries.append({"role": "chapter-knowledge-map", "root_key": chapter_key, "status": "relation-review-required", "path": None, "counts": None, "bounds": None})
        index = {
            "schema_version": 2, "manifest": str(self.manifest_path), "manifest_sha256": sha256_file(self.manifest_path),
            "book_root": str(self.book_root), "relation_status": "passed" if self.semantic_ready else "review_required",
            "layout": {
                "mode": "two-level-constellation", "theme": "adaptive",
                "zoom_levels": ["book-chapters", "chapter-atoms"], "learning_direction": "center-outward",
                "organization_encoding": "regions-and-landmarks", "source_region_order": "clockwise",
                "atom_visibility": "knowledge-scenario-and-bridge-examples",
                "exercise_representation": "organizer-clusters",
                "virtual_nodes": "exercise-convergence-and-selective-concept-hubs",
                "concept_hub_visibility": "two-displays-or-degree-three-or-cross-region-or-cross-chapter",
                "edge_ports": {
                    "progression": "right-to-left", "inspiration": "right-to-top",
                    "support-and-containment": "bottom-to-top",
                },
            },
            "atlas": {"role": "book-atlas", "root_key": self.root_key, "path": "overview.canvas", **overview_meta},
            "chapter_maps": chapter_entries,
        }
        return payloads, index


def build_canvas_bundle(manifest_path: Path, output_dir: Path, book_root: Path, overwrite: bool = False) -> dict[str, Any]:
    manifest_path, output_dir, book_root = (path.expanduser().resolve() for path in (manifest_path, output_dir, book_root))
    validation = validate_graph(manifest_path, book_root)
    if validation["status"] != "passed":
        raise ValueError("Book graph must pass before Canvas build: " + json.dumps(validation["errors"][:5], ensure_ascii=False))
    manifest = load_json(manifest_path)
    profile = load_json(Path(str(manifest["profile"])).expanduser().resolve())
    canvas_mode = str(profile.get("canvas", {}).get("mode", "two-level-constellation"))
    if canvas_mode == "three-level-constellation":
        # Imported lazily so the v2 compatibility builder remains directly
        # importable and existing reviewed bundles keep their exact contract.
        from constellation_v3 import CanvasBundleBuilderV3
        builder = CanvasBundleBuilderV3(manifest, manifest_path, book_root, output_dir)
    elif canvas_mode == "two-level-constellation":
        builder = CanvasBundleBuilder(manifest, manifest_path, book_root, output_dir)
    else:
        raise ValueError(f"Unsupported canvas.mode: {canvas_mode}")
    payloads, index = builder.build()
    index_path = output_dir / "canvas-index.json"
    planned = [*payloads, index_path]
    if not overwrite:
        existing = [str(path) for path in planned if path.exists()]
        if existing:
            raise FileExistsError("Canvas bundle output exists; pass --overwrite explicitly: " + ", ".join(existing))
    for path, payload in payloads.items():
        atomic_json(path, payload, overwrite=True)
    atomic_json(index_path, index, overwrite=True)
    report = {
        "status": "passed", "canvas_index": str(index_path), "canvases": len(payloads),
        "atlas": str(output_dir / index["atlas"]["path"]),
        "chapter_maps": sum(entry["status"] == "ready" for entry in index["chapter_maps"]),
        "relation_status": index["relation_status"],
    }
    if "section_maps" in index:
        report["section_maps"] = sum(entry["status"] == "ready" for entry in index["section_maps"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--book-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report, code = build_canvas_bundle(args.manifest, args.output_dir, args.book_root, overwrite=args.overwrite), 0
    except Exception as exc:
        report, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
