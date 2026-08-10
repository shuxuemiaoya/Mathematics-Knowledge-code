#!/usr/bin/env python3
"""Stream a full or plan-scoped MathMap topology audit."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable

try:
    from mathmap_registry import atomic_write_json
except ImportError:
    from scripts.mathmap_registry import atomic_write_json


EMBED_RE = re.compile(r"!\[\[([^\]|#]+)")
RULES = {
    "questions": ("mathmap/习题/answers/",),
    "题型整理": ("mathmap/习题/questions/", "mathmap/习题/题型整理/"),
    "题集": ("mathmap/习题/题型整理/",),
    "公式合集": ("mathmap/公式结论/公式整理/",),
    "公式整理": ("mathmap/公式结论/独立公式/",),
    "独立公式": ("mathmap/公式结论/", "mathmap/习题/题型整理/"),
}


def classify(relative: str) -> str | None:
    prefixes = {
        "mathmap/习题/questions/": "questions",
        "mathmap/习题/题型整理/": "题型整理",
        "mathmap/习题/题集/": "题集",
        "mathmap/公式结论/公式合集/": "公式合集",
        "mathmap/公式结论/公式整理/": "公式整理",
        "mathmap/公式结论/独立公式/": "独立公式",
    }
    for prefix, node_type in prefixes.items():
        if relative.startswith(prefix):
            return node_type
    return None


def full_paths(vault: Path) -> Iterable[str]:
    for prefix, recursive in (
        ("mathmap/习题/questions", False),
        ("mathmap/习题/题型整理", True),
        ("mathmap/习题/题集", False),
        ("mathmap/公式结论/公式合集", False),
        ("mathmap/公式结论/公式整理", False),
        ("mathmap/公式结论/独立公式", False),
    ):
        directory = vault / prefix
        if directory.is_dir():
            paths = directory.rglob("*.md") if recursive else directory.glob("*.md")
            for path in sorted(paths, key=lambda item: item.as_posix()):
                yield path.relative_to(vault).as_posix()


def plan_paths(plan_path: Path) -> Iterable[str]:
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    for item in plan.get("changes", []):
        destination = item.get("destination")
        if isinstance(destination, str):
            yield destination


def audit(vault: Path, paths: Iterable[str]) -> Dict[str, Any]:
    issues: list[Dict[str, str]] = []
    counts: Counter[str] = Counter()
    for relative in sorted(set(paths)):
        node_type = classify(relative)
        if not node_type:
            continue
        path = vault / relative
        if not path.is_file():
            issues.append({"kind": "missing_changed_file", "path": relative})
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            issues.append({"kind": "unreadable", "path": relative, "detail": str(exc)})
            continue
        counts[f"files:{node_type}"] += 1
        for raw_target in EMBED_RE.findall(text):
            target = raw_target.strip().removesuffix(".md")
            counts["embeds"] += 1
            if target.startswith("mathmap/") and not target.startswith(RULES[node_type]):
                issues.append({"kind": "wrong_tier", "path": relative, "target": target})
            if target.startswith("mathmap/") and not (vault / f"{target}.md").is_file():
                issues.append({"kind": "broken_target", "path": relative, "target": target})
    return {
        "vault_root": str(vault),
        "counts": dict(sorted(counts.items())),
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MathMap 全量或变更子图拓扑审计")
    parser.add_argument("vault_root")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--full", action="store_true", help="流式审计全部 MathMap 节点")
    scope.add_argument("--plan", help="只审计 link_to_mathmap --plan-out 中列出的文件")
    parser.add_argument("--out", help="JSON 输出路径")
    parser.add_argument("--fail-on-errors", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault_root).resolve()
    paths = full_paths(vault) if args.full else plan_paths(Path(args.plan))
    report = audit(vault, paths)
    if args.out:
        atomic_write_json(Path(args.out), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_errors and report["issue_count"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
