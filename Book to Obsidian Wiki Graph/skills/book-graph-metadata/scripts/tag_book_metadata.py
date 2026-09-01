#!/usr/bin/env python3
"""Batch derive, inject, and validate YAML Frontmatter File Properties for Obsidian notes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

SCHEMA_VERSION = 1

NODE_TYPE_MAP = {
    "概念": "概念",
    "知识点": "知识点",
    "拓展知识点": "拓展知识点",
    "非必修知识点": "拓展知识点",
    "思维或方法": "思维或方法",
    "习题": "习题",
    "趣味阅读": "趣味阅读",
    "工具": "工具",
    "目录": "目录",
    "索引": "索引",
    "情景导入": "情景导入",
    "例题": "例题",
}

ARCHITECTURE_NODE_TYPE_MAP = {
    "organizer": "目录",
    "scenario": "情景导入",
    "knowledge": "知识点",
    "worked-example": "例题",
    "practice-question": "习题",
    "section-exercise-question": "习题",
    "concept": "概念",
    "reading": "趣味阅读",
    "history": "趣味阅读",
    "method": "思维或方法",
    "tool": "工具",
}
ORGANIZER_TYPE_MAP = {
    "book": "全书",
    "chapter": "章节",
    "section": "小节",
    "knowledge-theme": "知识主题",
    "practice": "练习",
    "section-exercise": "习题",
}

VALID_NODE_TYPES = set(NODE_TYPE_MAP.values())
VALID_DURATIONS = {"15分钟", "20分钟", "25分钟", "30分钟", "45分钟", "60分钟"}
VALID_DIFFICULTIES = {"简单", "易", "难"}
VALID_IMPORTANCE = {"必须深度理解", "理解", "熟悉即可", "知道就行", "非必学"}
VALID_TIERS = {"D", "C", "B", "A", "A+"}
VALID_GRADES = {"高一", "高二", "高三"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_atomic(path: Path, payload: Any, overwrite: bool = True) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"file already exists: {path}")
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


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Extract existing YAML frontmatter key-values and remaining content."""
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)
    if not match:
        return {}, content

    yaml_block = match.group(1)
    body = match.group(2)
    metadata: dict[str, str] = {}
    for line in yaml_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            metadata[key.strip()] = val.strip()
    return metadata, body


def format_frontmatter(metadata: dict[str, str], body: str) -> str:
    """Serialize frontmatter dictionary and append body content."""
    lines = ["---"]
    for key, val in metadata.items():
        lines.append(f"{key}: {val}")
    lines.append("---")
    lines.append(body if body.startswith("\n") else "\n" + body)
    return "\n".join(lines)


def infer_grade(title: str, edition: str) -> str:
    combined = f"{title} {edition}".casefold()
    if "选择性" in combined or "选修" in combined or "第二册" in combined or "第三册" in combined:
        return "高二"
    if "必修一" in combined or "第一册" in combined or "必修1" in combined:
        return "高一"
    if "高三" in combined:
        return "高三"
    return "高一"


def infer_source(profile: dict[str, Any]) -> str:
    book = profile.get("book", {})
    edition = book.get("edition", "").strip()
    title = book.get("title", "").strip()
    if edition:
        return edition
    return title or "高中数学电子课本"


def infer_node_type(file_path: Path, book_root: Path) -> str:
    rel_path = file_path.relative_to(book_root).as_posix()
    if file_path.name == "index.md" or file_path.name == "目录.md":
        return "目录"
    if "索引" in file_path.name:
        return "索引"

    parts = rel_path.split("/")
    for part in parts[:-1]:
        clean_part = re.sub(r"^\d+[-_]?", "", part)
        if clean_part in NODE_TYPE_MAP:
            return NODE_TYPE_MAP[clean_part]

    stem = file_path.stem
    for key, val in NODE_TYPE_MAP.items():
        if key in stem:
            return val
    return "知识点"


def architecture_metadata_map(
    manifest: dict[str, Any] | None,
    profile: dict[str, Any],
    book_root: Path,
) -> dict[Path, dict[str, str]]:
    if not isinstance(manifest, dict):
        return {}
    categories = {
        str(item["role"]): str(item["directory"])
        for item in profile.get("categories", [])
        if isinstance(item, dict)
        and item.get("enabled", True)
        and isinstance(item.get("role"), str)
        and isinstance(item.get("directory"), str)
    }
    result: dict[Path, dict[str, str]] = {}
    for node in manifest.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_type = node.get("node_type")
        rendered_type = ARCHITECTURE_NODE_TYPE_MAP.get(str(node_type))
        if rendered_type is None:
            continue
        filename = str(node.get("filename") or f"{node.get('title')}.md")
        role = str(node.get("category", "root"))
        path = (
            book_root / filename
            if role == "root"
            else book_root / categories[role] / filename
        ).resolve()
        metadata = {"节点类型": rendered_type}
        if node_type == "organizer":
            organizer_type = ORGANIZER_TYPE_MAP.get(
                str(node.get("organizer_type"))
            )
            if organizer_type:
                metadata["组织类型"] = organizer_type
        result[path] = metadata
    return result


def infer_chapter(file_path: Path, book_root: Path) -> str:
    rel_parts = file_path.relative_to(book_root).parts
    for part in rel_parts:
        clean = re.sub(r"^\d+[-_]?", "", part).replace("_", " ")
        if re.search(r"第[一二三四五六七八九十\d]+章", clean):
            return clean
        if "高考" in clean or "新动向" in clean:
            return clean
    return "全书总览"


def infer_duration(node_type: str, line_count: int) -> str:
    if node_type == "概念":
        return "15分钟"
    if node_type == "趣味阅读":
        return "20分钟"
    if node_type in ("目录", "索引"):
        return "60分钟"
    if node_type == "习题":
        return "60分钟" if line_count > 100 else "45分钟"
    if line_count > 150:
        return "45分钟"
    return "30分钟"


def infer_difficulty(node_type: str, stem: str) -> str:
    if node_type in ("概念", "趣味阅读", "目录", "索引"):
        return "简单"
    if any(k in stem for k in ("综合", "导数", "圆锥曲线", "立体几何", "空间向量")):
        return "难"
    return "易"


def infer_importance(node_type: str, stem: str) -> str:
    if node_type == "趣味阅读":
        return "知道就行"
    if node_type == "拓展知识点":
        return "非必学"
    if any(k in stem for k in ("定义", "定理", "公式", "性质", "导数", "向量", "方程")):
        return "必须深度理解"
    return "理解"


def infer_tier(difficulty: str, importance: str) -> str:
    if difficulty == "难" and importance == "必须深度理解":
        return "A+"
    if difficulty == "难" or importance == "必须深度理解":
        return "A"
    if difficulty == "易" and importance == "理解":
        return "B"
    if difficulty == "简单":
        return "D"
    return "C"


def derive_metadata_for_file(
    file_path: Path,
    book_root: Path,
    profile: dict[str, Any],
    override_source: str | None = None,
    override_grade: str | None = None,
    architecture_metadata: dict[str, str] | None = None,
) -> dict[str, str]:
    content = file_path.read_text(encoding="utf-8")
    existing, body = parse_frontmatter(content)
    line_count = len(body.splitlines())

    book_title = profile.get("book", {}).get("title", "")
    book_edition = profile.get("book", {}).get("edition", "")

    source = override_source or existing.get("来源") or infer_source(profile)
    grade = override_grade or existing.get("年级") or infer_grade(book_title, book_edition)
    architecture_metadata = architecture_metadata or {}
    node_type = (
        architecture_metadata.get("节点类型")
        or existing.get("节点类型")
        or infer_node_type(file_path, book_root)
    )
    chapter = existing.get("章节") or infer_chapter(file_path, book_root)
    duration = existing.get("时长") or infer_duration(node_type, line_count)
    difficulty = existing.get("难度") or infer_difficulty(node_type, file_path.stem)
    importance = existing.get("重要程度") or infer_importance(node_type, file_path.stem)
    tier = existing.get("推荐层级") or infer_tier(difficulty, importance)

    metadata = dict(existing)
    metadata["来源"] = source
    metadata["年级"] = grade
    metadata["节点类型"] = node_type
    if "组织类型" in architecture_metadata:
        metadata["组织类型"] = architecture_metadata["组织类型"]
    elif node_type != "目录":
        metadata.pop("组织类型", None)
    metadata["章节"] = chapter
    metadata["时长"] = duration
    metadata["难度"] = difficulty
    metadata["重要程度"] = importance
    metadata["推荐层级"] = tier
    return metadata


def validate_file_metadata(metadata: dict[str, str]) -> list[str]:
    errors: list[str] = []
    required_keys = ["来源", "年级", "节点类型", "章节", "时长", "难度", "重要程度", "推荐层级"]
    for key in required_keys:
        if key not in metadata or not metadata[key].strip():
            errors.append(f"missing metadata field: {key}")

    if "节点类型" in metadata and metadata["节点类型"] not in VALID_NODE_TYPES:
        errors.append(f"invalid 节点类型: {metadata['节点类型']}")
    if metadata.get("节点类型") == "目录" and not metadata.get("组织类型", "").strip():
        errors.append("目录节点缺少组织类型")
    if "时长" in metadata and metadata["时长"] not in VALID_DURATIONS:
        errors.append(f"invalid 时长: {metadata['时长']}")
    if "难度" in metadata and metadata["难度"] not in VALID_DIFFICULTIES:
        errors.append(f"invalid 难度: {metadata['难度']}")
    if "重要程度" in metadata and metadata["重要程度"] not in VALID_IMPORTANCE:
        errors.append(f"invalid 重要程度: {metadata['重要程度']}")
    if "推荐层级" in metadata and metadata["推荐层级"] not in VALID_TIERS:
        errors.append(f"invalid 推荐层级: {metadata['推荐层级']}")
    if "年级" in metadata and metadata["年级"] not in VALID_GRADES:
        errors.append(f"invalid 年级: {metadata['年级']}")
    return errors


def process_book_metadata(
    book_root: Path,
    profile_path: Path,
    output_report_path: Path,
    override_source: str | None = None,
    override_grade: str | None = None,
    overwrite: bool = True,
    split_manifest_path: Path | None = None,
) -> dict[str, Any]:
    book_root = book_root.resolve()
    profile_path = profile_path.resolve()
    profile = read_json(profile_path)
    source_sha256 = profile.get("source", {}).get("sha256", "")
    if split_manifest_path is None:
        candidate = Path(profile.get("paths", {}).get("staging_root", "")) / "split-manifest.json"
        split_manifest_path = candidate if candidate.is_file() else None
    split_manifest = (
        read_json(split_manifest_path.resolve())
        if split_manifest_path is not None and split_manifest_path.is_file()
        else None
    )
    architecture_by_path = architecture_metadata_map(
        split_manifest, profile, book_root
    )

    md_files = sorted(f for f in book_root.rglob("*.md") if f.is_file())
    tagged_count = 0
    errors: list[str] = []
    categories_summary: dict[str, int] = {}

    for file_path in md_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            existing_meta, body = parse_frontmatter(content)
            metadata = derive_metadata_for_file(
                file_path,
                book_root,
                profile,
                override_source=override_source,
                override_grade=override_grade,
                architecture_metadata=architecture_by_path.get(file_path.resolve()),
            )
            file_errors = validate_file_metadata(metadata)
            if file_errors:
                rel = file_path.relative_to(book_root).as_posix()
                for err in file_errors:
                    errors.append(f"{rel}: {err}")
                continue

            node_type = metadata["节点类型"]
            categories_summary[node_type] = categories_summary.get(node_type, 0) + 1

            new_content = format_frontmatter(metadata, body)
            if new_content != content:
                file_path.write_text(new_content, encoding="utf-8")
            tagged_count += 1
        except Exception as exc:
            rel = file_path.relative_to(book_root).as_posix()
            errors.append(f"{rel}: failed to process ({type(exc).__name__}: {exc})")

    status = "passed" if not errors else "failed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": "metadata-tagging",
        "status": status,
        "profile": str(profile_path),
        "source_sha256": source_sha256,
        "total_files": len(md_files),
        "tagged_files": tagged_count,
        "categories_summary": categories_summary,
        "split_manifest": (
            str(split_manifest_path.resolve()) if split_manifest_path else None
        ),
        "errors": errors,
    }

    write_json_atomic(output_report_path, report, overwrite=overwrite)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_root", type=Path, help="Directory containing book Markdown notes")
    parser.add_argument("--profile", type=Path, required=True, help="Path to book-profile.json")
    parser.add_argument("--output", type=Path, required=True, help="Path to metadata-report.json output")
    parser.add_argument("--override-source", help="Optional override for 来源 metadata field")
    parser.add_argument("--override-grade", help="Optional override for 年级 metadata field")
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--no-overwrite", action="store_false", dest="overwrite")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = process_book_metadata(
            args.book_root,
            args.profile,
            args.output,
            override_source=args.override_source,
            override_grade=args.override_grade,
            overwrite=args.overwrite,
            split_manifest_path=args.split_manifest,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "passed" else 1
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
