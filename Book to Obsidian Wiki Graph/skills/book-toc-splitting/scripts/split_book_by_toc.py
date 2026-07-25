#!/usr/bin/env python3
"""Split formatted book Markdown with a reviewed TOC-based split manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_IMAGE_RE = re.compile(r"""<img\b[^>]*\bsrc=["']([^"']+)["']""", re.I)
EXTERNAL_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*]')
CONTENT_HEADING_RE = re.compile(r"^(#{4,6})\s+(.+?)\s*$")
NUMBERED_SUBSECTION_RE = re.compile(r"^\d+(?:\.\d+){2,}\s+\S")
SECTION_EXERCISE_RE = re.compile(r"^习题\s*\d+(?:\.\d+)+(?:\s|$)")


class SplitError(ValueError):
    pass


@dataclass(frozen=True)
class SplitNode:
    key: str
    title: str
    parent_key: str | None
    category: str
    filename: str
    start_line: int
    end_line: int
    toc_key: str | None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_filename(filename: str) -> str:
    cleaned = INVALID_FILENAME_RE.sub("_", filename).strip().rstrip(".")
    if not cleaned:
        raise SplitError("Split filename cannot be empty")
    if not cleaned.lower().endswith(".md"):
        cleaned += ".md"
    return cleaned


def category_map(profile: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in profile.get("categories", []):
        if not isinstance(item, dict) or not item.get("enabled", True):
            continue
        role = item.get("role")
        directory = item.get("directory")
        if isinstance(role, str) and role and isinstance(directory, str) and directory:
            result[role] = directory
    return result


def load_nodes(
    manifest: dict[str, Any],
    profile: dict[str, Any],
    line_count: int,
    toc_keys: set[str],
) -> tuple[dict[str, SplitNode], SplitNode]:
    raw_nodes = manifest.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise SplitError("Split manifest needs a non-empty nodes array")
    categories = category_map(profile)
    book_kind = str(profile.get("book", {}).get("kind", "")).casefold()
    allowed = set(categories)
    if "textbook" in book_kind:
        allowed &= {"knowledge", "concept", "exercise"}
        if set(categories) - {"knowledge", "concept", "exercise"}:
            raise SplitError(
                "Textbook profiles may enable only knowledge, concept, and exercise"
            )

    nodes: dict[str, SplitNode] = {}
    target_keys: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise SplitError(f"Split node {index} must be an object")
        key = raw.get("key")
        title = raw.get("title")
        parent_key = raw.get("parent_key")
        category = raw.get("category")
        start = raw.get("start_line")
        end = raw.get("end_line")
        toc_key = raw.get("toc_key")
        if not isinstance(key, str) or not key:
            raise SplitError(f"Split node {index} needs a key")
        if key in nodes:
            raise SplitError(f"Duplicate split key: {key}")
        if not isinstance(title, str) or not title.strip():
            raise SplitError(f"Split node {key!r} needs a title")
        if parent_key is not None and not isinstance(parent_key, str):
            raise SplitError(f"Split node {key!r} parent_key must be a string")
        if category != "root" and category not in allowed:
            raise SplitError(
                f"Split node {key!r} uses disabled or unsupported category {category!r}"
            )
        if not isinstance(start, int) or not isinstance(end, int):
            raise SplitError(f"Split node {key!r} needs integer line bounds")
        if start < 1 or end < start or end > line_count:
            raise SplitError(f"Split node {key!r} has invalid line bounds")
        filename = clean_filename(str(raw.get("filename") or f"{title}.md"))
        target_key = (str(category), filename.casefold())
        if target_key in target_keys:
            raise SplitError(f"Duplicate split target: {category}/{filename}")
        target_keys.add(target_key)
        if toc_key is not None and toc_key not in toc_keys:
            raise SplitError(f"Split node {key!r} has unknown toc_key {toc_key!r}")
        nodes[key] = SplitNode(
            key=key,
            title=title.strip(),
            parent_key=parent_key,
            category=str(category),
            filename=filename,
            start_line=start,
            end_line=end,
            toc_key=toc_key,
        )

    roots = [node for node in nodes.values() if node.parent_key is None]
    if len(roots) != 1 or roots[0].category != "root":
        raise SplitError("Split manifest needs exactly one root-category node")
    root = roots[0]

    children: dict[str, list[SplitNode]] = {key: [] for key in nodes}
    for node in nodes.values():
        if node.parent_key is None:
            continue
        parent = nodes.get(node.parent_key)
        if parent is None:
            raise SplitError(f"Split node {node.key!r} has a missing parent")
        if node.start_line < parent.start_line or node.end_line > parent.end_line:
            raise SplitError(f"Split node {node.key!r} lies outside its parent")
        if (
            node.start_line == parent.start_line
            and node.end_line == parent.end_line
            and parent.category != "root"
        ):
            raise SplitError(f"Split node {node.key!r} duplicates its parent range")
        children[parent.key].append(node)

    for parent_key, siblings in children.items():
        ordered = sorted(siblings, key=lambda item: (item.start_line, item.end_line))
        for previous, current in zip(ordered, ordered[1:]):
            if current.start_line <= previous.end_line:
                raise SplitError(
                    f"Sibling ranges overlap under {parent_key!r}: "
                    f"{previous.key!r} and {current.key!r}"
                )

    used_toc_keys = [node.toc_key for node in nodes.values() if node.toc_key]
    if len(used_toc_keys) != len(set(used_toc_keys)):
        raise SplitError("A TOC key is assigned to more than one split node")
    missing_toc = sorted(toc_keys - set(used_toc_keys))
    if missing_toc:
        raise SplitError("Split manifest omits TOC keys: " + ", ".join(missing_toc))
    return nodes, root


def target_path(
    node: SplitNode,
    output_root: Path,
    categories: dict[str, str],
) -> Path:
    if node.category == "root":
        return output_root / node.filename
    return output_root / categories[node.category] / node.filename


def encode_path(path: str, encode_spaces: bool) -> str:
    normalized = path.replace("\\", "/")
    return normalized.replace(" ", "%20") if encode_spaces else normalized


def note_link(
    child: SplitNode,
    parent: SplitNode,
    output_root: Path,
    vault_root: Path,
    categories: dict[str, str],
    links: dict[str, Any],
) -> str:
    child_target = target_path(child, output_root, categories)
    parent_target = target_path(parent, output_root, categories)
    if links.get("note_mode") == "vault-root":
        try:
            href = child_target.relative_to(vault_root).as_posix()
        except ValueError as exc:
            raise SplitError("Split target lies outside the configured vault") from exc
    else:
        href = os.path.relpath(child_target, parent_target.parent).replace("\\", "/")
    href = encode_path(href, bool(links.get("encode_spaces", False)))
    return f"[{child.title}]({href})"


def line_exclusions(toc_manifest: dict[str, Any]) -> set[int]:
    excluded: set[int] = set()
    for item in toc_manifest.get("toc_source_ranges", []):
        if isinstance(item, dict):
            start = item.get("start_line")
            end = item.get("end_line")
            if isinstance(start, int) and isinstance(end, int):
                excluded.update(range(start, end + 1))
    return excluded


def validate_semantic_review(
    manifest: dict[str, Any],
    nodes: dict[str, SplitNode],
    lines: list[str],
    excluded: set[int],
    profile: dict[str, Any],
) -> None:
    """Require an explicit disposition for every demoted content heading.

    TOC formatting deliberately pushes all non-TOC headings below H3.  A
    heading-only split can therefore satisfy TOC coverage while still leaving
    an entire lesson, its numbered subsections, and its section exercise in one
    oversized note.  The review ledger makes the semantic-boundary decision
    auditable and lets the splitter enforce textbook boundaries that are not
    optional.
    """

    book_kind = str(profile.get("book", {}).get("kind", "")).casefold()
    if "textbook" not in book_kind:
        return

    candidates: dict[int, str] = {}
    for line_number, line in enumerate(lines, start=1):
        if line_number in excluded:
            continue
        match = CONTENT_HEADING_RE.match(line)
        if match:
            candidates[line_number] = match.group(2).strip()

    review = manifest.get("semantic_review")
    raw_headings = review.get("headings") if isinstance(review, dict) else None
    if not isinstance(raw_headings, list):
        raise SplitError(
            "Textbook split manifest needs semantic_review.headings for every H4-H6 content heading"
        )

    reviewed: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(raw_headings):
        if not isinstance(item, dict):
            raise SplitError(f"semantic_review heading {index} must be an object")
        line_number = item.get("line")
        title = item.get("title")
        decision = item.get("decision")
        if not isinstance(line_number, int) or line_number not in candidates:
            raise SplitError(
                f"semantic_review heading {index} references no H4-H6 content heading"
            )
        if line_number in reviewed:
            raise SplitError(
                f"semantic_review duplicates heading at line {line_number}"
            )
        if title != candidates[line_number]:
            raise SplitError(
                f"semantic_review title mismatch at line {line_number}: "
                f"expected {candidates[line_number]!r}"
            )
        if decision not in {"split", "retain"}:
            raise SplitError(
                f"semantic_review heading at line {line_number} needs decision split or retain"
            )
        reviewed[line_number] = item

    missing = sorted(set(candidates) - set(reviewed))
    if missing:
        samples = ", ".join(
            f"{line}:{candidates[line]}" for line in missing[:12]
        )
        raise SplitError(
            f"semantic_review omits {len(missing)} H4-H6 content headings: {samples}"
        )

    for line_number, title in candidates.items():
        item = reviewed[line_number]
        decision = item["decision"]
        must_split_category: str | None = None
        if SECTION_EXERCISE_RE.match(title):
            must_split_category = "exercise"
        elif NUMBERED_SUBSECTION_RE.match(title):
            must_split_category = "knowledge"

        if must_split_category and decision != "split":
            raise SplitError(
                f"Textbook heading {title!r} at line {line_number} must be split as {must_split_category}"
            )

        if decision == "retain":
            if not str(item.get("reason", "")).strip():
                raise SplitError(
                    f"Retained semantic heading {title!r} at line {line_number} needs a reason"
                )
            continue

        node_key = item.get("node_key")
        node = nodes.get(node_key) if isinstance(node_key, str) else None
        if node is None:
            raise SplitError(
                f"Split semantic heading {title!r} at line {line_number} needs a valid node_key"
            )
        if node.start_line != line_number:
            raise SplitError(
                f"Semantic node {node.key!r} must start at reviewed heading line {line_number}"
            )
        if must_split_category and node.category != must_split_category:
            raise SplitError(
                f"Semantic node {node.key!r} must use category {must_split_category!r}"
            )


def render_node(
    node: SplitNode,
    nodes: dict[str, SplitNode],
    lines: list[str],
    excluded: set[int],
    output_root: Path,
    vault_root: Path,
    categories: dict[str, str],
    links: dict[str, Any],
    book_title: str,
) -> str:
    children = sorted(
        (item for item in nodes.values() if item.parent_key == node.key),
        key=lambda item: item.start_line,
    )
    rendered: list[str] = []
    cursor = node.start_line
    for child in children:
        for line_number in range(cursor, child.start_line):
            if line_number not in excluded:
                rendered.append(lines[line_number - 1])
        rendered.append(
            note_link(
                child,
                node,
                output_root,
                vault_root,
                categories,
                links,
            )
        )
        cursor = child.end_line + 1
    for line_number in range(cursor, node.end_line + 1):
        if line_number not in excluded:
            rendered.append(lines[line_number - 1])

    text = "\n".join(rendered).strip()
    if node.category == "root":
        expected = f"# {book_title}".strip()
        if not text.startswith(expected):
            text = expected + ("\n\n" + text if text else "")
    return text + "\n"


def local_asset_hrefs(markdown: str) -> list[str]:
    return MARKDOWN_IMAGE_RE.findall(markdown) + HTML_IMAGE_RE.findall(markdown)


def materialize_assets(
    markdown: str,
    source_parent: Path,
    target_parent: Path,
    final_parent: Path,
    vault_root: Path,
    links: dict[str, Any],
) -> tuple[str, int]:
    copied = 0
    replacements: dict[str, str] = {}
    for href in dict.fromkeys(local_asset_hrefs(markdown)):
        raw = href.strip().strip("<>")
        if EXTERNAL_RE.match(raw) or raw.startswith(("/", "\\", "#")):
            continue
        path_text = urllib.parse.unquote(raw.split("#", 1)[0].split("?", 1)[0])
        relative = Path(path_text.replace("/", os.sep))
        if relative.is_absolute() or ".." in relative.parts:
            continue
        source = (source_parent / relative).resolve()
        if not source.is_file():
            raise SplitError(f"Referenced source asset is missing: {source}")
        destination = (target_parent / relative).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
            copied += 1
        if links.get("asset_mode") == "vault-root":
            final_destination = (final_parent / relative).resolve()
            try:
                vault_relative = final_destination.relative_to(vault_root).as_posix()
            except ValueError as exc:
                raise SplitError(
                    "Split asset target lies outside the configured vault"
                ) from exc
            replacements[href] = "/" + encode_path(
                vault_relative, bool(links.get("encode_spaces", False))
            )

    if replacements:
        markdown = MARKDOWN_IMAGE_RE.sub(
            lambda match: match.group(0).replace(
                match.group(1), replacements.get(match.group(1), match.group(1))
            ),
            markdown,
        )
        markdown = HTML_IMAGE_RE.sub(
            lambda match: match.group(0).replace(
                match.group(1), replacements.get(match.group(1), match.group(1))
            ),
            markdown,
        )
    return markdown, copied


def write_split(
    source: Path,
    profile: dict[str, Any],
    toc_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    markdown = source.read_text(encoding="utf-8-sig")
    lines = markdown.splitlines()
    toc_keys = {
        str(item["key"])
        for item in toc_manifest.get("entries", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }
    nodes, root = load_nodes(split_manifest, profile, len(lines), toc_keys)
    categories = category_map(profile)
    vault_root = Path(profile["paths"]["vault_root"]).resolve()
    links = profile.get("links", {})
    excluded = line_exclusions(toc_manifest)
    validate_semantic_review(
        split_manifest, nodes, lines, excluded, profile
    )
    book_title = str(profile.get("book", {}).get("title", root.title))

    if output_root.exists():
        raise FileExistsError(
            f"Output root already exists; choose a new target or resume explicitly: {output_root}"
        )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.split-", dir=output_root.parent)
    )
    note_count = 0
    asset_count = 0
    coverage_units: list[dict[str, Any]] = []
    try:
        ordered_nodes = sorted(
            nodes.values(), key=lambda item: (item.start_line, item.end_line, item.key)
        )
        for order, node in enumerate(ordered_nodes, start=1):
            rendered = render_node(
                node,
                nodes,
                lines,
                excluded,
                output_root,
                vault_root,
                categories,
                links,
                book_title,
            )
            destination = target_path(node, temporary, categories)
            destination.parent.mkdir(parents=True, exist_ok=True)
            final_target = target_path(node, output_root, categories)
            rendered, copied = materialize_assets(
                rendered,
                source.parent,
                destination.parent,
                final_target.parent,
                vault_root,
                links,
            )
            destination.write_text(rendered, encoding="utf-8")
            asset_count += copied
            note_count += 1
            coverage_units.append(
                {
                    "source_key": node.key,
                    "source_order": order,
                    "role": node.category,
                    "target": final_target.relative_to(output_root).as_posix(),
                    "status": "assigned",
                    "line_range": [node.start_line, node.end_line],
                }
            )
        shutil.move(str(temporary), str(output_root))
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    coverage = {
        "schema_version": 1,
        "profile": split_manifest.get("profile"),
        "source_sha256": split_manifest.get("source_sha256"),
        "units": coverage_units,
    }
    staging_root = Path(profile["paths"]["staging_root"]).resolve()
    staging_root.mkdir(parents=True, exist_ok=True)
    coverage_path = staging_root / "coverage-manifest.json"
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "notes": note_count,
        "assets_copied": asset_count,
        "categories": categories,
        "coverage_manifest": str(coverage_path),
        "root_note": str(target_path(root, output_root, categories)),
    }


def validate_identity(
    profile_path: Path,
    profile: dict[str, Any],
    toc_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    source: Path,
) -> None:
    for name, artifact in (
        ("TOC manifest", toc_manifest),
        ("split manifest", split_manifest),
    ):
        raw_profile = artifact.get("profile")
        if not isinstance(raw_profile, str) or Path(raw_profile).resolve() != profile_path:
            raise SplitError(f"{name} profile does not match --profile")
        if artifact.get("source_sha256") != profile.get("source", {}).get("sha256"):
            raise SplitError(f"{name} source_sha256 does not match profile")
    candidate_hash = toc_manifest.get("candidate_markdown_sha256")
    if candidate_hash and candidate_hash != sha256_file(source):
        raise SplitError("Formatted Markdown hash does not match TOC manifest")
    expected_split_hash = split_manifest.get("input_markdown_sha256")
    if expected_split_hash != sha256_file(source):
        raise SplitError("Formatted Markdown hash does not match split manifest")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formatted_markdown", type=Path)
    parser.add_argument("toc_manifest", type=Path)
    parser.add_argument("split_manifest", type=Path)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = args.formatted_markdown.resolve()
        profile_path = args.profile.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Formatted Markdown does not exist: {source}")
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        toc_manifest = json.loads(
            args.toc_manifest.read_text(encoding="utf-8-sig")
        )
        split_manifest = json.loads(
            args.split_manifest.read_text(encoding="utf-8-sig")
        )
        validate_identity(
            profile_path, profile, toc_manifest, split_manifest, source
        )
        output_root = (
            args.output_root.resolve()
            if args.output_root
            else Path(profile["paths"]["book_root"]).resolve()
        )
        summary = write_split(
            source, profile, toc_manifest, split_manifest, output_root
        )
        result = {
            "schema_version": 1,
            "stage": "book-toc-splitting",
            "status": "completed",
            "profile": str(profile_path),
            "source_sha256": profile["source"]["sha256"],
            "input_markdown": str(source),
            "output_root": str(output_root),
            **summary,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "book-toc-splitting",
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
