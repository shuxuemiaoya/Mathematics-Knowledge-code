#!/usr/bin/env python3
"""Adopt an existing MathMap vault into QID and provenance registries.

The default mode is read-only and prints a JSON report.  --write-registry writes
only registry state; it never renames, moves, merges, or edits existing notes.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable

try:
    from mathmap_dedup import extract_stem, normalize_latex
    from mathmap_registry import RegistryStore, atomic_write_json, fingerprint, sha256_text, vault_relative
except ImportError:
    from scripts.mathmap_dedup import extract_stem, normalize_latex
    from scripts.mathmap_registry import RegistryStore, atomic_write_json, fingerprint, sha256_text, vault_relative


EMBED_RE = re.compile(r"!\[\[([^\]|#]+)")
QID_RE = re.compile(r"Q\d+")
ANSWER_RE = re.compile(r"Q\d+A.+")


def markdown_files(directory: Path, recursive: bool = False) -> Iterable[Path]:
    if not directory.is_dir():
        return []
    paths = directory.rglob("*.md") if recursive else directory.glob("*.md")
    return sorted(paths, key=lambda p: p.as_posix())


def embedded_targets(text: str) -> list[str]:
    return [value.strip().removesuffix(".md") for value in EMBED_RE.findall(text)]


def build_mount_index(kp_dir: Path) -> Dict[str, list[str]]:
    mounts: Dict[str, set[str]] = defaultdict(set)
    for path in markdown_files(kp_dir):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        for target in embedded_targets(text):
            if target.startswith("mathmap/习题/") or target.startswith("mathmap/公式结论/"):
                mounts[target].add(path.stem)
    return {key: sorted(value) for key, value in mounts.items()}


def bootstrap(vault_root: Path, write_registry: bool = False) -> Dict[str, Any]:
    vault = vault_root.resolve()
    mathmap = vault / "mathmap"
    if not mathmap.is_dir():
        raise SystemExit(f"mathmap 目录不存在: {mathmap}")

    store = RegistryStore(vault)
    mount_index = build_mount_index(mathmap / "知识点")
    anomalies: Dict[str, list[Any]] = defaultdict(list)
    normalized_groups: Dict[str, list[str]] = defaultdict(list)
    counts: Dict[str, int] = defaultdict(int)

    directories = {
        "questions": mathmap / "习题/questions",
        "answers": mathmap / "习题/answers",
        "题型整理": mathmap / "习题/题型整理",
        "题集": mathmap / "习题/题集",
        "公式合集": mathmap / "公式结论/公式合集",
        "公式整理": mathmap / "公式结论/公式整理",
        "独立公式": mathmap / "公式结论/独立公式",
        "知识点": mathmap / "知识点",
    }

    for node_type, directory in directories.items():
        for path in markdown_files(directory, recursive=node_type == "题型整理"):
            destination = vault_relative(path, vault)
            previous = store.file_record(destination) or {}
            fp = fingerprint(path, previous.get("fingerprint"))
            identity = f"legacy:{destination}"
            target_without_suffix = destination.removesuffix(".md")
            kps = mount_index.get(target_without_suffix, [])
            store.adopt_file(
                destination,
                identity,
                node_type,
                fp["sha256"],
                origin="legacy_bootstrap",
                fingerprint=fp,
                knowledge_points=kps,
            )
            counts[node_type] += 1

            if node_type != "questions":
                continue
            stem = path.stem
            if ANSWER_RE.fullmatch(stem):
                anomalies["answer_shaped_files_in_questions"].append(destination)
                continue
            if not QID_RE.fullmatch(stem):
                anomalies["legacy_question_names"].append(destination)
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError) as exc:
                anomalies["unreadable_questions"].append({"path": destination, "error": str(exc)})
                continue
            norm_hash = sha256_text(normalize_latex(extract_stem(text)))
            normalized_groups[norm_hash].append(stem)
            answers = [target for target in embedded_targets(text) if "/answers/" in target]
            store.register_question(
                stem,
                destination,
                norm_hash,
                fp["sha256"],
                identity,
                answers=answers,
                status="adopted",
            )

    for norm_hash, qids in normalized_groups.items():
        if len(qids) > 1:
            anomalies["duplicate_normalized_stems"].append(
                {"normalized_stem_hash": norm_hash, "qids": sorted(qids)}
            )

    report: Dict[str, Any] = {
        "vault_root": str(vault),
        "mode": "write-registry" if write_registry else "read-only",
        "counts": dict(sorted(counts.items())),
        "anomaly_counts": {key: len(value) for key, value in sorted(anomalies.items())},
        "anomalies": dict(sorted(anomalies.items())),
        "registry_paths": {
            "qid": str(store.qid_path),
            "provenance": str(store.provenance_path),
        },
    }
    if write_registry:
        store.save()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="从既有 MathMap Vault 引导生成 QID 与 provenance 注册表")
    parser.add_argument("vault_root", help="Vault 根目录")
    parser.add_argument("--write-registry", action="store_true", help="写入注册表；不修改任何既有笔记")
    parser.add_argument("--report", help="可选 JSON 报告输出路径")
    args = parser.parse_args()

    report = bootstrap(Path(args.vault_root), write_registry=args.write_registry)
    if args.report:
        atomic_write_json(Path(args.report), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
