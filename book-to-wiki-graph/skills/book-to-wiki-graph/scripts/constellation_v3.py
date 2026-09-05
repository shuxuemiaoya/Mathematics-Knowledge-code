#!/usr/bin/env python3
"""Three-scale, level-of-detail knowledge constellation Canvas builder."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from build_canvas import (
    ATOM_COLORS,
    BACKBONE_COLOR,
    CHAPTER_HEIGHT,
    CHAPTER_WIDTH,
    CONCEPT_HEIGHT,
    CONCEPT_WIDTH,
    CORE_HEIGHT,
    CORE_WIDTH,
    EXERCISE_HEIGHT,
    EXERCISE_WIDTH,
    GOLDEN_ANGLE,
    GROUP_PADDING,
    NODE_MARGIN,
    ORGANIZER_COLOR,
    SOURCE_ORDER_COLOR,
    CanvasBundleBuilder,
    bounds_for,
    collision_free,
    descendants,
    overlaps,
    rectangle,
    safe_filename,
    stable_id,
)


PORTAL_WIDTH, PORTAL_HEIGHT = 300, 94
MAP_HUB_WIDTH, MAP_HUB_HEIGHT = 390, 150
REGION_MIN_WIDTH, REGION_MIN_HEIGHT = 760, 580
SHORT_TITLE_LIMIT = 34


def compact_title(value: str, limit: int = SHORT_TITLE_LIMIT) -> str:
    """Keep Canvas labels readable without changing source metadata."""
    text = " ".join(str(value).replace("\n", " ").split()).strip(" #")
    if len(text) <= limit:
        return text
    for mark in ("。", "；", "？", "?", "！", "!", "：", ":", "，", ","):
        position = text.find(mark, 10, limit + 1)
        if position >= 0:
            return text[: position + 1]
    return text[: limit - 1].rstrip() + "…"


def center(node: dict[str, Any]) -> tuple[float, float]:
    return (
        float(node["x"]) + float(node["width"]) / 2,
        float(node["y"]) + float(node["height"]) / 2,
    )


def segment_crosses(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]) -> bool:
    def orientation(left: tuple[float, float], middle: tuple[float, float], right: tuple[float, float]) -> float:
        return (middle[0] - left[0]) * (right[1] - left[1]) - (middle[1] - left[1]) * (right[0] - left[0])

    return orientation(a, b, c) * orientation(a, b, d) < 0 and orientation(c, d, a) * orientation(c, d, b) < 0


def visual_quality(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(node["id"]): node for node in nodes if node.get("type") == "text"}
    lengths: list[float] = []
    lines: list[tuple[tuple[float, float], tuple[float, float], set[str]]] = []
    for edge in edges:
        left, right = by_id.get(str(edge.get("fromNode"))), by_id.get(str(edge.get("toNode")))
        if left is None or right is None:
            continue
        start, end = center(left), center(right)
        lengths.append(math.hypot(end[0] - start[0], end[1] - start[1]))
        lines.append((start, end, {str(edge["fromNode"]), str(edge["toNode"])}))
    crossings = 0
    for index, first in enumerate(lines):
        for second in lines[index + 1 :]:
            if first[2].intersection(second[2]):
                continue
            crossings += int(segment_crosses(first[0], first[1], second[0], second[1]))
    ordered = sorted(lengths)
    percentile = lambda ratio: round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * ratio))]) if ordered else 0
    practice_edges = sum(str(edge.get("label", "")).startswith("练习") for edge in edges)
    return {
        "straight_crossing_estimate": crossings,
        "edge_length_median": percentile(0.5),
        "edge_length_p90": percentile(0.9),
        "edge_length_max": round(max(ordered)) if ordered else 0,
        "edges_over_2000": sum(value > 2000 for value in ordered),
        "practice_edge_share": round(practice_edges / len(edges), 4) if edges else 0.0,
    }


class CanvasBundleBuilderV3(CanvasBundleBuilder):
    """Render atlas, chapter constellations, and section detail maps."""

    def __init__(self, manifest: dict[str, Any], manifest_path: Path, book_root: Path, output_dir: Path) -> None:
        super().__init__(manifest, manifest_path, book_root, output_dir)
        self.section_keys_by_chapter = {
            chapter: self.direct_sections(chapter) for chapter in self.chapter_keys
        }
        self.section_paths = self._section_paths()

    def _chapter_paths(self) -> dict[str, Path]:
        width = max(2, len(str(len(self.chapter_keys))))
        return {
            key: self.output_dir / "chapters" / f"{index:0{width}d}-{safe_filename(str(self.nodes[key]['title']), 'chapter')}-{stable_id('chapter-v3', key)[:6]}.canvas"
            for index, key in enumerate(self.chapter_keys, start=1)
        }

    def direct_sections(self, chapter_key: str) -> list[str]:
        result: list[str] = []
        for child in self.nodes[chapter_key].get("children", []):
            key = str(child)
            section = key if self.nodes[key].get("layer") == "organizer" else "__chapter_intro__"
            if section not in result:
                result.append(section)
        return result or ["__chapter_intro__"]

    def _section_paths(self) -> dict[tuple[str, str], Path]:
        result: dict[tuple[str, str], Path] = {}
        chapter_width = max(2, len(str(len(self.chapter_keys))))
        for chapter_index, chapter in enumerate(self.chapter_keys, start=1):
            sections = self.section_keys_by_chapter[chapter]
            section_width = max(2, len(str(len(sections))))
            for section_index, section in enumerate(sections, start=1):
                title = "章引入" if section == "__chapter_intro__" else str(self.nodes[section]["title"])
                filename = f"{chapter_index:0{chapter_width}d}-{section_index:0{section_width}d}-{safe_filename(title, 'section')}-{stable_id('section-v3', f'{chapter}:{section}')[:6]}.canvas"
                result[(chapter, section)] = self.output_dir / "sections" / filename
        return result

    def display_title(self, key: str) -> str:
        return compact_title(str(self.nodes[key]["title"]))

    def atom_card(self, key: str, canvas_path: Path, position: tuple[int, int], external: bool = False) -> dict[str, Any]:
        card = super().atom_card(key, canvas_path, position, external=external)
        node = self.nodes[key]
        category = str(node["category"])
        prefix = "↗ 外章" if external else ("✦" if self.is_core(key) else "·")
        card["text"] = self.link_text(
            f"{prefix} {self.atom_label(category)} · {self.display_title(key)}",
            self.note_target(key),
            canvas_path,
        )
        return card

    @staticmethod
    def atom_label(category: str) -> str:
        return {
            "knowledge": "知识点", "worked-example": "方法例题",
            "exercise": "习题", "scenario": "情景引入",
        }[category]

    def strict_concept_hubs(self, visible_atoms: set[str], region_of: dict[str, str]) -> set[str]:
        result: set[str] = set()
        if not self.dual_layer:
            return result
        for key in self.concepts:
            grounded = {
                str(link["atom_key"]) for link in self.links_by_concept.get(key, [])
                if str(link.get("atom_key")) in visible_atoms
            }
            if len(grounded) < 2:
                continue
            relation_degree = sum(
                key in {str(item.get("from_key")), str(item.get("to_key"))}
                for item in self.concept_relations
            )
            regions = {region_of.get(atom, "") for atom in grounded}
            cross_chapter = len({self.atom_chapter[atom] for atom in grounded}) > 1 or any(
                key in {str(item.get("from_key")), str(item.get("to_key"))}
                and self.concept_chapters(str(item.get("from_key"))) != self.concept_chapters(str(item.get("to_key")))
                for item in self.concept_relations
            )
            if len(regions) >= 2 or relation_degree >= 3 or cross_chapter:
                result.add(key)
        return result

    def section_portal_card(
        self,
        chapter_key: str,
        section_key: str,
        canvas_path: Path,
        position: tuple[int, int],
        atom_count: int,
        exercise_count: int,
    ) -> dict[str, Any]:
        title = "章引入" if section_key == "__chapter_intro__" else str(self.nodes[section_key]["title"])
        target = self.section_paths[(chapter_key, section_key)]
        return {
            "id": stable_id("section-portal", f"{chapter_key}:{section_key}"),
            "type": "text",
            "text": self.link_text(f"⌕ 放大 · {compact_title(title, 26)}", target, canvas_path) + f"\n\n{atom_count} 个展示原子 · {exercise_count} 题",
            "x": position[0], "y": position[1], "width": PORTAL_WIDTH, "height": PORTAL_HEIGHT,
            "color": ORGANIZER_COLOR,
        }

    def exercise_entry_card(self, owner: str, count: int, canvas_path: Path, position: tuple[int, int]) -> dict[str, Any]:
        return {
            "id": stable_id("exercise-entry", owner), "type": "text",
            "text": self.link_text(f"练习入口 · {compact_title(str(self.nodes[owner]['title']), 25)}", self.note_target(owner), canvas_path) + f"\n\n共 {count} 题",
            "x": position[0], "y": position[1], "width": EXERCISE_WIDTH, "height": EXERCISE_HEIGHT,
            "color": ATOM_COLORS["exercise"],
        }

    def map_hub(self, scope: str, title: str, subtitle: str, position: tuple[int, int], link: str | None = None) -> dict[str, Any]:
        text = f"# ✦ {compact_title(title, 42)}\n\n{subtitle}"
        if link:
            text = f"# {link}\n\n{subtitle}"
        return {
            "id": stable_id("map-hub", scope), "type": "text", "text": text,
            "x": position[0], "y": position[1], "width": MAP_HUB_WIDTH, "height": MAP_HUB_HEIGHT,
            "color": ORGANIZER_COLOR,
        }

    @staticmethod
    def navigation_edge(scope: str, suffix: str, left: str, right: str, label: str = "") -> dict[str, Any]:
        return {
            "id": stable_id("edge", f"{scope}:navigation:{suffix}"),
            "fromNode": left, "toNode": right, "fromSide": "right", "toSide": "left",
            "label": label, "color": SOURCE_ORDER_COLOR, "fromEnd": "none", "toEnd": "arrow",
        }

    def layout_cluster(self, atom_keys: list[str], extra_count: int = 0) -> tuple[dict[str, tuple[int, int]], list[tuple[int, int, int, int]]]:
        occupied: list[tuple[int, int, int, int]] = []
        positions: dict[str, tuple[int, int]] = {}
        ordered = self.topological_core_order(atom_keys, [
            item for item in self.relations
            if str(item.get("from_key")) in atom_keys and str(item.get("to_key")) in atom_keys
        ])
        remaining = [key for key in atom_keys if key not in ordered]
        for index, key in enumerate([*ordered, *remaining]):
            radius = 115 + 155 * math.sqrt(index)
            angle = index * GOLDEN_ANGLE - math.pi / 2
            size = (CORE_WIDTH, CORE_HEIGHT) if self.is_core(key) else (250, 66)
            positions[key] = collision_free(
                (radius * math.cos(angle) - size[0] / 2, radius * math.sin(angle) - size[1] / 2),
                size, occupied, index,
            )
        # Reserve a compact outer arc for exercise/detail entries.
        for index in range(extra_count):
            angle = math.pi / 4 + index * GOLDEN_ANGLE
            collision_free(
                (430 * math.cos(angle), 430 * math.sin(angle)),
                (max(EXERCISE_WIDTH, PORTAL_WIDTH), max(EXERCISE_HEIGHT, PORTAL_HEIGHT)),
                occupied, len(atom_keys) + index,
            )
        return positions, occupied

    def place_regions(self, payloads: list[dict[str, Any]], radius_floor: float = 980.0) -> None:
        max_dimension = max(
            max(item["bounds"][2] - item["bounds"][0], item["bounds"][3] - item["bounds"][1])
            for item in payloads
        )
        radius = 0.0 if len(payloads) == 1 else max(radius_floor, max_dimension * len(payloads) / (2 * math.pi) + 180)
        for _ in range(14):
            placed: list[tuple[int, int, int, int]] = []
            collision = False
            for index, item in enumerate(payloads):
                if len(payloads) == 1:
                    center_x, center_y = 0.0, 620.0
                else:
                    angle = -math.pi / 2 + 2 * math.pi * index / len(payloads)
                    center_x, center_y = radius * math.cos(angle), radius * math.sin(angle)
                width = max(REGION_MIN_WIDTH, item["bounds"][2] - item["bounds"][0])
                height = max(REGION_MIN_HEIGHT, item["bounds"][3] - item["bounds"][1])
                rect = (
                    round(center_x - width / 2), round(center_y - height / 2),
                    round(center_x + width / 2), round(center_y + height / 2),
                )
                if any(overlaps(rect, other, margin=150) for other in placed):
                    collision = True
                placed.append(rect)
                item["placement"] = rect
            if not collision:
                return
            radius *= 1.15

    def representative_atom(self, concept_key: str, visible: set[str]) -> str | None:
        candidates = []
        for link in self.links_by_concept.get(concept_key, []):
            atom = str(link.get("atom_key"))
            if atom not in visible:
                continue
            candidates.append((
                0 if link.get("role") == "introduces" and self.nodes[atom].get("category") == "knowledge" else 1,
                0 if self.nodes[atom].get("category") == "knowledge" else 1,
                self.source_starts[atom], atom,
            ))
        return min(candidates)[-1] if candidates else None

    def add_semantic_edges(
        self,
        scope: str,
        visible: set[str],
        hub_keys: set[str],
        cards: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        include_practice: bool = False,
    ) -> tuple[int, int, int]:
        card_ids = {str(card["id"]) for card in cards}
        representatives = {key: self.representative_atom(key, visible) for key in self.concepts}
        rendered_concept_keys: set[str] = set()
        concept_relation_count = 0
        for relation in self.concept_relations:
            endpoints: list[str] = []
            for concept in (str(relation.get("from_key")), str(relation.get("to_key"))):
                if concept in hub_keys:
                    endpoints.append(stable_id("concept", concept))
                else:
                    representative = representatives.get(concept)
                    endpoints.append(stable_id("card", representative) if representative else "")
            if endpoints[0] in card_ids and endpoints[1] in card_ids and endpoints[0] != endpoints[1]:
                edges.append(self.concept_edge(relation, endpoints[0], endpoints[1], scope))
                rendered_concept_keys.add(str(relation.get("key")))
                concept_relation_count += 1
        atom_relation_count = 0
        for relation in self.relations:
            if relation.get("type") == "practices" and not include_practice:
                continue
            left, right = str(relation.get("from_key")), str(relation.get("to_key"))
            if left not in visible or right not in visible:
                continue
            if set(map(str, relation.get("basis_keys", []))).intersection(rendered_concept_keys):
                continue
            left_id, right_id = stable_id("card", left), stable_id("card", right)
            if left_id in card_ids and right_id in card_ids and left_id != right_id:
                edges.append(self.relation_edge(relation, left_id, right_id, scope))
                atom_relation_count += 1
        membership_count = 0
        seen: set[tuple[str, str, str]] = set()
        for concept in sorted(hub_keys):
            for link in self.links_by_concept.get(concept, []):
                atom, role = str(link.get("atom_key")), str(link.get("role"))
                identity = concept, atom, role
                if atom not in visible or identity in seen:
                    continue
                seen.add(identity)
                edges.append(self.concept_membership_edge(scope, concept, stable_id("card", atom), role, atom))
                membership_count += 1
        return atom_relation_count, concept_relation_count, membership_count

    def add_isolation_fallback(self, scope: str, atom_keys: list[str], substantive: set[str], edges: list[dict[str, Any]]) -> int:
        incident = {str(endpoint) for edge in edges for endpoint in (edge.get("fromNode"), edge.get("toNode"))}
        ordered = sorted(atom_keys, key=lambda key: (self.source_starts[key], key))
        fallback = 0
        for key in ordered:
            node_id = stable_id("card", key)
            if node_id in incident or len(ordered) < 2:
                continue
            index = ordered.index(key)
            neighbour = ordered[index - 1] if index else ordered[1]
            left, right = (neighbour, key) if self.source_starts[neighbour] <= self.source_starts[key] else (key, neighbour)
            edge = self.navigation_edge(scope, f"reading:{left}:{right}", stable_id("card", left), stable_id("card", right), "书序")
            if edge["id"] not in {item["id"] for item in edges}:
                edges.append(edge)
                fallback += 1
                incident.update((edge["fromNode"], edge["toNode"]))
        return fallback

    def group_payload(self, label: str, atom_keys: list[str], extra_keys: list[str]) -> dict[str, Any]:
        positions, occupied = self.layout_cluster(atom_keys)
        extras: dict[str, tuple[int, int]] = {}
        for index, key in enumerate(extra_keys):
            angle = math.pi / 2 + index * GOLDEN_ANGLE
            extras[key] = collision_free(
                (430 * math.cos(angle) - PORTAL_WIDTH / 2, 430 * math.sin(angle) - PORTAL_HEIGHT / 2),
                (PORTAL_WIDTH, PORTAL_HEIGHT), occupied, len(atom_keys) + index,
            )
        min_x = min((item[0] for item in occupied), default=-REGION_MIN_WIDTH // 2) - GROUP_PADDING
        min_y = min((item[1] for item in occupied), default=-REGION_MIN_HEIGHT // 2) - GROUP_PADDING
        max_x = max((item[2] for item in occupied), default=REGION_MIN_WIDTH // 2) + GROUP_PADDING
        max_y = max((item[3] for item in occupied), default=REGION_MIN_HEIGHT // 2) + GROUP_PADDING
        return {"label": label, "atoms": atom_keys, "extras": extra_keys, "positions": positions, "extra_positions": extras, "bounds": (min_x, min_y, max_x, max_y)}

    def chapter_canvas(self, canvas_path: Path, chapter_key: str, overview_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        all_keys = descendants(self.nodes, chapter_key)[1:]
        source_atoms = sorted((key for key in all_keys if self.nodes[key].get("layer") == "atom"), key=lambda key: (self.source_starts[key], key))
        visible_atoms = [key for key in source_atoms if self.visible_atom(key)]
        visible_set = set(visible_atoms)
        sections = self.section_keys_by_chapter[chapter_key]
        region_of = {key: self.section_for(chapter_key, key) for key in visible_atoms}
        exercise_atoms = [key for key in source_atoms if self.nodes[key].get("category") == "exercise"]
        exercise_count_by_section = Counter(self.section_for(chapter_key, key) for key in exercise_atoms)
        payloads = []
        for section in sections:
            atoms = [key for key in visible_atoms if region_of[key] == section]
            title = "章引入" if section == "__chapter_intro__" else str(self.nodes[section]["title"])
            portal_key = f"portal:{chapter_key}:{section}"
            payload = self.group_payload(title, atoms, [portal_key])
            payload.update({"key": section, "portal_key": portal_key})
            payloads.append(payload)
        self.place_regions(payloads)
        groups: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        for order, payload in enumerate(payloads, start=1):
            rect, local = payload["placement"], payload["bounds"]
            offset_x, offset_y = rect[0] - local[0], rect[1] - local[1]
            section = payload["key"]
            groups.append({
                "id": stable_id("region-v3", f"{chapter_key}:{section}"), "type": "group",
                "label": f"{order:02d} · {payload['label']}", "x": rect[0], "y": rect[1],
                "width": rect[2] - rect[0], "height": rect[3] - rect[1],
            })
            for key, position in payload["positions"].items():
                cards.append(self.atom_card(key, canvas_path, (position[0] + offset_x, position[1] + offset_y)))
            portal_position = payload["extra_positions"][payload["portal_key"]]
            cards.append(self.section_portal_card(
                chapter_key, section, canvas_path,
                (portal_position[0] + offset_x, portal_position[1] + offset_y),
                len(payload["atoms"]), exercise_count_by_section.get(section, 0),
            ))
        cards.append(self.map_hub(chapter_key, str(self.nodes[chapter_key]["title"]), "章节主线 · 顺时针进入各知识星域", (-MAP_HUB_WIDTH // 2, -MAP_HUB_HEIGHT // 2)))
        cards.extend([
            {"id": stable_id("utility", f"{chapter_key}:back:v3"), "type": "text", "text": self.link_text("← 返回全书知识星图", overview_path, canvas_path), "x": -620, "y": -55, "width": 300, "height": 86},
            {"id": stable_id("utility", f"{chapter_key}:legend:v3"), "type": "text", "text": "**阅读图例**\n\n✦ 主线 · 彩色卡片为原子\n灰色书序只用于消除视觉孤岛\n练习下沉到小节图", "x": 320, "y": -86, "width": 410, "height": 150},
        ])
        occupied = [rectangle((int(card["x"]), int(card["y"])), (int(card["width"]), int(card["height"]))) for card in cards]
        hub_keys = self.strict_concept_hubs(visible_set, region_of)
        for index, concept in enumerate(sorted(hub_keys, key=lambda key: (int(self.concepts[key].get("first_source_order", 0)), key))):
            endpoints = []
            for link in self.links_by_concept.get(concept, []):
                card = next((item for item in cards if item["id"] == stable_id("card", str(link.get("atom_key")))), None)
                if card is not None:
                    endpoints.append(card)
            if endpoints:
                preferred = (
                    sum(center(item)[0] for item in endpoints) / len(endpoints) - CONCEPT_WIDTH / 2,
                    sum(center(item)[1] for item in endpoints) / len(endpoints) - CONCEPT_HEIGHT / 2,
                )
            else:
                preferred = (index * 280, 210)
            position = collision_free(preferred, (CONCEPT_WIDTH, CONCEPT_HEIGHT), occupied, len(cards) + index)
            cards.append(self.concept_card(concept, position))
        edges: list[dict[str, Any]] = []
        atom_edges, concept_edges, membership_edges = self.add_semantic_edges(chapter_key, visible_set, hub_keys, cards, edges)
        hub_id = stable_id("map-hub", chapter_key)
        for payload in payloads:
            portal_id = stable_id("section-portal", f"{chapter_key}:{payload['key']}")
            edges.append(self.navigation_edge(chapter_key, f"portal:{payload['key']}", hub_id, portal_id))
        fallback_edges = self.add_isolation_fallback(chapter_key, visible_atoms, {stable_id("card", key) for key in visible_atoms}, edges)
        all_nodes = [*groups, *cards]
        counts = {
            "cards": len(cards), "groups": len(groups), "edges": len(edges),
            "internal_atoms": len(visible_atoms), "source_atoms": len(source_atoms),
            "knowledge_atoms": sum(self.nodes[key].get("category") == "knowledge" for key in visible_atoms),
            "scenario_atoms": sum(self.nodes[key].get("category") == "scenario" for key in visible_atoms),
            "featured_examples": sum(self.nodes[key].get("category") == "worked-example" for key in visible_atoms),
            "exercise_atoms_summarized": len(exercise_atoms), "exercise_portals": len(sections),
            "exercise_relation_edges": 0, "concept_hubs": len(hub_keys),
            "atom_relation_edges": atom_edges, "concept_relation_edges": concept_edges,
            "concept_membership_edges": membership_edges, "source_order_fallback_edges": fallback_edges,
            "navigation_nodes": 3 + len(sections), "regions": len(groups), "landmarks": 0,
        }
        return {"nodes": all_nodes, "edges": edges}, {"counts": counts, "bounds": bounds_for(all_nodes), "visual_quality": visual_quality(cards, edges)}

    def subgroup_for(self, section_key: str, atom_or_owner: str) -> str:
        if section_key == "__chapter_intro__":
            return "__direct__"
        cursor = atom_or_owner
        parent = self.nodes[cursor].get("parent_key")
        if parent is not None and str(parent) == section_key:
            return cursor if self.nodes[cursor].get("layer") == "organizer" else "__direct__"
        while parent is not None and str(parent) != section_key:
            cursor = str(parent)
            parent = self.nodes[cursor].get("parent_key")
        return cursor if parent is not None else "__direct__"

    def section_canvas(self, canvas_path: Path, chapter_key: str, section_key: str, chapter_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        if section_key == "__chapter_intro__":
            source_atoms = [str(key) for key in self.nodes[chapter_key].get("children", []) if self.nodes[str(key)].get("layer") == "atom"]
            section_title = "章引入"
            note_key = chapter_key
        else:
            source_atoms = [key for key in descendants(self.nodes, section_key)[1:] if self.nodes[key].get("layer") == "atom"]
            section_title = str(self.nodes[section_key]["title"])
            note_key = section_key
        source_atoms.sort(key=lambda key: (self.source_starts[key], key))
        visible_atoms = [key for key in source_atoms if self.visible_atom(key)]
        visible_set = set(visible_atoms)
        exercises = [key for key in source_atoms if self.nodes[key].get("category") == "exercise"]
        owner_by_exercise, exercises_by_owner = self.exercise_owners(chapter_key, exercises)
        # Resolve each collapsed exercise organizer to one primary knowledge
        # anchor before layout. Keeping both cards in the same local star
        # region removes the long line fan produced by a separate exercise belt.
        anchors_by_owner: dict[str, Counter[str]] = defaultdict(Counter)
        for relation in self.relations:
            left, right = str(relation.get("from_key")), str(relation.get("to_key"))
            if right in owner_by_exercise and left in visible_set and self.nodes[left].get("category") == "knowledge":
                anchors_by_owner[owner_by_exercise[right]][left] += 1
            elif left in owner_by_exercise and right in visible_set and self.nodes[right].get("category") == "knowledge":
                anchors_by_owner[owner_by_exercise[left]][right] += 1
        primary_anchor: dict[str, str] = {}
        for owner in exercises_by_owner:
            candidates = anchors_by_owner.get(owner, Counter())
            if candidates:
                primary_anchor[owner] = min(
                    candidates,
                    key=lambda key: (-candidates[key], abs(self.source_starts[key] - self.source_starts[owner]), key),
                )
            elif visible_atoms:
                primary_anchor[owner] = min(
                    visible_atoms,
                    key=lambda key: (abs(self.source_starts[key] - self.source_starts[owner]), key),
                )
        owner_group = {
            owner: self.subgroup_for(section_key, anchor)
            for owner, anchor in primary_anchor.items()
        }
        subgroup_keys: list[str] = []
        for key in visible_atoms:
            subgroup = self.subgroup_for(section_key, key)
            if subgroup not in subgroup_keys:
                subgroup_keys.append(subgroup)
        if any(owner not in owner_group for owner in exercises_by_owner):
            subgroup_keys.append("__exercises__")
        if not subgroup_keys:
            subgroup_keys = ["__exercises__" if exercises_by_owner else "__direct__"]
        payloads = []
        for subgroup in subgroup_keys:
            atoms = [key for key in visible_atoms if self.subgroup_for(section_key, key) == subgroup]
            owners = [
                key for key in exercises_by_owner
                if owner_group.get(key, "__exercises__") == subgroup
            ]
            if subgroup == "__direct__":
                label = section_title
            elif subgroup == "__exercises__":
                label = "练习与习题"
            else:
                label = str(self.nodes[subgroup]["title"])
            payload = self.group_payload(label, atoms, owners)
            payload.update({"key": subgroup, "owners": owners})
            payloads.append(payload)
        self.place_regions(payloads, radius_floor=900.0)
        groups: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        for order, payload in enumerate(payloads, start=1):
            rect, local = payload["placement"], payload["bounds"]
            offset_x, offset_y = rect[0] - local[0], rect[1] - local[1]
            groups.append({
                "id": stable_id("detail-region", f"{chapter_key}:{section_key}:{payload['key']}"), "type": "group",
                "label": f"{order:02d} · {payload['label']}", "x": rect[0], "y": rect[1],
                "width": rect[2] - rect[0], "height": rect[3] - rect[1],
            })
            for key, position in payload["positions"].items():
                cards.append(self.atom_card(key, canvas_path, (position[0] + offset_x, position[1] + offset_y)))
            for owner, position in payload["extra_positions"].items():
                cards.append(self.exercise_entry_card(owner, len(exercises_by_owner[owner]), canvas_path, (position[0] + offset_x, position[1] + offset_y)))
        hub_link = self.link_text(compact_title(section_title, 40), self.note_target(note_key), canvas_path)
        scope = f"{chapter_key}:{section_key}"
        cards.append(self.map_hub(scope, section_title, "小节细图 · 原子、方法例题与练习入口", (-MAP_HUB_WIDTH // 2, -MAP_HUB_HEIGHT // 2), link=hub_link))
        cards.extend([
            {"id": stable_id("utility", f"{scope}:back"), "type": "text", "text": self.link_text("← 返回章节知识星图", chapter_path, canvas_path), "x": -610, "y": -50, "width": 290, "height": 82},
            {"id": stable_id("utility", f"{scope}:legend"), "type": "text", "text": "**细图图例**\n\n知识主线向右推进\n练习入口只保留一条主归属边", "x": 320, "y": -65, "width": 360, "height": 116},
        ])
        region_of = {key: self.subgroup_for(section_key, key) for key in visible_atoms}
        occupied = [rectangle((int(card["x"]), int(card["y"])), (int(card["width"]), int(card["height"]))) for card in cards]
        hub_keys = self.strict_concept_hubs(visible_set, region_of)
        for index, concept in enumerate(sorted(hub_keys, key=lambda key: (int(self.concepts[key].get("first_source_order", 0)), key))):
            linked = []
            for link in self.links_by_concept.get(concept, []):
                card = next((item for item in cards if item["id"] == stable_id("card", str(link.get("atom_key")))), None)
                if card is not None:
                    linked.append(card)
            preferred = (
                sum(center(item)[0] for item in linked) / len(linked) - CONCEPT_WIDTH / 2,
                sum(center(item)[1] for item in linked) / len(linked) - CONCEPT_HEIGHT / 2,
            ) if linked else (index * 270, 190)
            position = collision_free(preferred, (CONCEPT_WIDTH, CONCEPT_HEIGHT), occupied, len(cards) + index)
            cards.append(self.concept_card(concept, position))
        edges: list[dict[str, Any]] = []
        atom_edges, concept_edges, membership_edges = self.add_semantic_edges(scope, visible_set, hub_keys, cards, edges)
        # One primary practice edge per exercise organizer. Detailed atom-to-exercise
        # evidence remains authoritative in JSON and no longer becomes a line fan.
        exercise_edges = 0
        for owner in sorted(exercises_by_owner, key=lambda key: (self.source_starts[key], key)):
            anchor = primary_anchor.get(owner)
            if anchor is None:
                continue
            edges.append(self.exercise_edge(scope, owner, stable_id("card", anchor), stable_id("exercise-entry", owner), f"练习 · {len(exercises_by_owner[owner])}题", "primary"))
            exercise_edges += 1
        # A single neutral radial entry per detail region creates map-like zoom
        # navigation without pretending to be a semantic relation.
        map_hub_id = stable_id("map-hub", scope)
        for payload in payloads:
            candidates = [stable_id("card", key) for key in payload["atoms"]]
            candidates += [stable_id("exercise-entry", key) for key in payload["owners"]]
            if candidates:
                edges.append(self.navigation_edge(scope, f"region:{payload['key']}", map_hub_id, candidates[0]))
        fallback_edges = self.add_isolation_fallback(scope, visible_atoms, {stable_id("card", key) for key in visible_atoms}, edges)
        all_nodes = [*groups, *cards]
        counts = {
            "cards": len(cards), "groups": len(groups), "edges": len(edges),
            "internal_atoms": len(visible_atoms), "source_atoms": len(source_atoms),
            "exercise_atoms_collapsed": len(exercises), "exercise_organizers": len(exercises_by_owner),
            "exercise_relation_edges": exercise_edges, "concept_hubs": len(hub_keys),
            "atom_relation_edges": atom_edges, "concept_relation_edges": concept_edges,
            "concept_membership_edges": membership_edges, "source_order_fallback_edges": fallback_edges,
            "navigation_nodes": 3, "regions": len(groups), "landmarks": 0,
        }
        return {"nodes": all_nodes, "edges": edges}, {"counts": counts, "bounds": bounds_for(all_nodes), "visual_quality": visual_quality(cards, edges)}

    def build(self) -> tuple[dict[Path, dict[str, Any]], dict[str, Any]]:
        payloads: dict[Path, dict[str, Any]] = {}
        overview_path = self.output_dir / "overview.canvas"
        atlas, atlas_meta = self.overview_canvas(overview_path)
        payloads[overview_path] = atlas
        chapter_entries: list[dict[str, Any]] = []
        section_entries: list[dict[str, Any]] = []
        for chapter in self.chapter_keys:
            if not self.semantic_ready:
                chapter_entries.append({"role": "chapter-knowledge-map", "root_key": chapter, "status": "relation-review-required", "path": None, "counts": None, "bounds": None, "visual_quality": None})
                for section in self.section_keys_by_chapter[chapter]:
                    section_entries.append({"role": "section-detail-map", "chapter_key": chapter, "root_key": section, "status": "relation-review-required", "path": None, "counts": None, "bounds": None, "visual_quality": None})
                continue
            chapter_path = self.chapter_paths[chapter]
            canvas, meta = self.chapter_canvas(chapter_path, chapter, overview_path)
            payloads[chapter_path] = canvas
            chapter_entries.append({"role": "chapter-knowledge-map", "root_key": chapter, "status": "ready", "path": chapter_path.relative_to(self.output_dir).as_posix(), **meta})
            for section in self.section_keys_by_chapter[chapter]:
                section_path = self.section_paths[(chapter, section)]
                section_canvas, section_meta = self.section_canvas(section_path, chapter, section, chapter_path)
                payloads[section_path] = section_canvas
                section_entries.append({"role": "section-detail-map", "chapter_key": chapter, "root_key": section, "status": "ready", "path": section_path.relative_to(self.output_dir).as_posix(), **section_meta})
        index = {
            "schema_version": 3,
            "manifest": str(self.manifest_path),
            "manifest_sha256": self.manifest_sha256(),
            "book_root": str(self.book_root),
            "relation_status": "passed" if self.semantic_ready else "review_required",
            "layout": {
                "mode": "three-level-constellation", "theme": "adaptive",
                "zoom_levels": ["book-chapters", "chapter-core", "section-detail"],
                "learning_direction": "center-outward-clockwise",
                "organization_encoding": "regions-with-click-through-portals",
                "atom_visibility": "chapter-core-and-section-detail",
                "exercise_representation": "chapter-counts-section-primary-entries",
                "concept_hub_visibility": "multi-atom-and-semantic-bridge-only",
                "edge_noise_policy": "one-primary-practice-edge-per-exercise-organizer",
                "edge_ports": {"progression": "right-to-left", "inspiration": "right-to-top", "support-and-containment": "bottom-to-top"},
            },
            "atlas": {"role": "book-atlas", "root_key": self.root_key, "path": "overview.canvas", **atlas_meta},
            "chapter_maps": chapter_entries,
            "section_maps": section_entries,
        }
        return payloads, index

    def manifest_sha256(self) -> str:
        from build_canvas import sha256_file
        return sha256_file(self.manifest_path)


def summarize_bundle(index: dict[str, Any], payload_count: int) -> dict[str, Any]:
    return {
        "status": "passed", "canvases": payload_count,
        "atlas": str(Path(str(index["book_root"])) / str(index["atlas"]["path"])),
        "chapter_maps": sum(item.get("status") == "ready" for item in index["chapter_maps"]),
        "section_maps": sum(item.get("status") == "ready" for item in index["section_maps"]),
        "relation_status": index["relation_status"],
    }
