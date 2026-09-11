#!/usr/bin/env python3
"""Three-scale, level-of-detail knowledge constellation Canvas builder."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from compact_layout import CARD_GAP, REGION_GAP, RIGHT_GAP, DOWN_GAP, group_box, leaf_box

from build_canvas import (
    ATOM_COLORS,
    ATOM_HEIGHT,
    ATOM_WIDTH,
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
            f"{prefix} {self.atom_label(node)} · {self.display_title(key)}",
            self.note_target(key),
            canvas_path,
        )
        return card

    @staticmethod
    def atom_label(node: dict[str, Any]) -> str:
        if node.get("category") == "scenario" and node.get("scenario_role") == "reflection-question":
            return "思考题"
        category = str(node["category"])
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

    def compact_map(
        self, canvas_path: Path, chapter_key: str, section_key: str | None, back_path: Path,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        chapter_level = section_key is None
        root = chapter_key if chapter_level or section_key == "__chapter_intro__" else str(section_key)
        scope = chapter_key if chapter_level else f"{chapter_key}:{section_key}"
        source_atoms = (
            [str(key) for key in self.nodes[chapter_key].get("children", []) if self.nodes[str(key)].get("layer") == "atom"]
            if section_key == "__chapter_intro__" else
            [key for key in descendants(self.nodes, root)[1:] if self.nodes[key].get("layer") == "atom"]
        )
        source_atoms.sort(key=lambda key: (self.source_starts[key], key))
        visible = [key for key in source_atoms if self.visible_atom(key)]
        visible_set = set(visible)
        exercises = [key for key in source_atoms if self.nodes[key].get("category") == "exercise"]
        owner_by_exercise, by_owner = self.exercise_owners(chapter_key, exercises)
        cards = [self.atom_card(key, canvas_path, (0, 0)) for key in visible]
        owners = {stable_id("card",key): str(self.nodes[key]["parent_key"]) for key in visible}
        order = {stable_id("card",key): (self.source_starts[key],key) for key in visible}
        region_of = {key: self.section_for(chapter_key,key) for key in visible}
        hub_keys = self.strict_concept_hubs(visible_set,region_of)

        def ancestors(key: str) -> list[str]:
            chain = [key]
            while chain[-1] != root:
                parent = self.nodes[chain[-1]].get("parent_key")
                if parent is None:
                    raise ValueError(f"Canvas node is outside its map: {key}")
                chain.append(str(parent))
            return chain

        for concept in sorted(hub_keys):
            grounded = [str(link["atom_key"]) for link in self.links_by_concept[concept] if str(link["atom_key"]) in visible_set]
            chains = [ancestors(str(self.nodes[key]["parent_key"])) for key in grounded]
            common = next(key for key in chains[0] if all(key in chain for chain in chains))
            card = self.concept_card(concept,(0,0))
            cards.append(card)
            owners[card["id"]] = common
            order[card["id"]] = (min(self.source_starts[key] for key in grounded),concept)
        edges: list[dict[str, Any]] = []
        atom_edges, concept_edges, concept_memberships = self.add_semantic_edges(scope,visible_set,hub_keys,cards,edges)
        portals: dict[str,str] = {}
        if chapter_level:
            for section in self.section_keys_by_chapter[chapter_key]:
                section_owner = chapter_key if section == "__chapter_intro__" else section
                atoms = [key for key in visible if region_of[key] == section]
                card = self.section_portal_card(chapter_key,section,canvas_path,(0,0),len(atoms),
                    sum(self.section_for(chapter_key,key) == section for key in exercises))
                cards.append(card)
                owners[card["id"]] = section_owner
                order[card["id"]] = (self.source_starts[section_owner]-1,card["id"])
                portals[section_owner] = card["id"]

        # Practice anchors must be knowledge, even when the nearest source text
        # is a reflection question. A proximity-only fallback states ownership,
        # not an unreviewed practice relation.
        practice_edges = ownership_practice = 0
        if not chapter_level:
            support: dict[str,Counter[str]] = defaultdict(Counter)
            for relation in self.relations:
                left,right = str(relation["from_key"]),str(relation["to_key"])
                for teaching,exercise in ((left,right),(right,left)):
                    if exercise in owner_by_exercise and teaching in visible_set and self.nodes[teaching]["category"] == "knowledge":
                        support[owner_by_exercise[exercise]][teaching] += 1
            knowledge = [key for key in visible if self.nodes[key]["category"] == "knowledge"]
            for owner in sorted(by_owner,key=lambda key:(self.source_starts[key],key)):
                card = self.exercise_entry_card(owner,len(by_owner[owner]),canvas_path,(0,0))
                cards.append(card)
                owners[card["id"]] = owner
                order[card["id"]] = (self.source_starts[owner]+0.5,owner)
                candidates = support.get(owner,Counter())
                if candidates:
                    anchor = min(candidates,key=lambda key:(-candidates[key],abs(self.source_starts[key]-self.source_starts[owner]),key))
                    label = f"练习 · {len(by_owner[owner])}题"
                    practice_edges += 1
                elif knowledge:
                    anchor = min(knowledge,key=lambda key:(
                        0 if str(self.nodes[key]["parent_key"]) == owner else 1,
                        abs(self.source_starts[key]-self.source_starts[owner]),key))
                    label = f"归属 · {len(by_owner[owner])}题"
                    ownership_practice += 1
                else:
                    continue
                edges.append(self.exercise_edge(scope,owner,stable_id("card",anchor),card["id"],label,"primary"))

        # Symmetric edges have no prerequisite direction. Orient their drawing
        # consistently by reading order without modifying authoritative JSON.
        for edge in edges:
            if edge.get("fromEnd") == "none" and edge.get("toEnd") == "none":
                if order[edge["fromNode"]] > order[edge["toNode"]]:
                    edge["fromNode"],edge["toNode"] = edge["toNode"],edge["fromNode"]
        incident = {str(value) for edge in edges for value in (edge["fromNode"],edge["toNode"])}
        memberships = 0
        for key in visible:
            node_id = stable_id("card",key)
            if node_id in incident:
                continue
            owner = str(self.nodes[key]["parent_key"])
            if owner not in portals:
                portal_id = stable_id("organizer-entry",f"{scope}:{owner}")
                cards.append({
                    "id":portal_id,"type":"text",
                    "text":self.link_text(f"§ {self.display_title(owner)}",self.note_target(owner),canvas_path),
                    "x":0,"y":0,"width":260,"height":66,
                })
                owners[portal_id] = owner
                order[portal_id] = (self.source_starts[owner]+0.5,portal_id)
                portals[owner] = portal_id
            edges.append({
                "id":stable_id("edge",f"{scope}:membership:{key}"),
                "fromNode":node_id,"toNode":portals[owner],"fromSide":"bottom","toSide":"top",
                "label":"归属","color":SOURCE_ORDER_COLOR,"fromEnd":"none","toEnd":"arrow",
            })
            memberships += 1
        cards_by_id = {str(card["id"]):card for card in cards}
        group_keys = {key for owner in owners.values() for key in ancestors(owner)}
        children: dict[str,list[str]] = defaultdict(list)
        for key in group_keys:
            if key != root:
                children[str(self.nodes[key]["parent_key"])].append(key)
        direct_cards: dict[str,list[str]] = defaultdict(list)
        for card_id, owner in owners.items():
            direct_cards[owner].append(card_id)
        group_records = []

        def compose(key: str):
            items = [(self.source_starts[child],child,False) for child in children.get(key,[])]
            items += [(order[card_id][0],card_id,True) for card_id in direct_cards.get(key,[])]
            boxes = [leaf_box(cards_by_id[value]) if is_card else compose(value)
                     for _,value,is_card in sorted(items)]
            group_id = stable_id("organizer-group-v4",f"{scope}:{key}")
            title = self.display_title(key)
            if chapter_level and key in self.section_keys_by_chapter[chapter_key]:
                title = f"{self.section_keys_by_chapter[chapter_key].index(key)+1:02d} · {title}"
            box = group_box(key,title,boxes,edges,group_id)
            group_records.append({
                "organizer_key":key,"node_id":group_id,
                "parent_id":None if key == root else stable_id("organizer-group-v4",f"{scope}:{self.nodes[key]['parent_key']}"),
                "member_ids":sorted(box.members),
            })
            return box

        root_box = compose(root)
        all_nodes = root_box.nodes
        # A quiet header preserves navigation without a hub-and-spoke fan.
        title = "章引入" if section_key == "__chapter_intro__" else str(self.nodes[root]["title"])
        header_y = -180
        all_nodes.extend([
            self.map_hub(scope,title,"知识分簇 · 沿连线阅读",
                (0,header_y),link=self.link_text(compact_title(title,40),self.note_target(root),canvas_path)),
            {"id":stable_id("utility",f"{scope}:back:compact"),"type":"text",
             "text":self.link_text("← 返回全书" if chapter_level else "← 返回章节",back_path,canvas_path),
             "x":MAP_HUB_WIDTH+CARD_GAP,"y":header_y,"width":230,"height":66},
            {"id":stable_id("utility",f"{scope}:legend:compact"),"type":"text",
             "text":"✦ 知识主线　→ 发展／推导\n↓ 应用／并列　分组框＝组织层",
             "x":MAP_HUB_WIDTH+CARD_GAP+230+CARD_GAP,"y":header_y,"width":400,"height":86},
        ])
        counts = {
            "cards":len(cards)+3,"groups":len(group_records),"edges":len(edges),
            "internal_atoms":len(visible),"source_atoms":len(source_atoms),
            "knowledge_atoms":sum(self.nodes[key]["category"] == "knowledge" for key in visible),
            "scenario_atoms":sum(self.nodes[key]["category"] == "scenario" for key in visible),
            "featured_examples":sum(self.nodes[key]["category"] == "worked-example" for key in visible),
            "exercise_atoms_summarized":len(exercises) if chapter_level else 0,
            "exercise_atoms_collapsed":0 if chapter_level else len(exercises),
            "exercise_portals":len(self.section_keys_by_chapter[chapter_key]) if chapter_level else 0,
            "exercise_organizers":0 if chapter_level else len(by_owner),
            "exercise_relation_edges":practice_edges,"exercise_ownership_edges":ownership_practice,
            "concept_hubs":len(hub_keys),"atom_relation_edges":atom_edges,
            "concept_relation_edges":concept_edges,"concept_membership_edges":concept_memberships,
            "source_order_fallback_edges":0,"organization_membership_edges":memberships,
            "navigation_nodes":3+len(portals),"regions":len(children.get(root,[])),"landmarks":0,
        }
        return {"nodes":all_nodes,"edges":edges}, {
            "counts":counts,"bounds":bounds_for(all_nodes),
            "visual_quality":visual_quality(all_nodes,edges),"organization_groups":group_records,
        }

    def chapter_canvas(self, canvas_path: Path, chapter_key: str, overview_path: Path):
        return self.compact_map(canvas_path,chapter_key,None,overview_path)

    def section_canvas(self, canvas_path: Path, chapter_key: str, section_key: str, chapter_path: Path):
        return self.compact_map(canvas_path,chapter_key,section_key,chapter_path)

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
                "learning_direction": "edge-constrained-clusters",
                "organization_encoding": "regions-and-organizer-groups",
                "atom_visibility": "chapter-core-and-section-detail",
                "exercise_representation": "chapter-counts-section-primary-entries",
                "concept_hub_visibility": "hidden" if self.canvas_config.get("concept_nodes") == "hidden" else "multi-atom-and-semantic-bridge-only",
                "edge_noise_policy": "semantic-or-labelled-membership" if self.isolation_policy == "semantic-or-labelled-membership" else "one-primary-practice-edge-per-exercise-organizer",
                "edge_ports": {"progression": "right-to-left", "inspiration": "right-to-top", "support-and-containment": "bottom-to-top"},
                "revision": "compact-v1",
                "navigation": "unconnected-header-and-local-portals",
                "direction_constraints": {"right_outgoing": "target.left>=source.right+gap", "bottom_outgoing": "target.top>=source.bottom+gap"},
                "spacing": {"node_margin": CARD_GAP, "region_gap": REGION_GAP, "right_gap": RIGHT_GAP, "down_gap": DOWN_GAP},
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
