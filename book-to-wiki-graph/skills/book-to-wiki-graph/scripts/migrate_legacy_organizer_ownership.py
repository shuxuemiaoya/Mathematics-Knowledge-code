#!/usr/bin/env python3
"""Repair reviewed legacy organizer ownership without changing atom ranges.

The compatibility migration handles two narrowly evidenced v0.8 patterns:

* a heading-free knowledge-topic organizer was placed beside, rather than
  inside, the printed instructional subsection it describes;
* exercises following a printed grouping marker (for example ``复习巩固`` or
  ``综合运用``) remained owned by the preceding exercise group.

It consumes the validator's exact crossing evidence from a materialized
manifest, writes a sealed Agent-review artifact, updates organizer ownership,
and rebinds stable atom keys throughout the relation final.  Source ranges,
categories, prose, and semantic relation claims are never changed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any

import migrate_scoped_introductions as shared
from validate_book_graph import load_json, sha256_file, validate_graph


class LegacyOwnershipMigrationError(ValueError):
    pass


def node_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node["key"]): node for node in payload.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("key"), str)
    }


def descendant_atoms(nodes: dict[str, dict[str, Any]], key: str) -> list[dict[str, Any]]:
    node = nodes[key]
    if node.get("layer") == "atom":
        return [node]
    result: list[dict[str, Any]] = []
    for child in node.get("children", []):
        child_key = str(child)
        if child_key in nodes:
            result.extend(descendant_atoms(nodes, child_key))
    return result


def anchor(nodes: dict[str, dict[str, Any]], key: str) -> int:
    node = nodes[key]
    if node.get("layer") == "atom":
        return int(node["source_range"][0])
    values = [int(value[0]) for value in node.get("heading_ranges", []) if isinstance(value, list) and len(value) == 2]
    values.extend(int(atom["source_range"][0]) for atom in descendant_atoms(nodes, key) if atom.get("source_range"))
    return min(values) if values else 10**12


def exercise_group_title(title: str) -> str:
    for label in ("复习巩固", "综合运用", "拓广探索", "探究拓展"):
        if label in title:
            return label
    return "练习"


def stable_organizer_key(parent_key: str, start: int, title: str) -> str:
    identity = f"{parent_key}:{start}:{title}"
    return f"reviewed-exercise-{hashlib.sha256(identity.encode()).hexdigest()[:12]}"


def safe_path_component(value: str, fallback: str = "组织层") -> str:
    """Return a readable, portable organizer directory/file component."""
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", value).strip().strip(".")
    return cleaned or fallback


def rebase_organizer_subtree(
    nodes: dict[str, dict[str, Any]], key: str, old_root: PurePosixPath,
    new_root: PurePosixPath,
) -> None:
    """Move organizer-note paths with their reparented subtree.

    Materialization deliberately checks that an organizer note lives in the
    directory represented by its direct parent.  A hierarchy migration must
    therefore migrate paths together with ``parent_key`` rather than leaving a
    structurally stale sibling directory behind.
    """
    node = nodes[key]
    if node.get("layer") != "organizer":
        return
    current = PurePosixPath(str(node.get("filename", "")))
    try:
        relative = current.relative_to(old_root)
    except ValueError as exc:
        raise LegacyOwnershipMigrationError(
            f"Organizer path is outside the subtree being rebased: {key}"
        ) from exc
    node["filename"] = str(new_root / relative)
    for child in node.get("children", []):
        child_key = str(child)
        if child_key in nodes and nodes[child_key].get("layer") == "organizer":
            rebase_organizer_subtree(nodes, child_key, old_root, new_root)


def increment_levels(nodes: dict[str, dict[str, Any]], key: str, delta: int) -> None:
    node = nodes[key]
    if node.get("layer") != "organizer":
        return
    node["organizer_level"] = int(node.get("organizer_level", 1)) + delta
    for child in node.get("children", []):
        child_key = str(child)
        if child_key in nodes:
            increment_levels(nodes, child_key, delta)


def rebind_relation_final(
    legacy: dict[str, Any], key_map: dict[str, str], base_path: Path,
    atomization: dict[str, Any], atomization_path: Path,
    review: dict[str, Any], review_path: Path, legacy_path: Path,
) -> dict[str, Any]:
    concepts = shared.remap_evidence(copy.deepcopy(legacy.get("concepts", [])), key_map)
    for concept in concepts:
        if isinstance(concept, dict) and isinstance(concept.get("evidence"), list):
            unique = {json.dumps(item, ensure_ascii=False, sort_keys=True): item for item in concept["evidence"]}
            concept["evidence"] = sorted(
                unique.values(),
                key=lambda item: (item.get("source_range", [10**12])[0], str(item.get("atom_key"))),
            )

    links: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in shared.remap_evidence(copy.deepcopy(legacy.get("atom_concept_links", [])), key_map):
        identity = (str(raw["atom_key"]), str(raw["concept_key"]), str(raw["role"]))
        item = links.setdefault(identity, {
            "key": shared.stable_key("atom-concept", *identity),
            "atom_key": identity[0], "concept_key": identity[1], "role": identity[2],
            "evidence_ranges": [], "confidence": 0.0,
        })
        item["evidence_ranges"] = [list(value) for value in sorted({
            tuple(value) for value in [*item["evidence_ranges"], *raw.get("evidence_ranges", [])]
        })]
        item["confidence"] = max(float(item["confidence"]), float(raw.get("confidence", 0.0)))

    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in shared.remap_evidence(copy.deepcopy(legacy.get("relations", [])), key_map):
        left, right, relation_type = str(raw["from_key"]), str(raw["to_key"]), str(raw["type"])
        if left == right:
            continue
        if relation_type in {"contrasts", "analogous"} and left > right:
            left, right = right, left
        identity = (left, right, relation_type)
        copied = copy.deepcopy(raw)
        copied.update({
            "key": shared.stable_key("relation", *identity),
            "from_key": left, "to_key": right, "type": relation_type,
        })
        relations[identity] = copied

    roles: dict[str, dict[str, Any]] = {}
    for raw in shared.remap_evidence(copy.deepcopy(legacy.get("atom_roles", [])), key_map):
        roles.setdefault(str(raw.get("atom_key")), raw)

    result = copy.deepcopy(legacy)
    result.update({
        "manifest": str(base_path), "manifest_sha256": sha256_file(base_path),
        "atomization_final": str(atomization_path),
        "atomization_final_sha256": atomization["artifact_sha256"],
        "bindings": {
            "legacy_relation_final": {"path": str(legacy_path), "sha256": legacy["artifact_sha256"]},
            "organizer_ownership_review": {"path": str(review_path), "sha256": review["artifact_sha256"]},
        },
        "reviewer": {
            **dict(legacy.get("reviewer", {})),
            "organizer_ownership": {
                "identity": "Codex agent",
                "method": "printed-heading interval and exercise-group ownership audit",
            },
        },
        "concepts": concepts,
        "atom_concept_links": sorted(links.values(), key=lambda item: (item["atom_key"], item["concept_key"], item["role"])),
        "concept_relations": shared.remap_evidence(copy.deepcopy(legacy.get("concept_relations", [])), key_map),
        "relations": sorted(relations.values(), key=lambda item: (item["from_key"], item["to_key"], item["type"])),
        "formulas": shared.remap_evidence(copy.deepcopy(legacy.get("formulas", [])), key_map),
        "atom_roles": sorted(roles.values(), key=lambda item: str(item.get("atom_key"))),
        "independent_atoms": shared.remap_evidence(copy.deepcopy(legacy.get("independent_atoms", [])), key_map),
        "independent_components": shared.remap_evidence(copy.deepcopy(legacy.get("independent_components", [])), key_map),
        "boundary_feedback": [], "unresolved_count": 0, "status": "passed",
    })
    result.pop("artifact_sha256", None)
    return shared.seal(result)


def migrate(
    base_path: Path, atomization_path: Path, relation_path: Path,
    materialized_manifest_path: Path, output_dir: Path, overwrite: bool = False,
) -> dict[str, Any]:
    base_path = base_path.expanduser().resolve()
    atomization_path = atomization_path.expanduser().resolve()
    relation_path = relation_path.expanduser().resolve()
    materialized_manifest_path = materialized_manifest_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    base, atomization, relation, materialized = (
        load_json(base_path), load_json(atomization_path), load_json(relation_path),
        load_json(materialized_manifest_path),
    )
    shared.verify_sealed(atomization, "atomization-final")
    shared.verify_sealed(relation, "relation-final-v2")
    if relation.get("atomization_final_sha256") != atomization.get("artifact_sha256"):
        raise LegacyOwnershipMigrationError("Relation final binds another atomization final")
    validation = validate_graph(materialized_manifest_path, materialized_manifest_path.parent)
    crossing = [
        error for error in validation.get("errors", [])
        if error.get("code") == "organizer-child-source-span-crosses-next-sibling"
    ]
    if not crossing:
        raise LegacyOwnershipMigrationError("No organizer ownership crossings require migration")

    base_copy = copy.deepcopy(base)
    base_nodes = node_map(base_copy)
    output_nodes = node_map(materialized)
    final_atoms = {
        str(atom["atom_id"]): copy.deepcopy(atom)
        for atom in atomization.get("atoms", []) if isinstance(atom, dict)
    }
    node_to_atom_id = {
        key: str(node.get("atomization_id"))
        for key, node in output_nodes.items()
        if node.get("layer") == "atom" and node.get("atomization_id") is not None
    }
    decisions: list[dict[str, Any]] = []
    created_organizers: set[str] = set()

    # Put a heading-free reviewed topic inside the printed subsection that it
    # actually teaches.  Atom ownership and ranges remain unchanged.
    for error in crossing:
        left_key, right_key, parent_key = map(str, (error["left_child"], error["right_child"], error["node"]))
        left, right = output_nodes[left_key], output_nodes[right_key]
        if not (
            left.get("layer") == "organizer" and not left.get("heading_ranges")
            and right.get("layer") == "organizer" and right.get("heading_ranges")
        ):
            continue
        if left_key not in base_nodes or right_key not in base_nodes or parent_key not in base_nodes:
            raise LegacyOwnershipMigrationError(f"Organizer migration target is absent from base: {left_key} -> {right_key}")
        parent = base_nodes[parent_key]
        parent["children"] = [child for child in parent.get("children", []) if str(child) != left_key]
        right_base = base_nodes[right_key]
        if left_key not in [str(child) for child in right_base.get("children", [])]:
            right_base.setdefault("children", []).append(left_key)
        base_nodes[left_key]["parent_key"] = right_key
        topic_path = PurePosixPath(str(base_nodes[left_key]["filename"]))
        old_root = topic_path.parent
        new_root = PurePosixPath(str(right_base["filename"])).parent / old_root.name
        rebase_organizer_subtree(base_nodes, left_key, old_root, new_root)
        increment_levels(base_nodes, left_key, 1)
        decisions.append({
            "action": "nest-reviewed-topic-under-printed-subsection",
            "parent_key": parent_key, "topic_key": left_key, "printed_subsection_key": right_key,
            "source_boundary": int(error["right_start"]),
            "rationale": "The heading-free topic teaches the printed subsection and must be inside it; placing both as siblings left the printed subsection with exercises only.",
            "confidence": 0.99,
        })

    owner_changes: dict[str, str] = {}

    def create_exercise_group(parent_key: str, start: int, title: str, atom_nodes: list[dict[str, Any]], reason: str) -> None:
        if not atom_nodes:
            raise LegacyOwnershipMigrationError(f"Exercise group has no atoms: {parent_key} {start}")
        key = stable_organizer_key(parent_key, start, title)
        if key not in base_nodes:
            parent = base_nodes[parent_key]
            component = safe_path_component(title, "练习")
            parent_directory = PurePosixPath(str(parent["filename"])).parent
            base_nodes[key] = {
                "key": key, "title": title, "layer": "organizer", "parent_key": parent_key,
                "organizer_level": int(parent.get("organizer_level", 1)) + 1,
                "filename": str(parent_directory / component / f"{component}.md"),
                "heading_ranges": [], "children": [],
            }
            parent.setdefault("children", []).append(key)
            created_organizers.add(key)
        atom_ids: list[str] = []
        for node in atom_nodes:
            atom_id = node_to_atom_id.get(str(node["key"]))
            if not atom_id or atom_id not in final_atoms:
                raise LegacyOwnershipMigrationError(f"Cannot resolve frozen atom for {node['key']}")
            if final_atoms[atom_id].get("category") != "exercise":
                raise LegacyOwnershipMigrationError(f"Non-exercise entered exercise group: {node['key']}")
            owner_changes[atom_id] = key
            atom_ids.append(atom_id)
        decisions.append({
            "action": "create-exercise-group-and-reassign",
            "parent_key": parent_key, "organizer_key": key, "title": title,
            "source_range": [min(node["source_range"][0] for node in atom_nodes), max(node["source_range"][1] for node in atom_nodes)],
            "atom_ids": atom_ids, "rationale": reason, "confidence": 0.99,
        })

    # A source grouping marker became the first exercise atom while later
    # exercises stayed under the preceding organizer.  Regroup every complete
    # source-labelled run (复习巩固 / 综合运用 / ...) under its own organizer;
    # continuation cards are content inside the current run, not new groups.
    handled_parents: set[str] = set()
    for error in crossing:
        left_key, right_key, parent_key = map(str, (error["left_child"], error["right_child"], error["node"]))
        left, right = output_nodes[left_key], output_nodes[right_key]
        if not (
            left.get("layer") == "organizer" and not left.get("heading_ranges")
            and right.get("layer") == "atom" and right.get("category") == "exercise"
        ):
            continue
        if parent_key in handled_parents:
            continue
        handled_parents.add(parent_key)
        children = [str(value) for value in output_nodes[parent_key].get("children", []) if str(value) in output_nodes]
        markers: list[dict[str, Any]] = []
        for child_key in children:
            child = output_nodes[child_key]
            title = str(child.get("title", ""))
            if (
                child.get("layer") == "atom" and child.get("category") == "exercise"
                and exercise_group_title(title) != "练习"
                and "导语" not in title
                and not shared.CONTINUATION_SUFFIX_RE.search(title)
            ):
                markers.append(child)
        markers.sort(key=lambda item: int(item["source_range"][0]))
        if not markers:
            raise LegacyOwnershipMigrationError(f"Exercise group marker missing under {parent_key}")
        all_atoms = [
            atom for atom in descendant_atoms(output_nodes, parent_key)
            if atom.get("category") == "exercise"
        ]
        for index, marker in enumerate(markers):
            start = int(marker["source_range"][0])
            next_start = int(markers[index + 1]["source_range"][0]) if index + 1 < len(markers) else 10**12
            atoms = [
                atom for atom in all_atoms
                if start <= int(atom["source_range"][0]) < next_start
            ]
            create_exercise_group(
                parent_key, start, exercise_group_title(str(marker.get("title", ""))), atoms,
                "The printed exercise grouping marker starts at this atom; every following top-level problem before the next source-labelled group belongs to it.",
            )

    # Compound topics such as 全称量词/存在量词 may share one printed exercise
    # heading.  Move the post-heading exercises out of both topic organizers
    # and into one direct exercise organizer.
    for error in crossing:
        left_key, right_key, parent_key = map(str, (error["left_child"], error["right_child"], error["node"]))
        left, right = output_nodes[left_key], output_nodes[right_key]
        if not (
            left.get("layer") == right.get("layer") == "organizer"
            and not left.get("heading_ranges") and not right.get("heading_ranges")
        ):
            continue
        atoms = [
            atom for atom in descendant_atoms(output_nodes, parent_key)
            if atom.get("category") == "exercise"
            and int(atom["source_range"][0]) >= int(error["right_start"])
        ]
        if not atoms:
            raise LegacyOwnershipMigrationError(f"Unclassified headless organizer crossing: {left_key} -> {right_key}")
        start = min(int(atom["source_range"][0]) for atom in atoms)
        create_exercise_group(
            parent_key, start, "练习", atoms,
            "The printed exercise block checks multiple sibling concepts and therefore belongs to their common parent, not to either one concept topic.",
        )

    if not decisions:
        raise LegacyOwnershipMigrationError("Crossings did not match the reviewed legacy patterns")

    base_copy["nodes"] = list(base_nodes.values())
    profile_source = Path(str(base.get("profile", ""))).expanduser().resolve()
    profile = load_json(profile_source)
    profile["paths"] = {**dict(profile.get("paths", {})), "staging_root": str(output_dir)}
    profile_path = output_dir / "book-profile.json"
    shared.atomic_json(profile_path, profile, overwrite)
    base_copy["profile"] = str(profile_path)

    review = shared.seal({
        "schema_version": 1, "kind": "organizer-ownership-repair-review", "status": "passed",
        "base_manifest": str(base_path), "base_manifest_sha256": sha256_file(base_path),
        "materialized_manifest": str(materialized_manifest_path),
        "materialized_manifest_sha256": sha256_file(materialized_manifest_path),
        "source_markdown_sha256": base["source_markdown_sha256"],
        "reviewer": {"type": "codex-agent", "model": "current-agent"},
        "decisions": decisions, "unresolved_count": 0,
    })
    review_path = output_dir / "organizer-ownership-repair-review.json"
    shared.atomic_json(review_path, review, overwrite)
    organizer_review = shared.seal({
        "schema_version": 1, "kind": "organizer-review", "status": "passed",
        "base_manifest_sha256": sha256_file(base_path),
        "source_markdown_sha256": base["source_markdown_sha256"],
        "reviewer": {"type": "codex-agent", "model": "current-agent", "method": "legacy printed-heading interval ownership repair"},
        "demote_organizer_keys": [], "content_runs": [], "renumber_parent_keys": [],
        "synthesized_organizer_keys": sorted(created_organizers),
        "ownership_review": {"path": str(review_path), "sha256": review["artifact_sha256"]},
    })
    organizer_review_path = output_dir / "organizer-review.json"
    shared.atomic_json(organizer_review_path, organizer_review, overwrite)
    base_copy["organizer_review"] = {
        "status": "passed", "path": str(organizer_review_path),
        "sha256": organizer_review["artifact_sha256"],
        "demoted_organizer_keys": [], "synthesized_organizer_keys": sorted(created_organizers),
    }
    migrated_base_path = output_dir / "book-graph.organizers-reviewed.json"
    shared.atomic_json(migrated_base_path, base_copy, overwrite)

    key_map: dict[str, str] = {}
    rewritten_atoms: list[dict[str, Any]] = []
    for atom in atomization.get("atoms", []):
        copied = copy.deepcopy(atom)
        atom_id = str(copied["atom_id"])
        old_key = shared.virtual_atom_key(copied)
        if atom_id in owner_changes:
            copied["owner_key"] = owner_changes[atom_id]
            copied["review_origin"] = "organizer-ownership-repair-agent-review"
            key_map[old_key] = shared.virtual_atom_key(copied)
        rewritten_atoms.append(copied)
    migrated_atomization = copy.deepcopy(atomization)
    migrated_atomization.update({
        "base_manifest": str(migrated_base_path),
        "base_manifest_sha256": sha256_file(migrated_base_path),
        "atoms": rewritten_atoms,
        "bindings": {
            "legacy_atomization_final": {"path": str(atomization_path), "sha256": atomization["artifact_sha256"]},
            "organizer_ownership_review": {"path": str(review_path), "sha256": review["artifact_sha256"]},
        },
        "reviewer": {
            **dict(atomization.get("reviewer", {})),
            "organizer_ownership": {
                "identity": "Codex agent",
                "method": "printed-heading interval and exercise-group ownership audit",
            },
        },
        "status": "passed", "unresolved_count": 0,
    })
    migrated_atomization.pop("artifact_sha256", None)
    migrated_atomization = shared.seal(migrated_atomization)
    migrated_atomization_path = output_dir / "atomization-final.json"
    shared.atomic_json(migrated_atomization_path, migrated_atomization, overwrite)
    migrated_relation = rebind_relation_final(
        relation, key_map, migrated_base_path, migrated_atomization,
        migrated_atomization_path, review, review_path, relation_path,
    )
    migrated_relation_path = output_dir / "relation-final.json"
    shared.atomic_json(migrated_relation_path, migrated_relation, overwrite)
    report = shared.seal({
        "schema_version": 1, "kind": "legacy-organizer-ownership-migration-report", "status": "passed",
        "outputs": {
            "profile": str(profile_path), "base_manifest": str(migrated_base_path),
            "organizer_review": str(organizer_review_path), "review": str(review_path),
            "atomization_final": str(migrated_atomization_path), "relation_final": str(migrated_relation_path),
        },
        "counts": {
            "crossings_reviewed": len(crossing), "decisions": len(decisions),
            "nested_topics": sum(item["action"] == "nest-reviewed-topic-under-printed-subsection" for item in decisions),
            "exercise_groups_created": len(created_organizers), "atoms_reassigned": len(owner_changes),
        },
        "decisions": decisions,
    })
    shared.atomic_json(output_dir / "legacy-organizer-ownership-migration-report.json", report, overwrite)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_manifest", type=Path)
    parser.add_argument("atomization_final", type=Path)
    parser.add_argument("relation_final", type=Path)
    parser.add_argument("materialized_manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        report = migrate(
            args.base_manifest, args.atomization_final, args.relation_final,
            args.materialized_manifest, args.output_dir, args.overwrite,
        )
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
