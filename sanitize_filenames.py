#!/usr/bin/env python3
"""递归清理文件和目录名称，使其适合 GitHub 上的跨平台检出。"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
DEFAULT_EXCLUDES = {".git", ".hg", ".svn"}

# Git 本身只禁止 NUL 和路径分隔符，但 GitHub 仓库通常也要能在 Windows
# 上正常检出，所以这里采用 Windows 文件名不允许的字符集合。
INVALID_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
WINDOWS_RESERVED_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Entry:
    original: Path
    relative: Path
    final_relative: Path
    new_name: str
    is_dir: bool

    @property
    def changed(self) -> bool:
        return self.original.name != self.new_name

    @property
    def depth(self) -> int:
        return len(self.relative.parts)


def sanitize_name(name: str) -> str:
    """返回跨平台安全的单个路径组件，不改动路径分隔结构。"""
    # 同时处理用户特别指出的全角冒号“：”。
    cleaned = name.replace("：", "_")
    cleaned = INVALID_CHARACTERS.sub("_", cleaned)

    # 替换其余 Unicode 控制字符。格式字符（例如零宽连接符）不在此列，
    # 因为它们可能是合法文字或 emoji 的组成部分。
    cleaned = "".join(
        "_" if unicodedata.category(character) == "Cc" else character
        for character in cleaned
    )

    # Windows 不接受末尾的空格或句点；逐个替换可以保持名称长度和可辨识性。
    trailing_count = len(cleaned) - len(cleaned.rstrip(" ."))
    if trailing_count:
        cleaned = cleaned[:-trailing_count] + "_" * trailing_count

    # CON、NUL、COM1 等即使带扩展名也是 Windows 保留设备名。
    if WINDOWS_RESERVED_NAME.fullmatch(cleaned):
        stem, dot, suffix = cleaned.partition(".")
        cleaned = f"{stem}_{dot}{suffix}"

    # scandir 不会返回空名称、'.' 或 '..'，但保留兜底以方便单元调用。
    if cleaned in {"", ".", ".."}:
        cleaned = "_" * max(1, len(cleaned))

    return cleaned


def iter_entries(root: Path, excludes: set[str]) -> Iterable[Entry]:
    """深度优先遍历；不跟随目录符号链接。"""

    def visit(directory: Path) -> Iterable[Entry]:
        try:
            children = list(os.scandir(directory))
        except OSError as error:
            raise RuntimeError(f"无法读取目录 {directory}: {error}") from error

        for child in children:
            path = Path(child.path)
            relative = path.relative_to(root)
            if child.name in excludes and child.is_dir(follow_symlinks=False):
                continue

            is_dir = child.is_dir(follow_symlinks=False)
            if is_dir:
                yield from visit(path)

            final_parts = tuple(sanitize_name(part) for part in relative.parts)
            yield Entry(
                original=path,
                relative=relative,
                final_relative=Path(*final_parts),
                new_name=sanitize_name(child.name),
                is_dir=is_dir,
            )

    yield from visit(root)


def windows_key(path: Path) -> tuple[str, ...]:
    """用于发现 Windows/macOS 上不区分大小写造成的目标冲突。"""
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in path.parts)


def find_collisions(entries: list[Entry]) -> list[list[Entry]]:
    groups: dict[tuple[str, ...], list[Entry]] = {}
    for entry in entries:
        groups.setdefault(windows_key(entry.final_relative), []).append(entry)

    return [
        group
        for group in groups.values()
        if len(group) > 1 and any(entry.changed for entry in group)
    ]


def display_plan(changes: list[Entry], max_display: int) -> None:
    for entry in changes[:max_display]:
        kind = "目录" if entry.is_dir else "文件"
        print(f"[{kind}] {entry.relative}  ->  {entry.final_relative}")

    hidden = len(changes) - max_display
    if hidden > 0:
        print(f"... 另有 {hidden} 项未显示（可用 --max-display 调整）")


def apply_changes(changes: list[Entry]) -> None:
    # 必须从最深处开始，否则父目录改名后，子项的原路径就会失效。
    for entry in sorted(changes, key=lambda item: item.depth, reverse=True):
        destination = entry.original.with_name(entry.new_name)
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(f"目标在扫描后出现，已停止：{destination}")
        entry.original.rename(destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "递归替换文件和目录名中的跨平台非法字符。默认只预览；"
            "添加 --apply 才会真正重命名。"
        )
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"要处理的根目录（默认：{DEFAULT_ROOT}）",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行重命名；不加此参数时只预览",
    )
    parser.add_argument(
        "--max-display",
        type=int,
        default=200,
        metavar="N",
        help="最多显示多少条改名记录（默认：200）",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="NAME",
        help="额外跳过的目录名；可重复使用",
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

    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    try:
        entries = list(iter_entries(root, excludes))
    except RuntimeError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2

    changes = [entry for entry in entries if entry.changed]
    collisions = find_collisions(entries)

    print(f"扫描目录：{root}")
    print(f"扫描项目：{len(entries)}；需要改名：{len(changes)}")
    display_plan(changes, args.max_display)

    if collisions:
        print("\n发现目标名称冲突，未执行任何改名：", file=sys.stderr)
        for group in collisions[:20]:
            sources = " | ".join(str(entry.relative) for entry in group)
            print(f"  {sources}  ->  {group[0].final_relative}", file=sys.stderr)
        if len(collisions) > 20:
            print(f"  ... 另有 {len(collisions) - 20} 组冲突", file=sys.stderr)
        return 3

    if not changes:
        print("无需改名。")
        return 0

    if not args.apply:
        print("\n当前为预览模式；确认无误后添加 --apply 执行。")
        return 0

    try:
        apply_changes(changes)
    except OSError as error:
        print(f"错误：重命名失败：{error}", file=sys.stderr)
        return 4
    except RuntimeError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 4

    print(f"\n完成：已重命名 {len(changes)} 项。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
