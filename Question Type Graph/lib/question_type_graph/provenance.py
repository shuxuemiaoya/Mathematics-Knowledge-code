from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .common import ConfigurationError, load_json, load_profile, sha256_file, write_json_atomic


SOURCE_PART_RE = re.compile(
    r"<!--\s*source-part:(?P<part>\d+)\s+pages:(?P<start>\d+)-(?P<end>\d+)\s*-->"
)


def visible_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(filter(None, (visible_text(item) for item in value)))
    if isinstance(value, dict):
        return " ".join(filter(None, (visible_text(item) for item in value.values())))
    return ""


def normalize_evidence_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value)
    value = re.sub(r"^\s*#{1,6}\s+", "", value)
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", "", value).casefold()


def _part_number(path: Path) -> int:
    match = re.search(r"part-(\d+)", path.as_posix())
    if not match:
        raise ConfigurationError(f"Cannot determine PDF part from provenance path: {path}")
    return int(match.group(1))


def _select_content_lists(artifacts: list[dict[str, Any]]) -> list[Path]:
    grouped: dict[int, list[Path]] = defaultdict(list)
    for item in artifacts:
        path = Path(str(item.get("path", ""))).resolve()
        if not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise ConfigurationError(f"MinerU provenance artifact is missing or changed: {path}")
        grouped[_part_number(path)].append(path)
    selected: list[Path] = []
    for part in sorted(grouped):
        choices = sorted(grouped[part])
        legacy = [path for path in choices if "_v2" not in path.name.casefold()]
        selected.append((legacy or choices)[0])
    return selected


def load_blocks(report: dict[str, Any], role: str) -> list[dict[str, Any]]:
    parts = {int(item["index"]): item for item in report.get("parts", [])}
    blocks: list[dict[str, Any]] = []
    for artifact in _select_content_lists(
        report.get("page_provenance", {}).get("artifacts", [])
    ):
        part = _part_number(artifact)
        part_meta = parts.get(part)
        if not part_meta:
            raise ConfigurationError(f"Conversion report has no metadata for part {part}")
        try:
            payload = json.loads(artifact.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise ConfigurationError(f"Cannot parse MinerU provenance {artifact}: {exc}") from exc
        if not isinstance(payload, list):
            raise ConfigurationError(f"MinerU provenance root must be an array: {artifact}")
        page_blocks: list[tuple[int, dict[str, Any]]] = []
        if payload and isinstance(payload[0], list):
            for page_index, items in enumerate(payload):
                for item in items:
                    if isinstance(item, dict):
                        page_blocks.append((page_index, item))
        else:
            for item in payload:
                if isinstance(item, dict) and isinstance(item.get("page_idx"), int):
                    page_blocks.append((int(item["page_idx"]), item))
        page_ordinals: dict[int, int] = defaultdict(int)
        for page_index, item in page_blocks:
            bbox = item.get("bbox")
            if not (
                isinstance(bbox, list)
                and len(bbox) == 4
                and all(isinstance(value, (int, float)) for value in bbox)
            ):
                continue
            text = str(item.get("text") or visible_text(item.get("content", {}))).strip()
            page_ordinals[page_index] += 1
            source_page = int(part_meta["start_page"]) + page_index
            blocks.append(
                {
                    "block_id": f"{role}:p{source_page}:b{page_ordinals[page_index]}",
                    "role": role,
                    "part": part,
                    "part_page_index": page_index,
                    "source_page": source_page,
                    "type": item.get("type"),
                    "bbox": bbox,
                    "text": text,
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
            )
    return blocks


def map_markdown_lines(markdown: Path, blocks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Map raw lines to page/bbox evidence only when normalized containment is exact."""
    by_part: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    exact_by_part: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for block in blocks:
        if str(block.get("type", "")).casefold() in {
            "header",
            "footer",
            "page_header",
            "page_footer",
            "page_number",
        }:
            continue
        normalized = normalize_evidence_text(str(block.get("text", "")))
        if not normalized:
            continue
        by_part[int(block["part"])].append((normalized, block))
        exact_by_part[int(block["part"])][normalized].append(block)

    result: dict[str, list[dict[str, Any]]] = {}
    current_part = min(by_part, default=1)
    last_page_by_part: dict[int, int] = defaultdict(int)
    for raw_line, line in enumerate(markdown.read_text(encoding="utf-8-sig").splitlines(), 1):
        marker = SOURCE_PART_RE.search(line)
        if marker:
            current_part = int(marker.group("part"))
            continue
        normalized = normalize_evidence_text(line)
        if len(normalized) < 4:
            continue
        candidates = list(exact_by_part[current_part].get(normalized, []))
        method = "normalized-exact"
        if not candidates and len(normalized) >= 12:
            candidates = [
                block
                for block_text, block in by_part[current_part]
                if normalized in block_text or block_text in normalized
            ]
            method = "normalized-containment"
        if not candidates:
            continue
        forward = [
            item
            for item in candidates
            if int(item["source_page"]) >= last_page_by_part[current_part]
        ]
        if not forward:
            continue
        earliest_page = min(int(item["source_page"]) for item in forward)
        candidates = [
            item for item in forward if int(item["source_page"]) == earliest_page
        ]
        last_page_by_part[current_part] = earliest_page
        result[str(raw_line)] = [
            {
                "block_id": item["block_id"],
                "source_page": item["source_page"],
                "bbox": item["bbox"],
                "type": item.get("type"),
                "match": method,
            }
            for item in candidates[:8]
        ]
    return result


def page_layouts(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        by_page[int(block["source_page"])].append(block)
    layouts = []
    for page, items in sorted(by_page.items()):
        content = [
            item
            for item in items
            if item.get("type") not in {
                "header",
                "footer",
                "page_header",
                "page_footer",
                "page_number",
            }
            and str(item.get("text", "")).strip()
        ]
        left_edges = sorted(float(item["bbox"][0]) for item in content)
        left_edge_bands: list[float] = []
        for edge in left_edges:
            if not left_edge_bands or edge - left_edge_bands[-1] >= 60:
                left_edge_bands.append(edge)
        page_left = min((float(item["bbox"][0]) for item in content), default=0.0)
        page_right = max((float(item["bbox"][2]) for item in content), default=0.0)
        page_width = max(page_right - page_left, 1.0)
        midpoint = page_left + page_width / 2
        narrow = [
            item
            for item in content
            if float(item["bbox"][2]) - float(item["bbox"][0]) <= page_width * 0.6
        ]
        left_column = [
            item
            for item in narrow
            if (float(item["bbox"][0]) + float(item["bbox"][2])) / 2 < midpoint
        ]
        right_column = [item for item in narrow if item not in left_column]
        multi_column_risk = len(left_column) >= 2 and len(right_column) >= 2
        layouts.append(
            {
                "source_page": page,
                "block_count": len(content),
                "left_edge_bands": [round(value, 1) for value in left_edge_bands],
                "narrow_left_block_count": len(left_column),
                "narrow_right_block_count": len(right_column),
                "multi_column_risk": multi_column_risk,
            }
        )
    return layouts


def build_provenance_index(profile_path: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    staging = Path(profile["paths"]["staging_root"])
    sources: list[dict[str, Any]] = []
    for source in profile["sources"]:
        if source.get("kind") != "pdf":
            continue
        report_path = staging / f"{source['role']}-conversion-report.json"
        if not report_path.is_file():
            raise ConfigurationError(f"Conversion report is missing: {report_path}")
        report = load_json(report_path)
        blocks = load_blocks(report, str(source["role"]))
        if not blocks:
            raise ConfigurationError(
                f"No usable page/bbox blocks were found for PDF role {source['role']}"
            )
        markdown = Path(source["markdown_path"])
        line_map = map_markdown_lines(markdown, blocks)
        layouts = page_layouts(blocks)
        sources.append(
            {
                "role": source["role"],
                "markdown": str(markdown.resolve()),
                "markdown_sha256": sha256_file(markdown),
                "block_count": len(blocks),
                "mapped_line_count": len(line_map),
                "line_map": line_map,
                "page_layouts": layouts,
                "blocks": blocks,
            }
        )
    return {
        "schema_version": 1,
        "stage": "source-provenance-index",
        "status": "passed",
        "profile": profile["_profile_path"],
        "sources": sources,
    }


def write_provenance_index(profile_path: Path, output: Path) -> dict[str, Any]:
    value = build_provenance_index(profile_path)
    write_json_atomic(output, value, overwrite=output.exists())
    return value
