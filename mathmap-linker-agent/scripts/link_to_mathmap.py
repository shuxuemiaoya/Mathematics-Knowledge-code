#!/usr/bin/env python3
"""mathmap 习题三层归档 + 知识点挂载 链接器（通用多书版）。

用法：
    python3 link_to_mathmap.py <vault_root> <source_book_dir> <book_short_name>

示例：
    python3 link_to_mathmap.py /Users/oven/Documents/ovenmathmap \
        "/Users/oven/Documents/ovenmathmap/课堂同步/教辅/必刷题/2026版 必刷题 数学选择性必修第一册RJA" \
        选择性必修第一册RJA

功能（四遍式）：
  Pass 1  Tier1 questions/answers 归档（Q 文件重写答案嵌入，跳过已存在）
  Pass 2  Tier2 题型整理 + Tier3 题集 落盘（全路径链接重写、冲突命名、幂等）
  Pass 3  统一重写已落盘笔记内链（按源全路径映射，避免同名错链）
  Pass 4  知识点挂载：每个题型整理/题集节点挂到 mathmap/知识点 对应节点的
           # 题型 章节（按「## 来源：<书短名>」分组，已存在跳过）

关键设计（防重蹈覆辙）：
  - 链接重写一律基于「源文件全路径 -> mathmap 目标」映射，绝不按 basename
    匹配（同名 _bN 文件在不同小节大量存在，basename 会导致错链/覆盖）。
  - 冲突命名稳定：同名优先「小节目录名_原名」，再冲突加书短名前缀；
    existing 集合只统计 git 已跟踪文件，保证重复运行幂等（相同源->相同目标）。
  - 落盘前比对内容，相同则跳过写入（幂等，不产生重复副本）。
  - 知识点挂载纯新增（绝不删除既有行），旧书挂载完整保留。
"""
import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path


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


def safe_dest_name(base: str, section: str, existing: set, used: set) -> str:
    """生成无冲突的目标文件名（幂等）。

    优先用原名；冲突时用「小节目录名_原名」；再冲突则加书短名前缀。
    existing 只含已跟踪（旧书）文件，保证相同源文件始终得到相同目标名。
    """
    if base not in existing and base not in used:
        used.add(base)
        return base
    prefixed = f"{section}_{base}"
    if prefixed not in existing and prefixed not in used:
        used.add(prefixed)
        return prefixed
    book_prefixed = f"{BOOK_SHORT}_{base}"
    n = 2
    while book_prefixed in existing or book_prefixed in used:
        book_prefixed = f"{BOOK_SHORT}_{n}_{base}"
        n += 1
    used.add(book_prefixed)
    return book_prefixed


def rewrite_links(content: str, name_map: dict, tier_map: dict) -> str:
    """按「源全路径 -> mathmap 目标」重写笔记内 ![[...]] 链接。

    name_map: 源文件全路径(书目录名开头,含.md) -> mathmap 目标 stem
    tier_map: 源文件全路径 -> "questions"|"answers"|"题型整理"|"题集"
    优先全路径精确匹配；Q 单题按 basename 兜底；未知链接原样保留。
    """

    def repl(match):
        link_path = match.group(1)
        norm = link_path.lstrip("./")
        if norm in name_map:
            target = name_map[norm]
            tier = tier_map.get(norm, "题型整理")
            return f"![[mathmap/习题/{tier}/{target}|{clean_title(target)}]]"
        stem = link_target_stem(link_path)
        if re.match(r"^Q\d+$", stem):
            return f"![[mathmap/习题/questions/{stem}|{stem}]]"
        if re.match(r"^Q\d+A\d+$", stem):
            return f"![[mathmap/习题/answers/{stem}|{stem}]]"
        return match.group(0)

    return re.sub(r"!\[\[([^\]]+)\]\]", repl, content)


# ================= 知识点挂载 =================

def build_kp_index(kp_dir: Path) -> dict:
    """知识点节点名 -> 规范名（去空白），用于匹配。"""
    return {re.sub(r"[\s·:：,，。.．~～+＋]", "", p.stem): p.stem for p in kp_dir.glob("*.md")}


def kp_for_section(section: str, kp_index: dict, kp_dir: Path, section_map: dict, chapter_map: dict):
    """小节目录名/章目录名 -> 知识点节点名。

    匹配顺序：手工映射表 -> 章目录表 -> 精确（去编号前缀）-> 子串模糊。
    """
    if section in section_map:
        return section_map[section]
    if section in chapter_map:
        return chapter_map[section]
    s = re.sub(r"^\d+(\.\d+)*_", "", section)
    norm_s = re.sub(r"[\s·:：,，。.．~～+＋]", "", s)
    if norm_s in kp_index:
        return kp_index[norm_s]
    for stem, norm_k in kp_index.items():
        if len(norm_k) >= 3 and (norm_k in norm_s or norm_s in norm_k):
            return stem
    return None


def mount_kp(kp: str, tier: str, stem: str, kp_dir: Path, book_short: str) -> bool:
    """把 (tier, stem) 挂载到知识点节点 kp 的 # 题型 章节（纯新增，幂等）。

    返回 True 表示本次新增挂载。
    """
    kp_path = kp_dir / f"{kp}.md"
    if not kp_path.is_file():
        print(f"  !! 知识点节点缺失: {kp}")
        return False
    text = kp_path.read_text(encoding="utf-8-sig")
    embed = f"![[mathmap/习题/{tier}/{stem}|{clean_title(stem)}]]"
    if embed in text:
        return False
    source_heading = f"## 来源：{book_short}"

    if "# 题型" not in text:
        text = text.rstrip() + "\n\n# 题型\n"
    q_idx = text.find("# 题型")
    if source_heading in text[q_idx:]:
        # 追加到已有来源分组内（分组末尾，不越过下一个 ## 标题）
        pos = text.find(source_heading, q_idx)
        end = text.find("\n## ", pos + len(source_heading))
        if end == -1:
            end = len(text)
        text = text[:end].rstrip() + f"\n{embed}\n" + text[end:]
    else:
        # 新建来源分组，插在 # 题型 标题之后
        q_end = text.find("\n", q_idx)
        after = text[q_end:]
        text = text[:q_end] + f"\n{source_heading}\n{embed}" + after
    kp_path.write_text(text, encoding="utf-8")
    return True


# ================= 主流程 =================

def archive_and_link_mathmap(vault_root: str, source_book_dir: str, book_short: str):
    global BOOK_SHORT
    BOOK_SHORT = book_short

    vault = Path(vault_root)
    source_book = Path(source_book_dir)
    if not source_book.is_dir():
        raise SystemExit(f"源书目录不存在: {source_book}")

    mathmap = vault / "mathmap"
    q_dest = mathmap / "习题/questions"
    a_dest = mathmap / "习题/answers"
    qt_dest = mathmap / "习题/题型整理"
    paper_dest = mathmap / "习题/题集"
    kp_dir = mathmap / "知识点"
    for d in (q_dest, a_dest, qt_dest, paper_dest):
        d.mkdir(parents=True, exist_ok=True)

    # existing_* 只统计 git 已跟踪（旧书）文件：保证冲突命名与幂等稳定
    def tracked_in(d: Path) -> set:
        out = subprocess.run(
            ["git", "-C", str(vault), "-c", "core.quotepath=false", "ls-files", str(d)],
            capture_output=True, text=True,
        ).stdout
        return {os.path.basename(p) for p in out.splitlines() if p}

    existing_qt = tracked_in(qt_dest)
    existing_paper = tracked_in(paper_dest)
    existing_q = tracked_in(q_dest)
    existing_a = tracked_in(a_dest)

    q_copied = a_copied = qt_copied = paper_copied = 0
    q_skipped = a_skipped = 0
    tier2_used: set = set()
    tier3_used: set = set()
    name_map: dict = {}   # 源文件全路径(书目录名开头) -> mathmap stem
    tier_map: dict = {}
    paper_plans = []      # (src, clean_name, rel_dir)
    qt_plans = []         # (src, fname, section_dir)

    def src_vp(p: str) -> str:
        """链接中使用的路径：书目录名 + 相对书根的路径。"""
        return os.path.join(source_book.name, os.path.relpath(p, source_book))

    # ---- Pass 1: Tier1 questions/answers ----
    for root, dirs, files in os.walk(source_book):
        rel_dir = os.path.relpath(root, source_book)
        parts = rel_dir.split(os.sep)
        if "questions" in parts:
            for f in files:
                if not f.endswith(".md") or f.startswith("."):
                    continue
                src = os.path.join(root, f)
                if f in existing_q:
                    q_skipped += 1
                    continue
                content = Path(src).read_text(encoding="utf-8-sig")
                content = re.sub(r"!\[\[(Q\d+A\d+)(\.md)?\]\]", r"![[mathmap/习题/answers/\1|\1]]", content)
                (q_dest / f).write_text(content, encoding="utf-8")
                q_copied += 1
                name_map[src_vp(src)] = os.path.splitext(f)[0]
                tier_map[src_vp(src)] = "questions"
        if "answers" in parts or "答案" in parts:
            for f in files:
                if not f.endswith(".md") or f.startswith("."):
                    continue
                src = os.path.join(root, f)
                if f in existing_a:
                    a_skipped += 1
                    continue
                shutil.copy2(src, a_dest / f)
                a_copied += 1
                name_map[src_vp(src)] = os.path.splitext(f)[0]
                tier_map[src_vp(src)] = "answers"

    # ---- Pass 2: Tier2/Tier3 落盘计划 ----
    for root, dirs, files in os.walk(source_book):
        rel_dir = os.path.relpath(root, source_book)
        parts = rel_dir.split(os.sep)
        if "questions" in parts or "answers" in parts or "images" in parts:
            continue
        for f in files:
            if not f.endswith(".md") or f.startswith(".") or f == "index.md":
                continue
            src = os.path.join(root, f)
            if is_paper_tier3(parts, f):
                clean_name = f
                if len(parts) >= 2 and re.search(r"_b\d+\.md$", f):
                    sec_folder = parts[-2] if parts[-1].startswith("刷") else parts[-1]
                    clean_name = f"{sec_folder}_{f}"
                clean_name = re.sub(r"^\d+-", "", clean_name)
                paper_plans.append((src, clean_name, rel_dir))
            elif is_qt_tier2_name(f):
                section_dir = parts[-2] if len(parts) >= 2 else "章节"
                qt_plans.append((src, f, section_dir))

    # Tier3 落盘
    for src, clean_name, rel_dir in paper_plans:
        base = clean_name
        vp = src_vp(src)
        final_name = base
        if base in existing_paper or base in tier3_used:
            final_name = f"{book_short}_{base}"
            n = 2
            while final_name in existing_paper or final_name in tier3_used:
                final_name = f"{book_short}_{n}_{base}"
                n += 1
        tier3_used.add(final_name)
        content = Path(src).read_text(encoding="utf-8-sig")
        name_map[vp] = os.path.splitext(final_name)[0]
        tier_map[vp] = "题集"
        dst = paper_dest / final_name
        if dst.is_file() and dst.read_text(encoding="utf-8-sig") == content:
            pass  # 幂等
        else:
            dst.write_text(content, encoding="utf-8")
        paper_copied += 1

    # Tier2 落盘
    for src, fname, section_dir in qt_plans:
        vp = src_vp(src)
        final_name = safe_dest_name(fname, section_dir, existing_qt, tier2_used)
        name_map[vp] = os.path.splitext(final_name)[0]
        tier_map[vp] = "题型整理"
        dst = qt_dest / final_name
        if dst.is_file():
            if dst.read_bytes() == Path(src).read_bytes():
                pass  # 幂等
            else:
                shutil.copy2(src, dst)
        else:
            shutil.copy2(src, dst)
        qt_copied += 1

    # ---- Pass 3: 统一重写已落盘笔记内链 ----
    for d, tier in ((qt_dest, "题型整理"), (paper_dest, "题集")):
        for f in os.listdir(d):
            if not f.endswith(".md"):
                continue
            p = d / f
            content = p.read_text(encoding="utf-8-sig")
            new_content = rewrite_links(content, name_map, tier_map)
            if new_content != content:
                p.write_text(new_content, encoding="utf-8")

    # ---- Pass 4: 知识点挂载 ----
    kp_index = build_kp_index(kp_dir)
    kp_mounted = kp_skipped = 0
    for vp in [v for v, t in tier_map.items() if t in ("题型整理", "题集")]:
        tier = tier_map[vp]
        stem = name_map[vp]
        # 从源路径提取所属章节/小节目录（跳过文件名段）
        vp_parts = vp.split(os.sep)
        section = None
        for part in reversed(vp_parts[:-1]):
            if re.match(r"^(\d+(\.\d+)*|课时|专题|专练|第\d|模块|第一章|第二章|第三章|第[一二三]章)", part):
                section = part
                break
        if section is None:
            section = vp_parts[0]
        kp = kp_for_section(section, kp_index, kp_dir, SECTION_KP_MAP, CHAPTER_KP_MAP)
        if kp is None:
            print(f"  !! 未匹配知识点: {vp} (section={section})")
            continue
        if mount_kp(kp, tier, stem, kp_dir, book_short):
            kp_mounted += 1
        else:
            kp_skipped += 1

    print(f"Tier 1: 原始题目归档 (mathmap/习题/questions): {q_copied} 个 (跳过已存在 {q_skipped})")
    print(f"Tier 1: 原始解析归档 (mathmap/习题/answers): {a_copied} 个 (跳过已存在 {a_skipped})")
    print(f"Tier 2: 题型整理归档 (mathmap/习题/题型整理): {qt_copied} 个")
    print(f"Tier 3: 题集总集归档 (mathmap/习题/题集): {paper_copied} 个")
    print(f"知识点挂载: 新增 {kp_mounted}, 跳过已存在 {kp_skipped}")


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
}

# 章目录名 -> 章知识点节点（兜底）
CHAPTER_KP_MAP = {
    "01-第一章_空间向量与立体几何": "第一章 空间向量与立体几何",
    "02-第二章_直线和圆的方程": "第二章 直线和圆的方程",
    "03-第三章_圆锥曲线的方程": "第三章 圆锥曲线的方程",
    "04-高考新题型": "第三章 圆锥曲线的方程",
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="mathmap 习题三层归档 + 知识点挂载")
    parser.add_argument("vault_root", help="vault 根目录（如 /Users/oven/Documents/ovenmathmap）")
    parser.add_argument("source_book_dir", help="源书 QTG 产物目录（含 01-第一章... 等章节目录）")
    parser.add_argument("book_short", help="书短名，用于冲突文件命名空间与知识点来源分组（如 选择性必修第一册RJA）")
    args = parser.parse_args()
    archive_and_link_mathmap(args.vault_root, args.source_book_dir, args.book_short)
