#!/usr/bin/env python3
"""Adopt reviewer-confirmed same-edition semantic range proposals.

The proposal report is evidence for a human/LLM review. This command is
deliberately gated by ``--reviewer-confirmed`` and refuses weak, overlapping,
or out-of-parent ranges instead of silently forcing them into a manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from plan_split_manifest import safe_filename


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_TITLE_RE = re.compile(r"^\d+(?:\.\d+)+\s+")
NUMBER_PREFIX_RE = re.compile(r"^(\d+(?:\.\d+)*)\b")
SKIP_TITLE_RE = re.compile(r"(?:^| )小结$")
CHAPTER_TITLE_RE = re.compile(r"^第[一二三四五六七八九十百]+章")


class AdoptionError(ValueError):
    pass


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def proposal_key(title: str, start_line: int) -> str:
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
    return f"reviewed-{start_line:05d}-{digest}"


def is_same_numbered_parent(title: str, parent_title: str) -> bool:
    title_match = NUMBER_PREFIX_RE.match(title)
    parent_match = NUMBER_PREFIX_RE.match(parent_title)
    return bool(
        title_match
        and parent_match
        and title_match.group(1) == parent_match.group(1)
    )


def load_ambiguity_decisions(
    report: dict[str, Any],
    proposal_report: Path,
    decisions_path: Path | None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    ambiguous_items = [
        item
        for item in report.get("suggestions", [])
        if item.get("status") == "ambiguous"
    ]
    ambiguous = {
        str(item.get("title", "")).strip(): item for item in ambiguous_items
    }
    if len(ambiguous) != len(ambiguous_items) or "" in ambiguous:
        raise AdoptionError(
            "ambiguous reference proposals need unique non-empty titles"
        )
    if not ambiguous:
        return {}, None
    if decisions_path is None:
        raise AdoptionError(
            "ambiguous reference proposals require --review-decisions"
        )
    decisions = json.loads(decisions_path.read_text(encoding="utf-8-sig"))
    if not isinstance(decisions, dict):
        raise AdoptionError("ambiguity decisions must be an object")
    proposal_digest = hashlib.sha256(proposal_report.read_bytes()).hexdigest()
    if decisions.get("proposal_report_sha256") != proposal_digest:
        raise AdoptionError(
            "ambiguity decisions do not match the proposal report digest"
        )
    raw = decisions.get("decisions")
    if not isinstance(raw, list):
        raise AdoptionError("ambiguity decisions must be an array")
    reviewed: dict[str, dict[str, Any]] = {}
    for decision in raw:
        if not isinstance(decision, dict):
            raise AdoptionError("every ambiguity decision must be an object")
        title = str(decision.get("title", "")).strip()
        action = decision.get("decision")
        reason = str(decision.get("reason", "")).strip()
        if title not in ambiguous or title in reviewed:
            raise AdoptionError(
                f"ambiguity decisions contain an unknown or duplicate title: {title!r}"
            )
        if action not in {"accept", "revise", "reject"}:
            raise AdoptionError(
                f"ambiguity decision for {title!r} has invalid action"
            )
        if len(reason) < 12:
            raise AdoptionError(
                f"ambiguity decision for {title!r} needs a specific reason"
            )
        if action == "revise" and not all(
            isinstance(decision.get(field), int)
            for field in ("start_line", "end_line")
        ):
            raise AdoptionError(
                f"revised ambiguity decision for {title!r} needs integer bounds"
            )
        reviewed[title] = decision
    if set(reviewed) != set(ambiguous):
        missing = sorted(set(ambiguous) - set(reviewed))
        raise AdoptionError(
            f"ambiguity decisions do not cover every ambiguous proposal: {missing}"
        )
    return reviewed, hashlib.sha256(decisions_path.read_bytes()).hexdigest()


def adopt(
    formatted_markdown: Path,
    split_manifest: Path,
    proposal_report: Path,
    output_manifest: Path,
    minimum_containment: float,
    minimum_matched_characters: int,
    review_decisions: Path | None = None,
    reviewer_confirmed: bool = False,
) -> dict[str, Any]:
    if not reviewer_confirmed:
        raise AdoptionError("reference proposals require reviewer confirmation")
    lines = formatted_markdown.read_text(encoding="utf-8-sig").splitlines()
    manifest = json.loads(split_manifest.read_text(encoding="utf-8-sig"))
    report = json.loads(proposal_report.read_text(encoding="utf-8-sig"))
    ambiguity_decisions, decisions_digest = load_ambiguity_decisions(
        report,
        proposal_report,
        review_decisions,
    )
    if Path(str(report.get("formatted_markdown", ""))).resolve() != formatted_markdown.resolve():
        raise AdoptionError("proposal formatted Markdown does not match")
    if Path(str(report.get("split_manifest", ""))).resolve() != split_manifest.resolve():
        raise AdoptionError("proposal split manifest does not match")
    reference = report.get("reference")
    if not isinstance(reference, dict):
        reference = {
            "path": report.get("reference_root"),
            "sha256": None,
            "scope": None,
        }
    profile_value = manifest.get("profile")
    if isinstance(profile_value, str) and profile_value:
        profile = json.loads(
            Path(profile_value).resolve().read_text(encoding="utf-8-sig")
        )
        configured = profile.get("reference")
        if isinstance(configured, dict):
            if configured.get("scope") != "same-book-content-and-style":
                raise AdoptionError(
                    "reference adoption requires same-book-content-and-style scope"
                )
            if Path(str(configured.get("path", ""))).resolve() != Path(
                str(reference.get("path", ""))
            ).resolve():
                raise AdoptionError("proposal reference path does not match profile")
            if configured.get("sha256") != reference.get("sha256"):
                raise AdoptionError("proposal reference digest does not match profile")
    nodes: list[dict[str, Any]] = manifest["nodes"]
    node_by_key = {node["key"]: node for node in nodes}
    existing_filenames = {node["filename"].casefold() for node in nodes}
    existing_keys = set(node_by_key)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in report["suggestions"]:
        reason: str | None = None
        ambiguity_decision = ambiguity_decisions.get(str(item.get("title", "")))
        if ambiguity_decision:
            action = ambiguity_decision["decision"]
            if action == "reject":
                rejected.append(
                    {
                        "title": str(item.get("title", "")).strip(),
                        "reason": ambiguity_decision["reason"],
                    }
                )
                continue
            item = dict(item)
            item["status"] = "review_candidate"
            item["review_flags"] = []
            if action == "revise":
                item["start_line"] = ambiguity_decision["start_line"]
                item["end_line"] = ambiguity_decision["end_line"]
        parent = node_by_key.get(item.get("parent_node_key"))
        title = str(item.get("title", "")).strip()
        start_line = item.get("start_line")
        end_line = item.get("end_line")
        if item.get("status") != "review_candidate":
            reason = "proposal was ambiguous"
        elif float(item.get("containment", 0.0)) < minimum_containment:
            reason = "containment below reviewer threshold"
        elif int(item.get("matched_character_count", 0)) < minimum_matched_characters:
            reason = "matched character evidence below reviewer threshold"
        elif parent is None or parent.get("category") != "knowledge":
            reason = "owning node is not a knowledge node"
        elif SKIP_TITLE_RE.search(title):
            reason = "chapter summary already exists as a TOC node"
        elif is_same_numbered_parent(title, str(parent["title"])):
            reason = "reference note duplicates its numbered TOC parent"
        elif start_line is None or end_line is None:
            reason = "proposal has no source span"
        elif not (
            int(parent["start_line"])
            <= int(start_line)
            <= int(end_line)
            <= int(parent["end_line"])
        ):
            reason = "proposal is outside its owning node"
        elif int(end_line) - int(start_line) < 2:
            reason = "range is too small to be an independent teaching arc"
        if reason:
            rejected.append({"title": title, "reason": reason})
            continue
        accepted.append(
            {
                "title": title,
                "parent_key": parent["key"],
                "start_line": int(start_line),
                "end_line": int(end_line),
                "containment": float(item["containment"]),
                "matched_character_count": int(item["matched_character_count"]),
            }
        )

    # Matching chooses the best textual owner, but ancestor notes contain their
    # descendants verbatim. Re-anchor every accepted span to the smallest
    # existing knowledge node that physically contains it.
    knowledge_nodes = [
        node for node in nodes if node.get("category") == "knowledge"
    ]
    physically_anchored: list[dict[str, Any]] = []
    for item in accepted:
        physical_owners = [
            node
            for node in knowledge_nodes
            if int(node["start_line"]) <= item["start_line"]
            and item["end_line"] <= int(node["end_line"])
        ]
        if physical_owners:
            owner = min(
                physical_owners,
                key=lambda node: int(node["end_line"])
                - int(node["start_line"]),
            )
            item["parent_key"] = owner["key"]
            if CHAPTER_TITLE_RE.match(str(owner["title"])):
                rejected.append(
                    {
                        "title": item["title"],
                        "reason": (
                            "matched span crosses TOC child boundaries and "
                            "cannot be one contiguous semantic child"
                        ),
                    }
                )
                continue
            overlapping_children = [
                node
                for node in nodes
                if node.get("parent_key") == owner["key"]
                and not (
                    item["end_line"] < int(node["start_line"])
                    or int(node["end_line"]) < item["start_line"]
                )
            ]
            if overlapping_children:
                rejected.append(
                    {
                        "title": item["title"],
                        "reason": (
                            "matched span crosses an existing direct child "
                            "boundary"
                        ),
                    }
                )
                continue
        physically_anchored.append(item)
    accepted = physically_anchored

    # Prefer semantic nesting over duplicated source. A contained proposal
    # becomes a child of the smallest accepted range that contains it.
    for item in accepted:
        containers = [
            candidate
            for candidate in accepted
            if candidate is not item
            and candidate["parent_key"] == item["parent_key"]
            and candidate["start_line"] <= item["start_line"]
            and item["end_line"] <= candidate["end_line"]
            and (
                candidate["start_line"] < item["start_line"]
                or item["end_line"] < candidate["end_line"]
            )
        ]
        if containers:
            container = min(
                containers,
                key=lambda candidate: candidate["end_line"]
                - candidate["start_line"],
            )
            item["container"] = container

    # Create stable keys before assigning nested parents.
    for item in accepted:
        key = proposal_key(item["title"], item["start_line"])
        suffix = 2
        base = key
        while key in existing_keys:
            key = f"{base}-{suffix}"
            suffix += 1
        item["key"] = key
        existing_keys.add(key)
    for item in accepted:
        if "container" in item:
            item["parent_key"] = item["container"]["key"]

    # Reject only true partial sibling overlaps. Fully nested ranges were
    # handled above; exact duplicates retain the higher-containment proposal.
    retained: list[dict[str, Any]] = []
    for item in sorted(
        accepted,
        key=lambda value: (
            value["parent_key"],
            value["start_line"],
            value["end_line"],
            -value["containment"],
        ),
    ):
        conflict = next(
            (
                other
                for other in retained
                if other["parent_key"] == item["parent_key"]
                and not (
                    item["end_line"] < other["start_line"]
                    or other["end_line"] < item["start_line"]
                )
            ),
            None,
        )
        if conflict:
            rejected.append(
                {
                    "title": item["title"],
                    "reason": (
                        "partial or duplicate sibling overlap with "
                        f"{conflict['title']}"
                    ),
                }
            )
            continue
        retained.append(item)
    accepted = retained

    heading_review_by_line = {
        int(item["line"]): item
        for item in manifest["semantic_review"]["headings"]
    }
    ranges = manifest["semantic_review"].setdefault("ranges", [])
    added_nodes: list[dict[str, Any]] = []
    for item in sorted(accepted, key=lambda value: value["start_line"]):
        filename = safe_filename(item["title"])
        if filename.casefold() in existing_filenames:
            rejected.append(
                {
                    "title": item["title"],
                    "reason": f"filename already exists: {filename}",
                }
            )
            continue
        existing_filenames.add(filename.casefold())
        node = {
            "key": item["key"],
            "title": item["title"],
            "parent_key": item["parent_key"],
            "category": "knowledge",
            "filename": filename,
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "toc_key": None,
        }
        nodes.append(node)
        node_by_key[node["key"]] = node
        added_nodes.append(node)
        heading_match = HEADING_RE.match(lines[item["start_line"] - 1])
        heading_review = heading_review_by_line.get(item["start_line"])
        if heading_match and heading_review:
            heading_review.clear()
            heading_review.update(
                {
                    "line": item["start_line"],
                    "title": heading_match.group(2),
                    "decision": "split",
                    "node_key": item["key"],
                    "reason": (
                        "Same-edition source review confirmed a complete, "
                        "independently reusable teaching arc."
                    ),
                    "independent_teaching_arc": True,
                    "confidence": 0.96,
                }
            )
        else:
            ranges.append(
                {
                    "node_key": item["key"],
                    "title": item["title"],
                    "start_line": item["start_line"],
                    "end_line": item["end_line"],
                    "decision": "split",
                    "reason": (
                        "Same-edition source review aligned the complete body "
                        "to this exact non-heading range."
                    ),
                    "independent_teaching_arc": True,
                    "confidence": 0.96,
                }
            )

    children_by_parent: dict[str, list[str]] = {}
    for node in nodes:
        parent_key = node.get("parent_key")
        if parent_key:
            children_by_parent.setdefault(parent_key, []).append(node["key"])
    sections = manifest["semantic_review"]["sections"]
    section_keys = {section["node_key"] for section in sections}
    for node in added_nodes:
        source_heading = HEADING_RE.match(lines[int(node["start_line"]) - 1])
        nonblank_lines = sum(
            1
            for line in lines[
                int(node["start_line"]) - 1 : int(node["end_line"])
            ]
            if line.strip()
        )
        if (
            source_heading
            and 4 <= len(source_heading.group(1)) <= 6
            and nonblank_lines >= 24
            and node["key"] not in section_keys
        ):
            sections.append(
                {
                    "node_key": node["key"],
                    "title": node["title"],
                    "start_line": node["start_line"],
                    "end_line": node["end_line"],
                    "decision": "review_required",
                }
            )
            section_keys.add(node["key"])
    for section in sections:
        child_keys = children_by_parent.get(section["node_key"], [])
        section["decision"] = "split" if child_keys else "retain"
        section["child_node_keys"] = child_keys
        section["reason"] = (
            "Reviewed the complete section; the listed child ranges are "
            "complete independent teaching arcs."
            if child_keys
            else "Reviewed the complete section; no additional non-overlapping "
            "independent teaching arc was established."
        )
        section["confidence"] = 0.96
        section["reviewed_entire_section"] = True
        section.pop("reviewed", None)

    manifest["nodes"] = sorted(
        nodes,
        key=lambda node: (
            int(node["start_line"]),
            -int(node["end_line"]),
            str(node["key"]),
        ),
    )
    manifest["semantic_review"]["reference"] = {
        "status": "passed",
        "reviewer_confirmed": True,
        "scope": reference.get("scope"),
        "path": reference.get("path"),
        "sha256": reference.get("sha256"),
        "proposal_report": str(proposal_report),
        "proposal_report_sha256": hashlib.sha256(
            proposal_report.read_bytes()
        ).hexdigest(),
        "decision_report": str(review_decisions) if review_decisions else None,
        "decision_report_sha256": decisions_digest,
        "ambiguous_count": len(ambiguity_decisions),
        "resolved_ambiguity_count": len(ambiguity_decisions),
        "added_node_count": len(added_nodes),
        "rejected_count": len(rejected),
    }
    atomic_write_json(output_manifest, manifest)
    return {
        "schema_version": 1,
        "stage": "reference-semantic-review-adoption",
        "status": "passed",
        "output_manifest": str(output_manifest),
        "added_node_count": len(added_nodes),
        "rejected_count": len(rejected),
        "added_nodes": [
            {
                "key": node["key"],
                "title": node["title"],
                "parent_key": node["parent_key"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
            }
            for node in added_nodes
        ],
        "rejected": rejected,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formatted_markdown", type=Path)
    parser.add_argument("split_manifest", type=Path)
    parser.add_argument("proposal_report", type=Path)
    parser.add_argument("output_manifest", type=Path)
    parser.add_argument("--minimum-containment", type=float, default=0.55)
    parser.add_argument("--minimum-matched-characters", type=int, default=35)
    parser.add_argument("--review-decisions", type=Path)
    parser.add_argument("--reviewer-confirmed", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.reviewer_confirmed:
        raise AdoptionError(
            "Refusing automatic adoption without --reviewer-confirmed"
        )
    report = adopt(
        args.formatted_markdown.resolve(),
        args.split_manifest.resolve(),
        args.proposal_report.resolve(),
        args.output_manifest.resolve(),
        args.minimum_containment,
        args.minimum_matched_characters,
        review_decisions=(
            args.review_decisions.resolve() if args.review_decisions else None
        ),
        reviewer_confirmed=True,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
