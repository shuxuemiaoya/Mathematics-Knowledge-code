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

# 导入多层级语义去重与合并引擎
try:
    from mathmap_dedup import MathMapDedupEngine, normalize_latex, extract_stem, compare_qt_titles
except ImportError:
    from scripts.mathmap_dedup import MathMapDedupEngine, normalize_latex, extract_stem, compare_qt_titles



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


def extract_and_file_knowledge_guide(src: str, content: str, book_short: str, mathmap_dir: Path, name_map: dict, tier_map: dict) -> list:
    """若文件包含 ## 知识导学 / ## 知识梳理 / ## 考点精讲，解析其标题架构，自动提取 3 级公式结论卡片。

    1. 公式合集 (Level 1): <小节名>_公式合集.md
    2. 公式整理 (Level 2): <大主题名>.md (如 任意角.md, 弧度制.md)
    3. 独立公式 (Level 3/Atomic): <细分考点名>.md (如 终边相同的角.md, 扇形公式.md)
    """
    if "## 知识导学" not in content and "## 知识梳理" not in content and "## 考点精讲" not in content:
        return []

    # 截取 知识导学 / 知识梳理 / 考点精讲 区块
    guide_match = re.search(r"(##\s*(?:知识导学|知识梳理|考点精讲).*?)(?=\n#\s|\n##\s*(?:重点题型|刷题|习题|考点分类|例题)|$)", content, flags=re.DOTALL)
    if not guide_match:
        return []

    guide_text = guide_match.group(1)
    
    sec_match = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    sec_title = sec_match.group(1).strip() if sec_match else Path(src).stem
    sec_clean = re.sub(r"^第[0-9一二三四五六七八九十]+[节章]\s*", "", sec_title).strip()

    col_dir = mathmap_dir / "公式结论/公式合集"
    sum_dir = mathmap_dir / "公式结论/公式整理"
    atomic_dir = mathmap_dir / "公式结论/独立公式"
    for d in (col_dir, sum_dir, atomic_dir):
        d.mkdir(parents=True, exist_ok=True)

    extracted_stems = []

    # 解析 Level 2 块 (## 一. 任意角, ## 二. 弧度制)
    level2_blocks = re.split(r"\n(?=##\s+[一二三四五六七八九十]+\.\s*)", guide_text)
    level2_stems = []

    for block in level2_blocks:
        l2_match = re.match(r"##\s+[一二三四五六七八九十]+\.\s*([^\n]+)", block)
        if not l2_match:
            continue
        l2_title = l2_match.group(1).strip()

        # 解析 Level 3 / 独立公式 (## 1. 角的相关概念, ## 3. 终边相同的角, ## 6. 关于扇形的几个公式)
        atomic_blocks = re.split(r"\n(?=##\s+\d+[\.．、\s]\s*)", block)
        atomic_stems = []

        for a_block in atomic_blocks:
            a_match = re.match(r"##\s+\d+[\.．、\s]\s*([^\n]+)", a_block)
            if not a_match:
                continue
            a_raw_title = a_match.group(1).strip()
            a_title = re.sub(r"^[0-9一二三四五六七八九十①②③④⑤⑥⑦⑧⑨⑩\.．、\s\(\)（）]+", "", a_raw_title).strip()
            if not a_title:
                a_title = a_raw_title
            
            atomic_file = atomic_dir / f"{a_title}.md"
            atomic_body = f"# {a_title}\n\n{a_block.strip()}\n"
            if not atomic_file.exists() or atomic_file.read_text(encoding="utf-8-sig") != atomic_body:
                atomic_file.write_text(atomic_body, encoding="utf-8")
            
            atomic_stems.append(a_title)
            vp_atomic = f"formula:{a_title}"
            name_map[vp_atomic] = a_title
            tier_map[vp_atomic] = "独立公式"
            extracted_stems.append((vp_atomic, "独立公式", a_title))

        # 生成 Level 2 公式整理文件
        if atomic_stems:
            l2_body_lines = [f"# {l2_title}\n"]
            for a_stem in atomic_stems:
                l2_body_lines.append(f"![[mathmap/公式结论/独立公式/{a_stem}|{a_stem}]]\n")
            l2_body = "\n".join(l2_body_lines)
            l2_file = sum_dir / f"{l2_title}.md"
            if not l2_file.exists() or l2_file.read_text(encoding="utf-8-sig") != l2_body:
                l2_file.write_text(l2_body, encoding="utf-8")
            
            level2_stems.append(l2_title)
            vp_l2 = f"formula:{l2_title}"
            name_map[vp_l2] = l2_title
            tier_map[vp_l2] = "公式整理"
            extracted_stems.append((vp_l2, "公式整理", l2_title))

    # 生成 Level 1 公式合集文件
    if level2_stems:
        col_title = f"{sec_clean}_公式合集" if sec_clean else f"{Path(src).stem}_公式合集"
        col_file = col_dir / f"{col_title}.md"
        col_body_lines = [f"# {sec_title} 公式合集\n"]
        for l2_stem in level2_stems:
            col_body_lines.append(f"![[mathmap/公式结论/公式整理/{l2_stem}|{l2_stem}]]\n")
        col_body = "\n".join(col_body_lines)
        if not col_file.exists() or col_file.read_text(encoding="utf-8-sig") != col_body:
            col_file.write_text(col_body, encoding="utf-8")
        vp_col = f"formula:{col_title}"
        name_map[vp_col] = col_title
        tier_map[vp_col] = "公式合集"
        extracted_stems.append((vp_col, "公式合集", col_title))

    return extracted_stems


def rewrite_links(content: str, name_map: dict, tier_map: dict) -> str:
    """按「源全路径 -> mathmap 目标」重写笔记内 ![[...]] 链接。

    name_map: 源文件全路径(书目录名开头,含.md) -> mathmap 目标 stem
    tier_map: 源文件全路径 -> "questions"|"answers"|"题型整理"|"题集"|"公式合集"|"公式整理"|"独立公式"
    优先全路径精确匹配；Q 单题按 basename 兜底；未知链接原样保留。
    """

    def repl(match):
        link_path = match.group(1)
        norm = link_path.lstrip("./")
        if norm in name_map:
            target = name_map[norm]
            tier = tier_map.get(norm, "题型整理")
            if tier in ("公式合集", "公式整理", "独立公式"):
                return f"![[mathmap/公式结论/{tier}/{target}|{clean_title(target)}]]"
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

    匹配逻辑：
      1. 手工精确映射
      2. 细分知识点分离：若原旧节点为多概念组合节点（含 _ 或 与/及），而新目录为拆分后的精细单概念，
         创建并指向全新的独立知识点节点。
      3. 精确匹配 -> 子串匹配。
    """
    if section in section_map:
        return section_map[section]
    if section in chapter_map:
        return chapter_map[section]

    s = re.sub(r"^\d+(\.\d+)*_", "", section)
    norm_s = re.sub(r"[\s·:：,，。.．~～+＋]", "", s)

    # 检查是否为精细切分小节
    if norm_s in kp_index:
        matched_name = kp_index[norm_s]
        # 如果已存在的匹配节点是多概念组合节点 (例如含 '_' 或 '及'/'与')，且当前小节为单概念，建立独立节点
        if ("_" in matched_name or "及" in matched_name or "与" in matched_name) and ("_" not in s and "及" not in s and "与" not in s):
            new_kp_name = s.strip()
            new_kp_file = kp_dir / f"{new_kp_name}.md"
            if not new_kp_file.exists():
                new_kp_file.write_text(f"# {new_kp_name}\n\n# 题型\n", encoding="utf-8")
                kp_index[re.sub(r"[\s·:：,，。.．~～+＋]", "", new_kp_name)] = new_kp_name
            return new_kp_name
        return matched_name

    for stem, norm_k in kp_index.items():
        if len(norm_k) >= 3 and (norm_k in norm_s or norm_s in norm_k):
            return stem

    # 无法匹配时，自动建立新的精细知识点节点（不强行盲目合并到组合大节点）
    clean_section_name = s.strip()
    if clean_section_name:
        new_kp_file = kp_dir / f"{clean_section_name}.md"
        if not new_kp_file.exists():
            new_kp_file.write_text(f"# {clean_section_name}\n\n# 题型\n", encoding="utf-8")
            kp_index[re.sub(r"[\s·:：,，。.．~～+＋]", "", clean_section_name)] = clean_section_name
        return clean_section_name

    return None


def mount_kp(kp: str, tier: str, stem: str, kp_dir: Path, book_short: str) -> bool:
    """把 (tier, stem) 挂载到知识点节点 kp 的对应章节（纯新增，标明来源，幂等）。
    - 题型节点 -> # 题型
    - 公式/结论节点 -> # 公式与结论
    """
    kp_path = kp_dir / f"{kp}.md"
    if not kp_path.is_file():
        kp_path.write_text(f"# {kp}\n\n# 题型\n\n# 公式与结论\n", encoding="utf-8")

    text = kp_path.read_text(encoding="utf-8-sig")

    if tier in ("公式合集", "公式整理", "独立公式"):
        embed = f"![[mathmap/公式结论/{tier}/{stem}|{clean_title(stem)}]]"
        heading_target = "# 公式与结论"
    else:
        embed = f"![[mathmap/习题/{tier}/{stem}|{clean_title(stem)}]]"
        heading_target = "# 题型"

    if embed in text:
        return False
    source_heading = f"## 来源：{book_short}"

    if heading_target not in text:
        text = text.rstrip() + f"\n\n{heading_target}\n"
    q_idx = text.find(heading_target)
    if source_heading in text[q_idx:]:
        pos = text.find(source_heading, q_idx)
        end = text.find("\n## ", pos + len(source_heading))
        if end == -1:
            end = len(text)
        text = text[:end].rstrip() + f"\n{embed}\n" + text[end:]
    else:
        q_end = text.find("\n", q_idx)
        if q_end == -1:
            q_end = len(text)
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
    formula_col_dest = mathmap / "公式结论/公式合集"
    formula_sum_dest = mathmap / "公式结论/公式整理"
    formula_atomic_dest = mathmap / "公式结论/独立公式"
    kp_dir = mathmap / "知识点"
    for d in (q_dest, a_dest, qt_dest, paper_dest, formula_col_dest, formula_sum_dest, formula_atomic_dest):
        d.mkdir(parents=True, exist_ok=True)

    # existing_* 只统计 git 已跟踪（旧书）文件：保证冲突命名与幂等稳定
    def tracked_in(d: Path) -> set:
        if not d.exists():
            return set()
        out = subprocess.run(
            ["git", "-C", str(vault), "-c", "core.quotepath=false", "ls-files", str(d)],
            capture_output=True, text=True,
        ).stdout
        return {os.path.basename(p) for p in out.splitlines() if p}

    existing_qt = tracked_in(qt_dest)
    existing_paper = tracked_in(paper_dest)
    existing_q = tracked_in(q_dest)
    existing_a = tracked_in(a_dest)
    existing_formula_col = tracked_in(formula_col_dest)
    existing_formula_sum = tracked_in(formula_sum_dest)
    existing_formula_atomic = tracked_in(formula_atomic_dest)

    q_copied = a_copied = qt_copied = paper_copied = formula_copied = 0
    q_skipped = a_skipped = 0
    tier2_used: set = set()
    tier3_used: set = set()
    formula_used: set = set()
    name_map: dict = {}   # 源文件全路径(书目录名开头) -> mathmap stem
    tier_map: dict = {}
    paper_plans = []      # (src, clean_name, rel_dir)
    qt_plans = []         # (src, fname, section_dir)
    formula_plans = []    # (src, fname, f_tier, section_dir)

    def src_vp(p: str) -> str:
        """链接中使用的路径：书目录名 + 相对书根的路径。"""
        return os.path.join(source_book.name, os.path.relpath(p, source_book))

    # 初始化去重与合并引擎
    dedup_engine = MathMapDedupEngine(vault)

    # ---- Pass 1: Tier1 questions/answers ----
    for root, dirs, files in os.walk(source_book):
        rel_dir = os.path.relpath(root, source_book)
        parts = rel_dir.split(os.sep)
        if "questions" in parts:
            for f in files:
                if not f.endswith(".md") or f.startswith("."):
                    continue
                src = os.path.join(root, f)
                vp = src_vp(src)
                content = Path(src).read_text(encoding="utf-8-sig")
                stem = extract_stem(content)
                matched_q = dedup_engine.match_question(stem)
                
                if matched_q:
                    # 语义认定为完全同一题目（归一化一致），重用既有 Q 节点
                    target_stem = os.path.splitext(matched_q)[0]
                    name_map[vp] = target_stem
                    tier_map[vp] = "questions"
                    q_skipped += 1

                    # 检查候选题目中是否有解析嵌入链接，若有新解析则仅复制解析并挂载回既有 Q 节点
                    ans_links = re.findall(r"!\[\[(Q\d+A\d+)(\.md)?\]\]", content)
                    for ans_stem, _ in ans_links:
                        cand_ans_path = os.path.join(os.path.dirname(src), "answers", f"{ans_stem}.md")
                        if not os.path.exists(cand_ans_path):
                            cand_ans_path = os.path.join(os.path.dirname(os.path.dirname(src)), "answers", f"{ans_stem}.md")
                        if not os.path.exists(cand_ans_path):
                            cand_ans_path = os.path.join(os.path.dirname(os.path.dirname(src)), "答案", f"{ans_stem}.md")
                        
                        if os.path.exists(cand_ans_path):
                            new_ans_stem = f"{target_stem}A_{book_short}"
                            dst_ans_file = a_dest / f"{new_ans_stem}.md"
                            shutil.copy2(cand_ans_path, dst_ans_file)
                            
                            # 链接回既有 Q 节点 (带解析来源标记)
                            existing_q_file = q_dest / matched_q
                            if existing_q_file.is_file():
                                q_text = existing_q_file.read_text(encoding="utf-8-sig")
                                ans_embed = f"![[mathmap/习题/answers/{new_ans_stem}|解析来源：{book_short}]]"
                                if ans_embed not in q_text:
                                    q_text = q_text.rstrip() + f"\n\n{ans_embed}\n"
                                    existing_q_file.write_text(q_text, encoding="utf-8")

                elif f in existing_q:
                    target_stem = os.path.splitext(f)[0]
                    name_map[vp] = target_stem
                    tier_map[vp] = "questions"
                    q_skipped += 1
                else:
                    content = re.sub(r"!\[\[(Q\d+A\d+)(\.md)?\]\]", r"![[mathmap/习题/answers/\1|\1]]", content)
                    (q_dest / f).write_text(content, encoding="utf-8")
                    q_copied += 1
                    target_stem = os.path.splitext(f)[0]
                    name_map[vp] = target_stem
                    tier_map[vp] = "questions"
                    
        if "answers" in parts or "答案" in parts:
            for f in files:
                if not f.endswith(".md") or f.startswith("."):
                    continue
                src = os.path.join(root, f)
                vp = src_vp(src)
                if f in existing_a:
                    a_skipped += 1
                    name_map[vp] = os.path.splitext(f)[0]
                    tier_map[vp] = "answers"
                    continue
                shutil.copy2(src, a_dest / f)
                a_copied += 1
                name_map[vp] = os.path.splitext(f)[0]
                tier_map[vp] = "answers"

    # ---- Pass 2: Tier2/Tier3 与 公式结论 落盘计划 ----
    for root, dirs, files in os.walk(source_book):
        rel_dir = os.path.relpath(root, source_book)
        parts = rel_dir.split(os.sep)
        if "questions" in parts or "answers" in parts or "images" in parts:
            continue
        for f in files:
            if not f.endswith(".md") or f.startswith(".") or f == "index.md":
                continue
            src = os.path.join(root, f)
            section_dir = parts[-2] if len(parts) >= 2 else "章节"
            content = Path(src).read_text(encoding="utf-8-sig")

            # 自动解包与提炼 知识导学/公式/结论 块至 mathmap/公式结论/
            extracted_formulas = extract_and_file_knowledge_guide(src, content, book_short, mathmap, name_map, tier_map)
            if extracted_formulas:
                formula_copied += len(extracted_formulas)

            if is_formula_note(f):
                f_tier = classify_formula_tier(f)
                formula_plans.append((src, f, f_tier, section_dir))
            elif is_paper_tier3(parts, f):
                clean_name = f
                if len(parts) >= 2 and re.search(r"_b\d+\.md$", f):
                    sec_folder = parts[-2] if parts[-1].startswith("刷") else parts[-1]
                    clean_name = f"{sec_folder}_{f}"
                clean_name = re.sub(r"^\d+-", "", clean_name)
                paper_plans.append((src, clean_name, rel_dir))
            elif is_qt_tier2_name(f):
                qt_plans.append((src, f, section_dir))

    # 公式结论落盘
    for src, fname, f_tier, section_dir in formula_plans:
        vp = src_vp(src)
        if f_tier == "公式合集":
            f_dest = formula_col_dest
            existing_f = existing_formula_col
        elif f_tier == "公式整理":
            f_dest = formula_sum_dest
            existing_f = existing_formula_sum
        else:
            f_dest = formula_atomic_dest
            existing_f = existing_formula_atomic

        final_name = safe_dest_name(fname, section_dir, existing_f, formula_used)
        name_map[vp] = os.path.splitext(final_name)[0]
        tier_map[vp] = f_tier
        dst = f_dest / final_name
        if dst.is_file() and dst.read_bytes() == Path(src).read_bytes():
            pass  # 幂等
        else:
            shutil.copy2(src, dst)
        formula_copied += 1

    # Tier3 落盘（不合并，书命名空间隔离）
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

    # Tier2 落盘与严格语义合并
    for src, fname, section_dir in qt_plans:
        vp = src_vp(src)
        matched_qt = dedup_engine.match_problem_type(fname)
        if matched_qt:
            target_file, ratio = matched_qt
            final_name = target_file
            name_map[vp] = os.path.splitext(final_name)[0]
            tier_map[vp] = "题型整理"
            dst = qt_dest / final_name
            # 合并新旧题型中的单题链接
            src_content = Path(src).read_text(encoding="utf-8-sig")
            dst_content = dst.read_text(encoding="utf-8-sig") if dst.is_file() else ""
            new_links = re.findall(r"!\[\[([^\]]+)\]\]", src_content)
            merged_content = dst_content
            for link in new_links:
                if link not in merged_content:
                    merged_content = merged_content.rstrip() + f"\n\n![[{link}]]\n"
            if merged_content != dst_content:
                dst.write_text(merged_content, encoding="utf-8")
        else:
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
    for d, tier in ((qt_dest, "题型整理"), (paper_dest, "题集"), (formula_col_dest, "公式合集"), (formula_sum_dest, "公式整理"), (formula_atomic_dest, "独立公式")):
        if not d.exists():
            continue
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
    for vp in [v for v, t in tier_map.items() if t in ("题型整理", "题集", "公式合集", "公式整理", "独立公式")]:
        tier = tier_map[vp]
        stem = name_map[vp]
        # 从源路径提取所属章节/小节目录（跳过文件名段）
        vp_parts = vp.split(os.sep)
        section = None
        for part in reversed(vp_parts[:-1]):
            if re.match(r"^(\d+(\.\d+)*|课时|专题|专练|第[0-9一二三四五六七八九十]+[节章]|第\d|模块)", part):
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
    parser = argparse.ArgumentParser(description="mathmap 习题三层归档 + 知识点挂载")
    parser.add_argument("vault_root", help="vault 根目录（如 /Users/oven/Documents/ovenmathmap）")
    parser.add_argument("source_book_dir", help="源书 QTG 产物目录（含 01-第一章... 等章节目录）")
    parser.add_argument("book_short", help="书短名，用于冲突文件命名空间与知识点来源分组（如 选择性必修第一册RJA）")
    args = parser.parse_args()
    archive_and_link_mathmap(args.vault_root, args.source_book_dir, args.book_short)
