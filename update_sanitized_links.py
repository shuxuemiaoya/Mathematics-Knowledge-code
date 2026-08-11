#!/usr/bin/env python3
"""更新因文件名清理而失效的 Markdown/Obsidian 本地链接。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sanitize_filenames import DEFAULT_ROOT, sanitize_name


WIKILINK = re.compile(r"(!?\[\[)([^\]\n]+)(\]\])")
QUOTED_ABSOLUTE_PATH = re.compile(
    r"(?P<quote>['\"])(?P<path>/Users/oven/Documents/ovenmathmap/[^'\"\n]+)(?P=quote)"
)
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def sanitize_path(path_text: str) -> str:
    """清理路径的每个组件，但保留绝对路径和相对路径结构。"""
    parts = path_text.split("/")
    cleaned = [
        part if part in {"", ".", ".."} else sanitize_name(part)
        for part in parts
    ]
    return "/".join(cleaned)


def target_exists(candidate: str, source: Path, root: Path) -> bool:
    """同时支持 vault 根路径、绝对路径和普通相对路径。"""
    candidate_path = Path(candidate)
    possible_paths: list[Path]
    if candidate_path.is_absolute():
        possible_paths = [candidate_path]
    else:
        possible_paths = [root / candidate_path, source.parent / candidate_path]

    for path in possible_paths:
        if path.exists() or (not path.suffix and path.with_suffix(".md").exists()):
            return True
    return False


def update_target(
    raw_target: str,
    source: Path,
    root: Path,
    unresolved: list[tuple[Path, str, str]],
) -> str:
    """更新一个链接目标；目标不存在时保持原样。"""
    leading = raw_target[: len(raw_target) - len(raw_target.lstrip())]
    trailing = raw_target[len(raw_target.rstrip()) :]
    target = raw_target.strip()
    if not target or target.startswith("#") or URI_SCHEME.match(target):
        return raw_target

    path_part, marker, fragment = target.partition("#")
    sanitized = sanitize_path(path_part)
    if sanitized == path_part:
        return raw_target

    if not target_exists(sanitized, source, root):
        unresolved.append((source, path_part, sanitized))
        return raw_target

    updated = sanitized + (marker + fragment if marker else "")
    return leading + updated + trailing


def update_content(
    content: str,
    source: Path,
    root: Path,
    unresolved: list[tuple[Path, str, str]],
) -> tuple[str, int]:
    replacements = 0

    def replace_wikilink(match: re.Match[str]) -> str:
        nonlocal replacements
        payload = match.group(2)
        target, separator, display = payload.partition("|")
        updated_target = update_target(target, source, root, unresolved)
        if updated_target != target:
            replacements += 1
        updated_payload = updated_target + (separator + display if separator else "")
        return match.group(1) + updated_payload + match.group(3)

    content = WIKILINK.sub(replace_wikilink, content)

    def replace_absolute(match: re.Match[str]) -> str:
        nonlocal replacements
        old_path = match.group("path")
        new_path = update_target(old_path, source, root, unresolved)
        if new_path != old_path:
            replacements += 1
        quote = match.group("quote")
        return quote + new_path + quote

    content = QUOTED_ABSOLUTE_PATH.sub(replace_absolute, content)
    return content, replacements


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "更新 Markdown/Obsidian 链接中因非法字符改名而变化的路径。"
            "默认只预览；添加 --apply 才会写入。"
        )
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Markdown 根目录（默认：{DEFAULT_ROOT}）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入修改；不加时只预览",
    )
    parser.add_argument(
        "--max-display",
        type=int,
        default=50,
        metavar="N",
        help="最多显示多少个修改文件（默认：50）",
    )
    args = parser.parse_args()
    if args.max_display < 0:
        parser.error("--max-display 不能小于 0")
    return args


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"错误：目录不存在或不是目录：{root}", file=sys.stderr)
        return 2

    changed: list[tuple[Path, str, int]] = []
    unresolved: list[tuple[Path, str, str]] = []
    scanned = 0

    for source in root.rglob("*.md"):
        if ".git" in source.parts:
            continue
        scanned += 1
        try:
            original = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"错误：无法读取 {source}: {error}", file=sys.stderr)
            return 2
        updated, replacements = update_content(original, source, root, unresolved)
        if replacements:
            changed.append((source, updated, replacements))

    total_replacements = sum(item[2] for item in changed)
    print(f"扫描 Markdown：{scanned}")
    print(f"需要修改：{len(changed)} 个文件，{total_replacements} 处路径")
    for source, _, replacements in changed[: args.max_display]:
        print(f"[{replacements:>3} 处] {source.relative_to(root)}")
    if len(changed) > args.max_display:
        print(f"... 另有 {len(changed) - args.max_display} 个文件未显示")

    if unresolved:
        unique_unresolved = list(dict.fromkeys(unresolved))
        print(f"未修改的无对应目标路径：{len(unique_unresolved)}", file=sys.stderr)
        for source, old, candidate in unique_unresolved[:20]:
            print(
                f"  {source.relative_to(root)}: {old} -> {candidate}",
                file=sys.stderr,
            )

    if not args.apply:
        print("当前为预览模式；确认后添加 --apply 写入。")
        return 0

    for source, updated, _ in changed:
        source.write_text(updated, encoding="utf-8")
    print(f"完成：已更新 {len(changed)} 个文件中的 {total_replacements} 处路径。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
