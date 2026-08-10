#!/usr/bin/env python3
"""MathMap baseline-aware planner, linker, and changed-subgraph auditor.

用法：
    python3 link_to_mathmap.py <vault_root> <source_book_dir> <book_short_name> --dry-run
    python3 link_to_mathmap.py <vault_root> <source_book_dir> <book_short_name> --apply

示例：
    python3 link_to_mathmap.py /Users/oven/Documents/ovenmathmap \
        "/Users/oven/Documents/ovenmathmap/课堂同步/教辅/必刷题/2026版 必刷题 数学选择性必修第一册RJA" \
        选择性必修第一册RJA

Default execution is read-only.  Apply mode protects manual Obsidian edits with
bootstrapped content baselines, backs up changed files, rewrites only current-run
assets, and rejects tier or broken-link errors in the changed subgraph.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

# 导入多层级语义去重与合并引擎
try:
    from mathmap_dedup import MathMapDedupEngine, normalize_latex, extract_stem
except ImportError:
    from scripts.mathmap_dedup import MathMapDedupEngine, normalize_latex, extract_stem

try:
    from mathmap_registry import (
        UNLINKED_QUESTION_TYPES_DIR,
        RegistryStore,
        atomic_write_json,
        sha256_bytes,
        sha256_text,
        source_identity,
        vault_relative,
    )
except ImportError:
    from scripts.mathmap_registry import (
        UNLINKED_QUESTION_TYPES_DIR,
        RegistryStore,
        atomic_write_json,
        sha256_bytes,
        sha256_text,
        source_identity,
        vault_relative,
    )



def clean_title(name: str) -> str:
    """去掉 _bN 后缀，用于链接显示名。"""
    return re.sub(r"_b\d+$", "", name)


def link_target_stem(link_path: str) -> str:
    """从 ![[...]] 链接中提取目标文件名（去 .md 后缀）。"""
    fname = os.path.basename(link_path)
    return os.path.splitext(fname)[0]


def is_qt_tier2_name(fname: str) -> bool:
    """Tier 2 判定：题型/考法/易错点/微专题笔记。"""
    if re.search(
        r"(刷基础|刷易错|刷提升|刷难关|刷素养|刷能力|刷速度|刷真题|刷原创|刷综合|基础|易错|提升|难关|素养|能力)_b\d+\.md$",
        fname,
    ):
        return True
    if re.match(r"^(题型|考点|易错点|微专题|习题)", fname):
        return True
    return False


def is_paper_tier3(rel_dir_parts, fname: str) -> bool:
    """Tier 3 判定：框架/总集/套卷笔记。"""
    parts = rel_dir_parts
    if "复习参考题" in fname:
        return True
    if len(parts) >= 2 and fname == parts[1] + ".md":
        return True
    if len(parts) >= 2 and fname.startswith("专题") and fname.endswith(".md"):
        return True
    if len(parts) >= 2 and ("综合训练" in fname or "检测" in fname or "强化" in fname) and fname.endswith(".md") and not re.search(r"_b\d+\.md$", fname):
        return True
    if re.search(r"(刷真题|刷原创|刷综合|刷速度)_b\d+\.md$", fname) and any(
        kw in "/".join(parts) for kw in ["检测", "强化", "综合训练", "高考新动向", "强基", "月考", "期中", "期末"]
    ):
        return True
    return False


def is_formula_note(fname: str) -> bool:
    """判定是否为公式/结论/知识导学笔记。"""
    return bool(re.search(r"(知识导学|知识梳理|公式|结论|考点精讲|知识精讲|考点清单|独立公式)", fname))


def classify_formula_tier(fname: str) -> str:
    """分类公式/结论笔记的层级: 公式合集 | 公式整理 | 独立公式。"""
    if "公式合集" in fname or re.search(r"^(第一章|第二章|第三章|第四章|第五章|第六章|第七章|第八章|第九章|第\d+章|第\d+节|小节|章末).*公式", fname):
        return "公式合集"
    if "公式整理" in fname or re.search(r"(知识导学|知识梳理|考点精讲|知识精讲|考点清单)", fname):
        return "公式整理"
    return "独立公式"


def rewrite_links(content: str, name_map: dict, tier_map: dict) -> str:
    """按「源全路径 -> mathmap 目标」重写笔记内 ![[...]] 链接。

    name_map: 源文件全路径(书目录名开头,含.md) -> mathmap 目标 stem
    tier_map: 源文件全路径 -> "questions"|"answers"|"题型整理"|"题集"|"公式合集"|"公式整理"|"独立公式"
    优先全路径精确匹配；Q 单题按 basename 兜底；未知链接原样保留。
    """

    def repl(match):
        link_path = match.group(1).strip()
        anchor = match.group(2) or ""
        alias = match.group(3)
        norm = link_path.lstrip("./")
        if norm in name_map:
            target = name_map[norm]
            tier = tier_map.get(norm, "题型整理")
            display = alias[1:] if alias else clean_title(Path(target).name)
            if tier in ("公式合集", "公式整理", "独立公式"):
                return f"![[mathmap/公式结论/{tier}/{target}{anchor}|{display}]]"
            return f"![[mathmap/习题/{tier}/{target}{anchor}|{display}]]"
        stem = link_target_stem(link_path)
        if re.match(r"^Q\d+$", stem):
            display = alias[1:] if alias else stem
            return f"![[mathmap/习题/questions/{stem}{anchor}|{display}]]"
        if re.match(r"^Q\d+A.+$", stem):
            display = alias[1:] if alias else stem
            return f"![[mathmap/习题/answers/{stem}{anchor}|{display}]]"
        return match.group(0)

    return re.sub(r"!\[\[([^\]|#]+)(#[^\]|]*)?(\|[^\]]*)?\]\]", repl, content)


# ================= 知识点挂载 =================

def build_kp_index(kp_dir: Path) -> dict:
    """知识点节点名 -> 规范名（去空白），用于匹配。"""
    return {re.sub(r"[\s·:：,，。.．~～+＋]", "", p.stem): p.stem for p in kp_dir.glob("*.md")}


def kp_for_section(
    section: str,
    kp_index: dict,
    kp_dir: Path,
    section_map: dict,
    chapter_map: dict,
    allow_create: bool = False,
):
    """小节目录名/章目录名 -> 知识点节点名。

    匹配逻辑：
      1. 手工精确映射
      2. 细分知识点分离：若原旧节点为多概念组合节点（含 _ 或 与/及），而新目录为拆分后的精细单概念，
         创建并指向全新的独立知识点节点。
      3. 精确匹配 -> 子串匹配。
    """
    if section in section_map:
        target = section_map[section]
        return target if (kp_dir / f"{target}.md").is_file() else None
    if section in chapter_map:
        target = chapter_map[section]
        return target if (kp_dir / f"{target}.md").is_file() else None

    s = re.sub(r"^\d+(\.\d+)*_", "", section)
    norm_s = re.sub(r"[\s·:：,，。.．~～+＋]", "", s)

    # 检查是否为精细切分小节
    if norm_s in kp_index:
        matched_name = kp_index[norm_s]
        # 精细拆分节点只有显式授权时才创建；默认进入人工映射队列。
        if allow_create and ("_" in matched_name or "及" in matched_name or "与" in matched_name) and ("_" not in s and "及" not in s and "与" not in s):
            new_kp_name = s.strip()
            kp_index[re.sub(r"[\s·:：,，。.．~～+＋]", "", new_kp_name)] = new_kp_name
            return new_kp_name
        return matched_name

    for stem, norm_k in kp_index.items():
        if len(norm_k) >= 3 and (norm_k in norm_s or norm_s in norm_k):
            return stem

    # 无法匹配时默认不创建节点；显式 --allow-create-knowledge-points 才允许。
    clean_section_name = s.strip()
    if allow_create and clean_section_name:
        kp_index[re.sub(r"[\s·:：,，。.．~～+＋]", "", clean_section_name)] = clean_section_name
        return clean_section_name

    return None


def render_kp_mount(text: str, tier: str, stem: str, book_short: str) -> tuple[str, bool]:
    """Return a heading-bounded, append-only knowledge-point mount edit.

    - 题型节点 -> # 题型
    - 公式/结论节点 -> # 公式与结论
    """
    if tier in ("公式合集", "公式整理", "独立公式"):
        embed = f"![[mathmap/公式结论/{tier}/{stem}|{clean_title(stem)}]]"
        heading_target = "# 公式与结论"
    else:
        embed = f"![[mathmap/习题/{tier}/{stem}|{clean_title(stem)}]]"
        heading_target = "# 题型"

    if embed in text:
        return text, False
    source_heading = f"## 来源：{book_short}"

    heading_match = re.search(rf"(?m)^{re.escape(heading_target)}\s*$", text)
    if not heading_match:
        text = text.rstrip() + f"\n\n{heading_target}\n"
        heading_match = re.search(rf"(?m)^{re.escape(heading_target)}\s*$", text)
    assert heading_match is not None
    section_start = heading_match.end()
    next_h1 = re.search(r"(?m)^# (?!#)", text[section_start:])
    section_end = section_start + next_h1.start() if next_h1 else len(text)
    section_text = text[section_start:section_end]
    source_match = re.search(rf"(?m)^{re.escape(source_heading)}\s*$", section_text)
    if source_match:
        group_start = section_start + source_match.end()
        next_h2 = re.search(r"(?m)^## ", text[group_start:section_end])
        insert_at = group_start + next_h2.start() if next_h2 else section_end
        text = text[:insert_at].rstrip() + f"\n{embed}\n\n" + text[insert_at:].lstrip("\n")
    else:
        insertion = f"\n{source_heading}\n{embed}\n"
        text = text[:section_start] + insertion + text[section_start:].lstrip("\n")
    return text, True


def mount_kp(kp: str, tier: str, stem: str, kp_dir: Path, book_short: str) -> bool:
    """Compatibility wrapper for callers outside the planner."""
    kp_path = kp_dir / f"{kp}.md"
    if not kp_path.is_file():
        return False
    current = kp_path.read_text(encoding="utf-8-sig")
    updated, changed = render_kp_mount(current, tier, stem, book_short)
    if changed:
        kp_path.write_text(updated, encoding="utf-8")
    return changed



# ================= 主流程 =================

EMBED_RE = re.compile(r"!\[\[([^\]|#]+)")
FORMULA_TIERS = ("公式合集", "公式整理", "独立公式")


@dataclass(frozen=True)
class SourceAsset:
    path: Path
    relative: str
    identity: str
    virtual_path: str
    node_type: str
    section: str
    naming_section: str
    content: str


@dataclass
class PlannedChange:
    destination: str
    content: bytes
    node_type: str
    source_identity: str
    source_hash: Optional[str]
    reason: str
    source_identities: list[str] = field(default_factory=list)


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_component(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" ._")
    return value or "source"


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class LinkPlan:
    """A non-mutating virtual file overlay plus a scoped apply journal."""

    def __init__(self, vault: Path, store: RegistryStore, book_short: str):
        self.vault = vault.resolve()
        self.store = store
        self.book_short = book_short
        self.run_id = _run_id()
        self.changes: Dict[str, PlannedChange] = {}
        self.conflicts: list[Dict[str, Any]] = []
        self.warnings: list[Dict[str, Any]] = []
        self.audit_errors: list[Dict[str, Any]] = []
        self.unchanged: set[str] = set()
        self.source_mappings: Dict[str, str] = {}
        self.adoptions: Dict[str, Dict[str, Any]] = {}
        self.question_registrations: list[Dict[str, Any]] = []
        self.reserved: set[str] = set()
        self.required_directories: set[str] = set()

    def absolute(self, destination: str) -> Path:
        path = (self.vault / destination).resolve()
        try:
            path.relative_to(self.vault)
        except ValueError as exc:
            raise ValueError(f"目标路径越出 Vault: {destination}") from exc
        return path

    def virtual_bytes(self, destination: str) -> Optional[bytes]:
        change = self.changes.get(destination)
        if change:
            return change.content
        path = self.absolute(destination)
        return path.read_bytes() if path.is_file() else None

    def virtual_text(self, destination: str, default: str = "") -> str:
        value = self.virtual_bytes(destination)
        return value.decode("utf-8-sig") if value is not None else default

    def register_mapping(self, identity: str, destination: str) -> None:
        self.source_mappings[identity] = destination

    def ensure_directory(self, destination: str) -> None:
        self.absolute(destination)
        self.required_directories.add(destination.rstrip("/"))

    def add_conflict(self, destination: str, reason: str, identity: str, proposed: Optional[bytes] = None) -> None:
        item: Dict[str, Any] = {
            "destination": destination,
            "reason": reason,
            "source_identity": identity,
        }
        if proposed is not None:
            item["proposed_sha256"] = sha256_bytes(proposed)
            item["_proposed"] = proposed
        self.conflicts.append(item)

    def propose(
        self,
        destination: str,
        content: bytes,
        node_type: str,
        identity: str,
        source_hash: Optional[str],
        reason: str,
    ) -> bool:
        self.register_mapping(identity, destination)
        existing_change = self.changes.get(destination)
        if existing_change:
            existing_change.content = content
            existing_change.reason = reason
            if identity not in existing_change.source_identities:
                existing_change.source_identities.append(identity)
            return True

        current = self.virtual_bytes(destination)
        if current == content:
            self.unchanged.add(destination)
            self.adoptions.setdefault(
                destination,
                {
                    "identity": identity,
                    "node_type": node_type,
                    "source_hash": source_hash,
                    "destination_hash": sha256_bytes(content),
                },
            )
            return False

        current_hash = sha256_bytes(current) if current is not None else None
        baseline = self.store.baseline_state(destination, current_hash)
        if current is not None and baseline in ("unknown", "manually_modified"):
            reason_text = "未引导的既有文件" if baseline == "unknown" else "检测到基线后的人工修改"
            self.add_conflict(destination, reason_text, identity, content)
            return False

        self.changes[destination] = PlannedChange(
            destination=destination,
            content=content,
            node_type=node_type,
            source_identity=identity,
            source_hash=source_hash,
            reason=reason,
            source_identities=[identity],
        )
        return True

    def choose_destination(
        self,
        directory: Path,
        base_name: str,
        section: str,
        identity: str,
        proposed_content: Optional[bytes] = None,
    ) -> str:
        mapped = self.store.destination_for_source(identity)
        directory_rel = vault_relative(directory, self.vault)
        if mapped:
            if mapped == directory_rel or mapped.startswith(directory_rel.rstrip("/") + "/"):
                self.reserved.add(mapped)
                return mapped
            self.add_conflict(mapped, "注册表目标层级与当前节点类型不一致", identity)

        safe_base = Path(base_name).name
        stem, suffix = os.path.splitext(safe_base)
        candidates = [
            safe_base,
            f"{_safe_component(section)}_{safe_base}",
            f"{_safe_component(self.book_short)}_{safe_base}",
        ]
        candidate_index = 0
        suffix_counter = 2
        while True:
            if candidate_index < len(candidates):
                candidate = candidates[candidate_index]
            else:
                candidate = f"{_safe_component(self.book_short)}_{suffix_counter}_{stem}{suffix}"
                suffix_counter += 1
            destination = f"{directory_rel}/{candidate}"
            current = self.virtual_bytes(destination)
            if destination not in self.reserved:
                if current is None or (proposed_content is not None and current == proposed_content):
                    self.reserved.add(destination)
                    return destination
                record = self.store.file_record(destination)
                if record and record.get("source_identity") == identity:
                    self.reserved.add(destination)
                    return destination
            candidate_index += 1

    def audit(self) -> None:
        planned = set(self.changes)
        allowed = {
            "questions": ("mathmap/习题/answers/",),
            "题型整理": ("mathmap/习题/questions/", "mathmap/习题/题型整理/"),
            "题集": ("mathmap/习题/题型整理/",),
            "公式合集": ("mathmap/公式结论/公式整理/",),
            "公式整理": ("mathmap/公式结论/独立公式/",),
            "独立公式": ("mathmap/公式结论/", "mathmap/习题/题型整理/"),
        }
        self.audit_errors = []
        for destination, change in sorted(self.changes.items()):
            prefixes = allowed.get(change.node_type)
            if not prefixes:
                continue
            text = change.content.decode("utf-8-sig")
            for target in EMBED_RE.findall(text):
                target = target.strip().removesuffix(".md")
                if target.startswith("mathmap/") and not target.startswith(prefixes):
                    self.audit_errors.append(
                        {"destination": destination, "kind": "wrong_tier", "target": target}
                    )
                if target.startswith("mathmap/"):
                    target_file = f"{target}.md"
                    if target_file not in planned and not self.absolute(target_file).is_file():
                        self.audit_errors.append(
                            {"destination": destination, "kind": "broken_target", "target": target}
                        )

    def report(self, mode: str) -> Dict[str, Any]:
        action_counts = Counter("create" if not self.absolute(path).exists() else "update" for path in self.changes)
        directory_changes = [
            path for path in sorted(self.required_directories) if not self.absolute(path).is_dir()
        ]
        public_conflicts = [{key: value for key, value in item.items() if not key.startswith("_")} for item in self.conflicts]
        return {
            "run_id": self.run_id,
            "mode": mode,
            "bootstrapped": self.store.bootstrapped,
            "summary": {
                "create": action_counts["create"],
                "update": action_counts["update"],
                "unchanged": len(self.unchanged),
                "conflicts": len(self.conflicts),
                "warnings": len(self.warnings),
                "audit_errors": len(self.audit_errors),
                "create_directories": len(directory_changes),
                "unlinked_question_types": sum(
                    warning.get("kind") == "knowledge_point_review"
                    and warning.get("node_type") == "题型整理"
                    for warning in self.warnings
                ),
            },
            "directories": [
                {
                    "destination": path,
                    "action": "unchanged" if self.absolute(path).is_dir() else "create",
                }
                for path in sorted(self.required_directories)
            ],
            "changes": [
                {
                    "destination": path,
                    "action": "create" if not self.absolute(path).exists() else "update",
                    "node_type": change.node_type,
                    "reason": change.reason,
                    "source_identity": change.source_identity,
                    "proposed_sha256": sha256_bytes(change.content),
                }
                for path, change in sorted(self.changes.items())
            ],
            "conflicts": public_conflicts,
            "warnings": self.warnings,
            "audit_errors": self.audit_errors,
        }

    def apply(self, allow_audit_errors: bool = False, backup: bool = True) -> Path:
        if self.conflicts:
            review_dir = self.store.state_dir / "review" / self.run_id
            review_dir.mkdir(parents=True, exist_ok=True)
            public = []
            for index, item in enumerate(self.conflicts, 1):
                clean = {key: value for key, value in item.items() if not key.startswith("_")}
                public.append(clean)
                proposed = item.get("_proposed")
                if proposed is not None:
                    proposal_path = review_dir / f"{index:04d}-{Path(item['destination']).name}.proposed"
                    proposal_path.write_bytes(proposed)
            atomic_write_json(review_dir / "conflicts.json", {"run_id": self.run_id, "conflicts": public})
            raise RuntimeError(f"存在 {len(self.conflicts)} 个冲突；原文件未移动，建议稿位于 {review_dir}")
        if self.audit_errors and not allow_audit_errors:
            raise RuntimeError(f"变更子图审计失败，共 {len(self.audit_errors)} 项；使用 dry-run 报告检查")

        for destination in sorted(self.required_directories):
            self.absolute(destination).mkdir(parents=True, exist_ok=True)

        backup_dir = self.store.state_dir / "backups" / self.run_id
        if backup:
            for destination in sorted(self.changes):
                source = self.absolute(destination)
                if source.is_file():
                    target = backup_dir / destination
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)

        for destination, change in sorted(self.changes.items()):
            _atomic_write_bytes(self.absolute(destination), change.content)
            self.store.adopt_file(
                destination,
                change.source_identity,
                change.node_type,
                sha256_bytes(change.content),
                source_hash=change.source_hash,
                book_short=self.book_short,
                origin="linker",
            )
        for destination, adoption in self.adoptions.items():
            if not self.store.file_record(destination):
                self.store.adopt_file(
                    destination,
                    adoption["identity"],
                    adoption["node_type"],
                    adoption["destination_hash"],
                    source_hash=adoption["source_hash"],
                    book_short=self.book_short,
                    origin="linker_adopted_identical",
                )
        for identity, destination in self.source_mappings.items():
            self.store.provenance["sources"][identity] = {"destination": destination}
        for registration in self.question_registrations:
            destination = registration["destination"]
            path = self.absolute(destination)
            if path.is_file():
                self.store.register_question(
                    registration["qid"],
                    destination,
                    registration["normalized_stem_hash"],
                    sha256_bytes(path.read_bytes()),
                    registration["origin"],
                    answers=registration.get("answers"),
                    status="linked",
                )
        self.store.save()
        return backup_dir


def _section_from_parts(parts: Iterable[str], fallback: str) -> str:
    part_list = list(parts)
    for part in reversed(part_list):
        if re.match(r"^(\d+(\.\d+)*|课时|专题|专练|第[0-9一二三四五六七八九十]+[节章]|第\d|模块)", part):
            return part
    return part_list[-1] if part_list else fallback


def _generated_formula_assets(
    source_book: Path,
    source_path: Path,
    source_relative: str,
    book_short: str,
    parts: tuple[str, ...],
    content: str,
) -> list[SourceAsset]:
    """Extract formula hierarchy into virtual assets without writing during planning."""
    if not any(marker in content for marker in ("## 知识导学", "## 知识梳理", "## 考点精讲")):
        return []
    guide_match = re.search(
        r"(##\s*(?:知识导学|知识梳理|考点精讲).*?)(?=\n#\s|\n##\s*(?:重点题型|刷题|习题|考点分类|例题)|$)",
        content,
        flags=re.DOTALL,
    )
    if not guide_match:
        return []
    guide_text = guide_match.group(1)
    section_match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    section_title = section_match.group(1).strip() if section_match else source_path.stem
    section_clean = re.sub(r"^第[0-9一二三四五六七八九十]+[节章]\s*", "", section_title).strip()
    section = _section_from_parts(parts, source_book.name)
    naming_section = parts[-1] if parts else "章节"
    namespace = hashlib.sha1(source_relative.encode("utf-8")).hexdigest()[:12]
    generated: list[SourceAsset] = []

    def make_asset(title: str, tier: str, body: str) -> SourceAsset:
        safe_title = _safe_component(title)
        relative = f".generated-formulas/{namespace}/{tier}/{safe_title}.md"
        virtual = f"{source_book.name}/{relative}"
        return SourceAsset(
            path=source_book / relative,
            relative=relative,
            identity=f"generated-formula:{book_short}:{source_relative}:{tier}:{title}",
            virtual_path=virtual,
            node_type=tier,
            section=section,
            naming_section=naming_section,
            content=body,
        )

    level2_assets: list[SourceAsset] = []
    level2_blocks = re.split(r"\n(?=##\s+[一二三四五六七八九十]+\.\s*)", guide_text)
    for block in level2_blocks:
        level2_match = re.match(r"##\s+[一二三四五六七八九十]+\.\s*([^\n]+)", block)
        if not level2_match:
            continue
        level2_title = level2_match.group(1).strip()
        atomic_assets: list[SourceAsset] = []
        for atomic_block in re.split(r"\n(?=##\s+\d+[\.．、\s]\s*)", block):
            atomic_match = re.match(r"##\s+\d+[\.．、\s]\s*([^\n]+)", atomic_block)
            if not atomic_match:
                continue
            raw_title = atomic_match.group(1).strip()
            atomic_title = re.sub(
                r"^[0-9一二三四五六七八九十①②③④⑤⑥⑦⑧⑨⑩\.．、\s\(\)（）]+",
                "",
                raw_title,
            ).strip() or raw_title
            atomic_assets.append(make_asset(atomic_title, "独立公式", f"# {atomic_title}\n\n{atomic_block.strip()}\n"))
        generated.extend(atomic_assets)
        if atomic_assets:
            links = "\n".join(f"![[{asset.virtual_path}|{Path(asset.path).stem}]]" for asset in atomic_assets)
            level2_asset = make_asset(level2_title, "公式整理", f"# {level2_title}\n\n{links}\n")
            generated.append(level2_asset)
            level2_assets.append(level2_asset)

    if level2_assets:
        collection_title = f"{section_clean}_公式合集" if section_clean else f"{source_path.stem}_公式合集"
        links = "\n".join(f"![[{asset.virtual_path}|{Path(asset.path).stem}]]" for asset in level2_assets)
        generated.append(make_asset(collection_title, "公式合集", f"# {section_title} 公式合集\n\n{links}\n"))
    return generated


def discover_source_assets(source_book: Path, book_short: str) -> list[SourceAsset]:
    """Classify each source Markdown exactly once, with answers taking precedence."""
    assets: list[SourceAsset] = []
    for root, dirs, files in os.walk(source_book):
        dirs[:] = sorted(dirs)
        root_path = Path(root)
        rel_dir = root_path.relative_to(source_book)
        parts = rel_dir.parts
        if "images" in parts:
            dirs[:] = []
            continue
        for filename in sorted(files):
            if (
                not filename.endswith(".md")
                or filename.startswith(".")
                or filename == "index.md"
                or filename.endswith(".raw.md")
                or filename in ("answers.raw.md", "hierarchy.raw.md")
            ):
                continue
            path = root_path / filename
            relative = path.relative_to(source_book).as_posix()
            content = path.read_text(encoding="utf-8-sig")
            if "answers" in parts or "答案" in parts:
                node_type = "answers"
            elif "questions" in parts:
                node_type = "questions"
            # Question-group notes may contain words such as "公式法" in their
            # title.  They are not formula hierarchy nodes; treating them as
            # 独立公式 creates an illegal formula -> question edge.  Keep the
            # existing behavior for ordinary question groups (unclassified
            # unless their name explicitly matches a Tier-2 pattern).
            elif is_formula_note(filename) and "题目" not in parts:
                node_type = classify_formula_tier(filename)
            elif re.match(r"^(题型|考点|易错点|微专题|习题)", filename):
                node_type = "题型整理"
            elif is_paper_tier3(parts, filename):
                node_type = "题集"
            elif is_qt_tier2_name(filename):
                node_type = "题型整理"
            else:
                node_type = None
            if node_type:
                assets.append(
                    SourceAsset(
                        path=path,
                        relative=relative,
                        identity=source_identity(book_short, source_book, path),
                        virtual_path=f"{source_book.name}/{relative}",
                        node_type=node_type,
                        section=_section_from_parts(parts, source_book.name),
                        naming_section=parts[-1] if parts else "章节",
                        content=content,
                    )
                )
            if "questions" not in parts and "answers" not in parts and "答案" not in parts:
                assets.extend(
                    _generated_formula_assets(
                        source_book,
                        path,
                        relative,
                        book_short,
                        parts,
                        content,
                    )
                )
    return assets


def _asset_mapping_keys(asset: SourceAsset) -> tuple[str, ...]:
    return (asset.virtual_path, asset.relative, asset.virtual_path.lstrip("./"), asset.relative.lstrip("./"))


def _embed_targets(content: str) -> list[str]:
    return [target.strip().removesuffix(".md") for target in EMBED_RE.findall(content)]


def _closest_asset(owner: SourceAsset, candidates: list[SourceAsset]) -> Optional[SourceAsset]:
    if not candidates:
        return None
    owner_parts = Path(owner.relative).parts

    def score(candidate: SourceAsset) -> tuple[int, str]:
        candidate_parts = Path(candidate.relative).parts
        common = 0
        for left, right in zip(owner_parts, candidate_parts):
            if left != right:
                break
            common += 1
        return (-common, candidate.relative)

    return sorted(candidates, key=score)[0]


def _merge_embeds(existing: str, candidate: str) -> str:
    merged = existing
    existing_targets = set(_embed_targets(existing))
    for match in re.finditer(r"!\[\[[^\]]+\]\]", candidate):
        embed = match.group(0)
        targets = _embed_targets(embed)
        if targets and targets[0] not in existing_targets:
            merged = merged.rstrip() + f"\n\n{embed}\n"
            existing_targets.add(targets[0])
    return merged


def build_link_plan(
    vault_root: Path,
    source_book: Path,
    book_short: str,
    allow_create_knowledge_points: bool = False,
) -> LinkPlan:
    vault = vault_root.resolve()
    source_book = source_book.resolve()
    mathmap = vault / "mathmap"
    if not source_book.is_dir():
        raise SystemExit(f"源书目录不存在: {source_book}")
    if not mathmap.is_dir():
        raise SystemExit(f"mathmap 目录不存在: {mathmap}")

    store = RegistryStore(vault)
    plan = LinkPlan(vault, store, book_short)
    if not store.bootstrapped:
        plan.warnings.append(
            {
                "kind": "registry_not_bootstrapped",
                "message": "既有文件不会被覆盖；请先运行 bootstrap_registry.py --write-registry",
            }
        )
    assets = discover_source_assets(source_book, book_short)
    by_type: Dict[str, list[SourceAsset]] = defaultdict(list)
    for asset in assets:
        by_type[asset.node_type].append(asset)

    directories = {
        "questions": mathmap / "习题/questions",
        "answers": mathmap / "习题/answers",
        "题型整理": mathmap / "习题/题型整理",
        "题集": mathmap / "习题/题集",
        "公式合集": mathmap / "公式结论/公式合集",
        "公式整理": mathmap / "公式结论/公式整理",
        "独立公式": mathmap / "公式结论/独立公式",
    }
    unlinked_question_types = vault / UNLINKED_QUESTION_TYPES_DIR
    plan.ensure_directory(UNLINKED_QUESTION_TYPES_DIR)
    dedup_engine = MathMapDedupEngine(vault)
    name_map: Dict[str, str] = {}
    tier_map: Dict[str, str] = {}
    assignments: Dict[str, str] = {}
    matched_questions: set[str] = set()
    answer_by_stem: Dict[str, list[SourceAsset]] = defaultdict(list)
    answer_assignments: Dict[str, str] = {}
    for asset in by_type["answers"]:
        answer_by_stem[asset.path.stem].append(asset)

    def set_mapping(asset: SourceAsset, destination: str) -> None:
        tier_roots = {
            "questions": "mathmap/习题/questions/",
            "answers": "mathmap/习题/answers/",
            "题型整理": "mathmap/习题/题型整理/",
            "题集": "mathmap/习题/题集/",
            "公式合集": "mathmap/公式结论/公式合集/",
            "公式整理": "mathmap/公式结论/公式整理/",
            "独立公式": "mathmap/公式结论/独立公式/",
        }
        root = tier_roots[asset.node_type]
        target = destination.removeprefix(root).removesuffix(".md")
        for key in _asset_mapping_keys(asset):
            name_map[key] = target
            tier_map[key] = asset.node_type
        assignments[asset.identity] = destination
        plan.register_mapping(asset.identity, destination)

    def assign_answer(answer: SourceAsset, preferred_name: str) -> str:
        existing = answer_assignments.get(answer.identity)
        if existing:
            return existing
        destination = plan.choose_destination(
            directories["answers"],
            preferred_name,
            answer.naming_section,
            answer.identity,
            answer.content.encode("utf-8"),
        )
        answer_assignments[answer.identity] = destination
        set_mapping(answer, destination)
        return destination

    question_metadata: list[Dict[str, Any]] = []
    for asset in by_type["questions"]:
        normalized = normalize_latex(extract_stem(asset.content))
        normalized_hash = sha256_text(normalized)
        matched_q = store.find_qid_by_stem_hash(normalized_hash) or dedup_engine.match_question(extract_stem(asset.content))
        qid = asset.path.stem
        existing_qid = store.qids["questions"].get(qid) if re.fullmatch(r"Q\d+", qid) else None
        if existing_qid and existing_qid.get("normalized_stem_hash") != normalized_hash and not matched_q:
            destination = existing_qid.get("path", f"mathmap/习题/questions/{asset.path.name}")
            plan.add_conflict(destination, "QID 已由不同题干占用", asset.identity, asset.content.encode("utf-8"))
            continue
        previous_destination = store.destination_for_source(asset.identity)
        same_source_rerun = bool(previous_destination and Path(previous_destination).stem == Path(matched_q or "").stem)
        reuse_existing_question = bool(matched_q) and not same_source_rerun
        if matched_q:
            matched_name = Path(matched_q).name
            if not matched_name.endswith(".md"):
                matched_name += ".md"
            destination = f"mathmap/习题/questions/{matched_name}"
            if reuse_existing_question:
                matched_questions.add(asset.identity)
        else:
            destination = plan.choose_destination(
                directories["questions"],
                asset.path.name,
                asset.naming_section,
                asset.identity,
                asset.content.encode("utf-8"),
            )
            if not re.fullmatch(r"Q\d+\.md", Path(destination).name):
                plan.warnings.append(
                    {"kind": "noncanonical_question_name", "source": asset.relative, "destination": destination}
                )
        set_mapping(asset, destination)

        linked_answers: list[str] = []
        for target in _embed_targets(asset.content):
            answer_stem = Path(target).stem
            answer = _closest_asset(asset, answer_by_stem.get(answer_stem, []))
            if not answer:
                continue
            if reuse_existing_question:
                preferred = f"{Path(destination).stem}A_{_safe_component(book_short)}.md"
            else:
                preferred = answer.path.name
            answer_destination = assign_answer(answer, preferred)
            linked_answers.append(answer_destination.removesuffix(".md"))
        question_metadata.append(
            {
                "asset": asset,
                "destination": destination,
                "normalized_hash": normalized_hash,
                "answers": linked_answers,
                "matched": reuse_existing_question,
            }
        )

    for asset in by_type["answers"]:
        if asset.identity not in answer_assignments:
            assign_answer(asset, asset.path.name)
    unique_answer_stems = {stem for stem, values in answer_by_stem.items() if len(values) == 1}
    for stem in unique_answer_stems:
        answer = answer_by_stem[stem][0]
        destination = answer_assignments[answer.identity]
        name_map[stem] = Path(destination).stem
        tier_map[stem] = "answers"

    for asset in by_type["answers"]:
        destination = answer_assignments[asset.identity]
        plan.propose(
            destination,
            asset.content.encode("utf-8"),
            "answers",
            asset.identity,
            sha256_text(asset.content),
            "归档解析",
        )

    for metadata in question_metadata:
        asset = metadata["asset"]
        destination = metadata["destination"]
        if metadata["matched"]:
            content = plan.virtual_text(destination)
            for answer_target in metadata["answers"]:
                embed = f"![[{answer_target}|解析来源：{book_short}]]"
                if embed not in content:
                    content = content.rstrip() + f"\n\n{embed}\n"
            if metadata["answers"]:
                plan.propose(
                    destination,
                    content.encode("utf-8"),
                    "questions",
                    asset.identity,
                    sha256_text(asset.content),
                    "复用题干并追加新解析",
                )
        else:
            rewritten = rewrite_links(asset.content, name_map, tier_map)
            plan.propose(
                destination,
                rewritten.encode("utf-8"),
                "questions",
                asset.identity,
                sha256_text(asset.content),
                "归档题目并重写解析链接",
            )
            if re.fullmatch(r"Q\d+", Path(destination).stem):
                plan.question_registrations.append(
                    {
                        "qid": Path(destination).stem,
                        "destination": destination,
                        "normalized_stem_hash": metadata["normalized_hash"],
                        "origin": asset.identity,
                        "answers": metadata["answers"],
                    }
                )

    kp_dir = mathmap / "知识点"
    kp_index = build_kp_index(kp_dir)
    higher_assignments: list[Dict[str, Any]] = []
    for node_type in ("公式合集", "公式整理", "独立公式", "题集", "题型整理"):
        for asset in by_type[node_type]:
            knowledge_point = kp_for_section(
                asset.section,
                kp_index,
                kp_dir,
                SECTION_KP_MAP,
                CHAPTER_KP_MAP,
                allow_create=allow_create_knowledge_points,
            )
            matched_qt = (
                dedup_engine.match_problem_type(asset.path.name, knowledge_point=knowledge_point)
                if node_type == "题型整理" and knowledge_point
                else None
            )
            if matched_qt:
                destination = f"mathmap/习题/题型整理/{matched_qt[0]}"
            else:
                base_name = asset.path.name
                if node_type == "题集":
                    base_name = re.sub(r"^\d+-", "", base_name)
                destination_directory = (
                    unlinked_question_types
                    if node_type == "题型整理" and not knowledge_point
                    else directories[node_type]
                )
                mapped = plan.store.destination_for_source(asset.identity)
                linked_tier2_prefix = "mathmap/习题/题型整理/"
                if (
                    node_type == "题型整理"
                    and not knowledge_point
                    and mapped
                    and mapped.startswith(linked_tier2_prefix)
                    and not mapped.startswith(UNLINKED_QUESTION_TYPES_DIR + "/")
                ):
                    # Preserve previously published paths. Moving them automatically would
                    # break human-authored Obsidian links; a migration can promote them later.
                    destination = mapped
                    plan.reserved.add(mapped)
                else:
                    destination = plan.choose_destination(
                        destination_directory,
                        base_name,
                        asset.naming_section,
                        asset.identity,
                    )
            set_mapping(asset, destination)
            higher_assignments.append(
                {
                    "asset": asset,
                    "destination": destination,
                    "matched": bool(matched_qt),
                    "node_type": node_type,
                    "knowledge_point": knowledge_point,
                }
            )

    for item in higher_assignments:
        asset = item["asset"]
        destination = item["destination"]
        rewritten = rewrite_links(asset.content, name_map, tier_map)
        if item["matched"]:
            existing = plan.virtual_text(destination)
            proposed = _merge_embeds(existing, rewritten)
            reason = "题型语义匹配后合并题目链接"
        else:
            proposed = rewritten
            reason = "归档并重写当前来源内链"
        plan.propose(
            destination,
            proposed.encode("utf-8"),
            item["node_type"],
            asset.identity,
            sha256_text(asset.content),
            reason,
        )

    for item in higher_assignments:
        asset = item["asset"]
        destination = item["destination"]
        kp = item["knowledge_point"]
        if not kp:
            plan.warnings.append(
                {
                    "kind": "knowledge_point_review",
                    "source": asset.relative,
                    "section": asset.section,
                    "destination": destination,
                    "node_type": item["node_type"],
                    "unlinked_question_type_folder": (
                        UNLINKED_QUESTION_TYPES_DIR
                        if item["node_type"] == "题型整理"
                        else None
                    ),
                    "quarantined": destination.startswith(UNLINKED_QUESTION_TYPES_DIR + "/"),
                }
            )
            continue
        kp_destination = f"mathmap/知识点/{kp}.md"
        if not plan.absolute(kp_destination).is_file() and kp_destination not in plan.changes:
            if not allow_create_knowledge_points:
                plan.warnings.append(
                    {"kind": "missing_knowledge_point", "knowledge_point": kp, "source": asset.relative}
                )
                continue
            plan.propose(
                kp_destination,
                f"# {kp}\n\n# 题型\n\n# 公式与结论\n".encode("utf-8"),
                "知识点",
                f"generated-kp:{book_short}:{kp}",
                None,
                "显式授权创建知识点",
            )
        current = plan.virtual_text(kp_destination)
        updated, changed = render_kp_mount(current, item["node_type"], Path(destination).stem, book_short)
        if changed:
            plan.propose(
                kp_destination,
                updated.encode("utf-8"),
                "知识点",
                f"mount:{book_short}:{kp}",
                sha256_text(f"{asset.identity}:{destination}"),
                "追加来源分组挂载",
            )

    plan.audit()
    return plan


def archive_and_link_mathmap(
    vault_root: str,
    source_book_dir: str,
    book_short: str,
    apply: bool = False,
    allow_create_knowledge_points: bool = False,
    allow_audit_errors: bool = False,
    backup: bool = True,
) -> Dict[str, Any]:
    plan = build_link_plan(
        Path(vault_root),
        Path(source_book_dir),
        book_short,
        allow_create_knowledge_points=allow_create_knowledge_points,
    )
    mode = "apply" if apply else "dry-run"
    report = plan.report(mode)
    if apply:
        backup_dir = plan.apply(allow_audit_errors=allow_audit_errors, backup=backup)
        report["backup_dir"] = str(backup_dir) if backup else None
        report["applied"] = True
    else:
        report["applied"] = False
    return report


# 小节目录名 -> 知识点节点名（自动匹配不上的手工精确映射）
SECTION_KP_MAP = {
    "1.1.1_空间向量及其线性运算": "空间向量的线性运算",
    "1.1.2_空间向量的数量积运算": "空间向量的数量积运算",
    "1.2_空间向量基本定理": "空间向量基本定理",
    "1.3.1_空间直角坐标系_1.3.2_空间向量运算的坐标表示": "空间向量运算的坐标表示",
    "1.4.1_用空间向量研究直线、平面的位置关系": "用空间向量研究直线、平面的位置关系",
    "1.4.2_用空间向量研究距离、夹角问题": "用空间向量研究距离、夹角问题",
    "课时1_空间中点、直线和平面的向量表示": "空间中点、直线和平面的向量表示",
    "课时2_空间线面位置关系的判定": "用空间向量研究直线、平面的位置关系",
    "课时1_用空间向量研究距离问题": "用空间向量研究距离问题",
    "课时2_用空间向量研究夹角问题": "用空间向量研究夹角问题",
    "专题1_空间中的动点问题": "空间向量的应用",
    "第1.1~1.3节综合训练": "空间向量及其运算",
    "第1.4节综合训练": "空间向量的应用",
    "2.1.1_倾斜角与斜率_2.1.2_两条直线平行和垂直的判定": "直线的倾斜角与斜率",
    "2.2.1_直线的点斜式方程": "直线的点斜式方程",
    "2.2.2_直线的两点式方程": "直线的两点式方程",
    "2.2.3_直线的一般式方程": "直线的一般式方程",
    "2.3.1_两条直线的交点坐标": "两条直线的交点坐标",
    "2.3.2_两点间的距离公式": "两点间的距离公式",
    "2.3.3_点到直线的距离公式_2.3.4_两条平行直线间的距离": "点到直线的距离公式",
    "2.4.1_圆的标准方程": "圆的标准方程",
    "2.4.2_圆的一般方程": "圆的一般方程",
    "2.5.1_直线与圆的位置关系": "直线与圆的位置关系",
    "2.5.2_圆与圆的位置关系": "圆与圆的位置关系",
    "专题2_与直线有关的对称问题": "直线的方程",
    "专题3_与直线有关的最值问题": "直线的方程",
    "专题4_与圆有关的轨迹问题": "圆的方程",
    "第2.1节综合训练": "直线的倾斜角与斜率",
    "第2.2节综合训练": "直线的方程",
    "第2.3节综合训练": "直线的交点坐标与距离公式",
    "第2.4节综合训练": "圆的方程",
    "第2.5节综合训练": "直线与圆、圆与圆的位置关系",
    "3.1.1_椭圆及其标准方程": "椭圆及其标准方程",
    "3.1.2_椭圆的简单几何性质": "椭圆的简单几何性质",
    "3.2.1_双曲线及其标准方程": "双曲线的标准方程",
    "3.2.2_双曲线的简单几何性质": "双曲线的简单几何性质",
    "3.3.1_抛物线及其标准方程": "抛物线的标准方程",
    "3.3.2_抛物线的简单几何性质": "抛物线的简单几何性质",
    "课时1_椭圆的简单几何性质": "椭圆的简单几何性质",
    "课时2_直线与椭圆的位置关系": "椭圆的综合应用",
    "课时1_双曲线的简单几何性质": "双曲线的简单几何性质",
    "课时2_直线与双曲线的位置关系": "双曲线的综合应用",
    "专题5_求离心率的值或取值范围": "椭圆的综合应用",
    "专题6_圆锥曲线中的中点弦、对称问题": "第三章 圆锥曲线的方程",
    "专题7_圆锥曲线中的范围、最值问题": "第三章 圆锥曲线的方程",
    "专题8_圆锥曲线中的定点、定值问题": "第三章 圆锥曲线的方程",
    "专题9_圆锥曲线中的存在、探索性问题": "第三章 圆锥曲线的方程",
    "第3.1节综合训练": "椭圆",
    "第3.2节综合训练": "双曲线",
    "第3.3节综合训练": "抛物线",
    "第一章素养检测": "第一章 空间向量与立体几何",
    "第一章高考强化": "第一章 空间向量与立体几何",
    "第二章素养检测": "第二章 直线和圆的方程",
    "第二章高考强化": "第二章 直线和圆的方程",
    "第三章素养检测": "第三章 圆锥曲线的方程",
    "第三章高考强化": "第三章 圆锥曲线的方程",
    "专练1_新定义、新情境专练": "第三章 圆锥曲线的方程",
    "专练2_开放题专练": "第三章 圆锥曲线的方程",
    "模块综合测试": "第三章 圆锥曲线的方程",
    "第一节 任意角与弧度制": "任意角和弧度制",
    "第二节 三角函数的定义": "三角函数的概念",
    "第三节 同角的三角函数关系": "同角三角函数的基本关系",
    "第四节 诱导公式": "诱导公式",
    "第五节 三角函数的图像": "三角函数的图象与性质",
    "第六节 正余弦函数的性质": "三角函数的性质",
    "第七节 正切函数的图像与性质": "正切函数的性质与图象",
    "第八节 两角和与差公式": "两角和与差的正弦、余弦、正切公式",
    "第九节 倍角公式": "二倍角的正弦、余弦、正切公式",
    "第十节 半角与积化和差和差化积公式": "简单的三角恒等变换",
    "第十一节 正弦型三角函数的图像与性质": "三角函数的图象与性质",
    "第十二节 专题 三角函数的图像变换问题": "三角函数的图象与性质",
    "第十三节 专题 求 omega 的取值范围问题": "三角函数的图象与性质",
    "第十四节（补充）反三角函数": "反三角函数",
    "第一节 向量的概念及加减法运算": "平面向量的概念",
    "第二节 向量的数乘运算": "向量的数乘运算",
    "第三节 平面向量基本定理": "平面向量基本定理",
    "第四节 向量的数量积": "向量的数量积",
    "第五节 向量的坐标表示": "平面向量基本定理及坐标表示",
    "第六节 专题 与向量有关的取值范围方法总结": "平面向量的应用",
    "第七节 专题 极化恒等式与等和线问题": "平面向量的应用",
    "第八节 正弦、余弦定理": "余弦定理、正弦定理",
    "第九节 专题 三角形四心的向量表示": "平面向量的应用",
    "第十节 专题 奔驰定理与面积问题": "平面向量的应用",
    "第十一节 专题 解三角形基础解答题专练": "余弦定理、正弦定理",
    "第十二节 专题 三角形中的范围与最值问题": "余弦定理、正弦定理",
    "第十三节 专题 三角形中的角分线中线高线问题": "余弦定理、正弦定理",
    "第十四节 专题 多三角形组合问题": "余弦定理、正弦定理",
}

# 章目录名 -> 章知识点节点（兜底）
CHAPTER_KP_MAP = {
    "01-第一章_空间向量与立体几何": "第一章 空间向量与立体几何",
    "02-第二章_直线和圆的方程": "第二章 直线和圆的方程",
    "03-第三章_圆锥曲线的方程": "第三章 圆锥曲线的方程",
    "04-高考新题型": "第三章 圆锥曲线的方程",
    "三角函数": "第五章 三角函数",
    "平面向量": "第六章 平面向量及其应用",
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MathMap 安全归档计划、人工编辑保护与知识点挂载")
    parser.add_argument("vault_root", help="vault 根目录（如 /Users/oven/Documents/ovenmathmap）")
    parser.add_argument("source_book_dir", help="源书 QTG 产物目录（含 01-第一章... 等章节目录）")
    parser.add_argument("book_short", help="书短名，用于冲突文件命名空间与知识点来源分组（如 选择性必修第一册RJA）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="应用计划；默认只做 dry-run")
    mode.add_argument("--dry-run", action="store_true", help="显式只生成计划（默认行为）")
    parser.add_argument("--plan-out", help="把 JSON 计划写到指定路径")
    parser.add_argument(
        "--allow-create-knowledge-points",
        action="store_true",
        help="显式允许为无法映射的小节创建知识点；默认进入人工审查",
    )
    parser.add_argument(
        "--allow-audit-errors",
        action="store_true",
        help="即使变更子图审计失败仍应用（高风险，不建议）",
    )
    parser.add_argument("--no-backup", action="store_true", help="应用前不备份将被修改的既有文件")
    args = parser.parse_args()
    try:
        result = archive_and_link_mathmap(
            args.vault_root,
            args.source_book_dir,
            args.book_short,
            apply=args.apply,
            allow_create_knowledge_points=args.allow_create_knowledge_points,
            allow_audit_errors=args.allow_audit_errors,
            backup=not args.no_backup,
        )
    except RuntimeError as exc:
        parser.exit(2, f"错误: {exc}\n")
    if args.plan_out:
        atomic_write_json(Path(args.plan_out), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
