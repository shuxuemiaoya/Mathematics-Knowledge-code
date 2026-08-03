#!/usr/bin/env python3
"""Compare a candidate Canvas with its frozen same-series style reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)")
WIKILINK = re.compile(r"\[\[[^\]]+\]\]")


class StyleComparisonError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise StyleComparisonError(f"cannot read JSON {path}: {exc}") from exc


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def number(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def contains_center(group: dict[str, Any], node: dict[str, Any]) -> bool:
    center_x = number(node.get("x")) + number(node.get("width")) / 2
    center_y = number(node.get("y")) + number(node.get("height")) / 2
    left = number(group.get("x"))
    top = number(group.get("y"))
    return (
        left <= center_x <= left + number(group.get("width"))
        and top <= center_y <= top + number(group.get("height"))
    )


def ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def rounded(value: float) -> float:
    return round(value, 4)


def canvas_metrics(canvas: Any) -> dict[str, Any]:
    if not isinstance(canvas, dict):
        raise StyleComparisonError("Canvas root must be an object")
    nodes = canvas.get("nodes")
    edges = canvas.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise StyleComparisonError("Canvas must contain nodes and edges arrays")
    if any(not isinstance(node, dict) for node in nodes):
        raise StyleComparisonError("Canvas nodes must be objects")
    if any(not isinstance(edge, dict) for edge in edges):
        raise StyleComparisonError("Canvas edges must be objects")

    groups = [node for node in nodes if node.get("type") == "group"]
    text_nodes = [node for node in nodes if node.get("type") == "text"]
    bounds_nodes = [
        node
        for node in nodes
        if all(
            isinstance(node.get(field), (int, float))
            and not isinstance(node.get(field), bool)
            for field in ("x", "y", "width", "height")
        )
    ]
    if bounds_nodes:
        min_x = min(number(node["x"]) for node in bounds_nodes)
        min_y = min(number(node["y"]) for node in bounds_nodes)
        max_x = max(
            number(node["x"]) + number(node["width"])
            for node in bounds_nodes
        )
        max_y = max(
            number(node["y"]) + number(node["height"])
            for node in bounds_nodes
        )
        span_x = max_x - min_x
        span_y = max_y - min_y
    else:
        span_x = span_y = 0.0

    depths = [
        sum(contains_center(group, node) for group in groups)
        for node in text_nodes
    ]
    heights = [number(node.get("height")) for node in text_nodes]
    positive_heights = [height for height in heights if height > 0]
    mean_height = statistics.fmean(positive_heights) if positive_heights else 0.0
    height_cv = (
        statistics.pstdev(positive_heights) / mean_height
        if len(positive_heights) > 1 and mean_height
        else 0.0
    )
    linked = 0
    wiki_linked = 0
    markdown_linked = 0
    for node in text_nodes:
        text = str(node.get("text", ""))
        has_markdown = bool(MARKDOWN_LINK.search(text))
        has_wiki = bool(WIKILINK.search(text))
        markdown_linked += has_markdown
        wiki_linked += has_wiki
        linked += has_markdown or has_wiki

    return {
        "nodes": len(nodes),
        "text_nodes": len(text_nodes),
        "groups": len(groups),
        "edges": len(edges),
        "group_per_text": rounded(ratio(len(groups), len(text_nodes))),
        "cards_per_group": rounded(ratio(len(text_nodes), len(groups))),
        "max_text_group_depth": max(depths, default=0),
        "nested_text_ratio": rounded(
            ratio(sum(depth >= 3 for depth in depths), len(depths))
        ),
        "canvas_aspect_y_over_x": rounded(ratio(span_y, span_x)),
        "labeled_edge_ratio": rounded(
            ratio(sum(bool(str(edge.get("label", "")).strip()) for edge in edges), len(edges))
        ),
        "colored_edge_ratio": rounded(
            ratio(sum("color" in edge for edge in edges), len(edges))
        ),
        "colored_text_ratio": rounded(
            ratio(sum("color" in node for node in text_nodes), len(text_nodes))
        ),
        "annotation_card_ratio": rounded(ratio(len(text_nodes) - linked, len(text_nodes))),
        "card_height_cv": rounded(height_cv),
        "markdown_link_ratio": rounded(ratio(markdown_linked, len(text_nodes))),
        "wikilink_ratio": rounded(ratio(wiki_linked, len(text_nodes))),
    }


def relative_factor(candidate: float, reference: float) -> float:
    if reference == 0:
        return math.inf if candidate else 1.0
    return candidate / reference


def compare_metrics(reference: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []

    def block(code: str, message: str, metric: str, tolerance: str) -> None:
        differences.append(
            {
                "code": code,
                "message": message,
                "metric": metric,
                "reference": reference[metric],
                "candidate": candidate[metric],
                "tolerance": tolerance,
            }
        )

    if abs(candidate["max_text_group_depth"] - reference["max_text_group_depth"]) > 1:
        block(
            "group-depth",
            "The group nesting depth differs by more than one level.",
            "max_text_group_depth",
            "absolute difference <= 1",
        )
    if reference["groups"] >= 4:
        factor = relative_factor(candidate["group_per_text"], reference["group_per_text"])
        if not 0.55 <= factor <= 1.8:
            block(
                "group-density",
                "The candidate uses a materially different group density.",
                "group_per_text",
                "reference factor 0.55..1.80",
            )
        factor = relative_factor(candidate["cards_per_group"], reference["cards_per_group"])
        if not 0.45 <= factor <= 2.2:
            block(
                "cards-per-group",
                "The candidate clusters a materially different number of cards per group.",
                "cards_per_group",
                "reference factor 0.45..2.20",
            )
    if reference["canvas_aspect_y_over_x"] > 0:
        factor = relative_factor(
            candidate["canvas_aspect_y_over_x"],
            reference["canvas_aspect_y_over_x"],
        )
        if not 1 / 3 <= factor <= 3:
            block(
                "canvas-aspect",
                "The overall horizontal/vertical layout proportion is too different.",
                "canvas_aspect_y_over_x",
                "reference factor 0.333..3.000",
            )
    for metric, code, label, tolerance in (
        ("labeled_edge_ratio", "edge-labeling", "edge-label usage", 0.25),
        ("colored_edge_ratio", "edge-coloring", "edge-color usage", 0.35),
        ("colored_text_ratio", "card-coloring", "card-color usage", 0.30),
    ):
        if abs(candidate[metric] - reference[metric]) > tolerance:
            block(
                code,
                f"The {label} differs beyond the style tolerance.",
                metric,
                f"absolute difference <= {tolerance:.2f}",
            )
    if reference["nested_text_ratio"] >= 0.10 and candidate["nested_text_ratio"] < 0.05:
        block(
            "nested-clusters",
            "The reference uses nested clusters but the candidate largely flattens them.",
            "nested_text_ratio",
            "candidate >= 0.05 when reference >= 0.10",
        )
    if reference["annotation_card_ratio"] >= 0.05 and candidate["annotation_card_ratio"] < 0.02:
        block(
            "annotation-cards",
            "The reference uses explanatory cards but the candidate omits them.",
            "annotation_card_ratio",
            "candidate >= 0.02 when reference >= 0.05",
        )
    if reference["card_height_cv"] >= 0.25 and candidate["card_height_cv"] < 0.10:
        block(
            "card-height-rhythm",
            "The reference varies card height but the candidate uses a uniform grid.",
            "card_height_cv",
            "candidate >= 0.10 when reference >= 0.25",
        )
    return differences


def compare_canvas_styles(
    profile_path: Path,
    candidate_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    profile_path = profile_path.resolve()
    candidate_path = candidate_path.resolve()
    profile = read_json(profile_path)
    if not isinstance(profile, dict):
        raise StyleComparisonError("profile must be an object")
    configured = profile.get("canvas", {}).get("style_reference")
    if not isinstance(configured, dict):
        raise StyleComparisonError(
            "profile.canvas.style_reference is required for style comparison"
        )
    if configured.get("scope") != "same-series-style":
        raise StyleComparisonError(
            "profile.canvas.style_reference.scope must be same-series-style"
        )
    reference_path = Path(str(configured.get("path", ""))).resolve()
    if not reference_path.is_file():
        raise StyleComparisonError(f"reference Canvas is missing: {reference_path}")
    if not candidate_path.is_file():
        raise StyleComparisonError(f"candidate Canvas is missing: {candidate_path}")
    reference_sha256 = sha256_file(reference_path)
    if reference_sha256 != configured.get("sha256"):
        raise StyleComparisonError(
            "reference Canvas SHA-256 does not match the frozen profile"
        )
    source_sha256 = profile.get("source", {}).get("sha256")
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise StyleComparisonError("profile.source.sha256 is invalid")

    reference_metrics = canvas_metrics(read_json(reference_path))
    candidate_metrics = canvas_metrics(read_json(candidate_path))
    blocking = compare_metrics(reference_metrics, candidate_metrics)
    payload = {
        "schema_version": 1,
        "stage": "canvas-style-parity",
        "status": "passed" if not blocking else "style_review_required",
        "profile": str(profile_path),
        "source_sha256": source_sha256,
        "reference": {
            "path": str(reference_path),
            "sha256": reference_sha256,
        },
        "candidate": {
            "path": str(candidate_path),
            "sha256": sha256_file(candidate_path),
        },
        "metrics": {
            "reference": reference_metrics,
            "candidate": candidate_metrics,
        },
        "blocking_differences": blocking,
        "ignored_contract_differences": [
            {
                "code": "raw-counts",
                "reason": "Different volumes may contain different numbers of notes and relations.",
            },
            {
                "code": "legacy-link-syntax",
                "reason": (
                    "The candidate must keep canonical Markdown links even when "
                    "the visual reference contains legacy Wikilinks or plain cards."
                ),
            },
            {
                "code": "semantic-content",
                "reason": "A style reference never authorizes copying another volume's content.",
            },
        ],
    }
    if output_path is not None:
        write_json_atomic(output_path.resolve(), payload)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("candidate_canvas", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = compare_canvas_styles(
            args.profile, args.candidate_canvas, args.output
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["status"] == "passed" else 2
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
