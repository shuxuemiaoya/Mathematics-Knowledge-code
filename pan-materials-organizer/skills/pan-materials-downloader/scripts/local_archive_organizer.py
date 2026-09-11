# -*- coding: utf-8 -*-
"""
Local Archive Organizer
对本地下载的初高中教辅文件进行智能分拣，构建教学大纲标准化层级，并生成全量 manifest 索引。
"""

import os
import sys
import shutil
import hashlib
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

# 引入命名规则解析器
SCRIPT_DIR = Path(__file__).resolve().parent
NAMING_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "baidu-pan-organizer" / "scripts"
if str(NAMING_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(NAMING_SCRIPT_DIR))

from naming_rules import parse_material_name

def calculate_sha256(filepath: Path) -> str:
    """计算文件 SHA256 哈希值"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def organize_downloaded_folder(
    source_dir: str,
    target_vault_dir: str,
    move_files: bool = False
) -> Dict[str, Any]:
    """遍历源文件夹，自动分拣整理到目标教研标准拓扑"""
    src_path = Path(source_dir).resolve()
    dst_path = Path(target_vault_dir).resolve()

    if not src_path.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    dst_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_dir": str(src_path),
        "target_vault_dir": str(dst_path),
        "total_files": 0,
        "items": []
    }

    supported_exts = {".pdf", ".docx", ".doc", ".zip", ".rar", ".png", ".jpg"}

    for p in src_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in supported_exts and not p.name.startswith("."):
            meta = parse_material_name(p.stem)
            
            # 组装标准目标路径
            rel_dir = Path(meta["stage"]) / meta["subject"] / meta["edition"] / meta["volume"] / meta["standard_folder"]
            target_file_dir = dst_path / rel_dir
            target_file_dir.mkdir(parents=True, exist_ok=True)

            final_filename = f"{meta['role']}_{p.name}"
            final_target_file = target_file_dir / final_filename

            sha256 = calculate_sha256(p)
            file_size_mb = round(p.stat().st_size / (1024 * 1024), 2)

            if move_files:
                shutil.move(str(p), str(final_target_file))
                action = "moved"
            else:
                shutil.copy2(str(p), str(final_target_file))
                action = "copied"

            item_info = {
                "original_path": str(p),
                "target_path": str(final_target_file),
                "action": action,
                "size_mb": file_size_mb,
                "sha256": sha256,
                "meta": meta
            }
            manifest["items"].append(item_info)
            print(f"[{action.upper()}] {p.name} -> {rel_dir / final_filename}")

    manifest["total_files"] = len(manifest["items"])
    manifest_file = dst_path / "materials_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n整理完毕！共归档 {manifest['total_files']} 个文件。清单已写入: {manifest_file}")
    return manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local Educational Materials Archive Organizer")
    parser.add_argument("--source", required=True, help="Path to raw downloaded materials")
    parser.add_argument("--target", required=True, help="Path to organized vault directory")
    parser.add_argument("--move", action="store_true", help="Move files instead of copying")
    args = parser.parse_args()

    organize_downloaded_folder(args.source, args.target, move_files=args.move)
