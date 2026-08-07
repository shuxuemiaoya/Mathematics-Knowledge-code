import os
import re
import shutil
import subprocess
from pathlib import Path

VAULT = Path("/Users/oven/Documents/ovenmathmap")
BOOK_SHORT = "选择性必修第一册RJA"          # 新书短名，用于冲突文件命名空间
SOURCE_BOOK = VAULT / "课堂同步/教辅/必刷题/2026版 必刷题 数学选择性必修第一册RJA"

MATHMAP = VAULT / "mathmap"
Q_DEST = MATHMAP / "习题/questions"
A_DEST = MATHMAP / "习题/answers"
QT_DEST = MATHMAP / "习题/题型整理"
PAPER_DEST = MATHMAP / "习题/题集"


def clean_title(name: str) -> str:
    """去掉 _bN 后缀，用于链接显示名。"""
    return re.sub(r"_b\d+$", "", name)


def link_target_stem(link_path: str) -> str:
    """从 ![[...]] 链接中提取目标文件名（含 .md 去后缀）。"""
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
    """生成无冲突的目标文件名。

    优先用原名；冲突时用 「小节目录名_原名」；再冲突则加书短名前缀。
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


def rewrite_links(content: str, name_map, tier_map) -> str:
    """把笔记内的 ![[...]] 链接按目标文件重写为 mathmap 路径。

    name_map: 源文件全路径(相对 vault，含 .md) -> mathmap 目标文件名(去扩展名)
    tier_map: 源文件全路径 -> "questions"|"题型整理"|"题集"|"answers"
    优先按全路径匹配；Q 单题按 basename 匹配。
    """

    def repl(match):
        link_path = match.group(1)
        # 规范化：去掉前导 ./ 与书目录前缀差异
        norm = link_path.lstrip("./")
        if norm in name_map:
            target = name_map[norm]
            tier = tier_map.get(norm, "题型整理")
            return f"![[mathmap/习题/{tier}/{target}|{clean_title(target)}]]"
        # 直接 Q 链接：优先 questions / answers
        stem = link_target_stem(link_path)
        if re.match(r"^Q\d+$", stem):
            return f"![[mathmap/习题/questions/{stem}|{stem}]]"
        if re.match(r"^Q\d+A\d+$", stem):
            return f"![[mathmap/习题/answers/{stem}|{stem}]]"
        # 未知：保持原链接（避免破坏）
        return match.group(0)

    return re.sub(r"!\[\[([^\]]+)\]\]", repl, content)


# ---- 知识点挂载 ----
KP_DIR = MATHMAP / "知识点"

# 小节目录名 -> 知识点节点名（手工精确映射；自动匹配不上的都在这）
SECTION_KP_MAP = {
    # 第一章 空间向量与立体几何
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
    # 第二章 直线和圆的方程
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
    # 第三章 圆锥曲线的方程
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
    # 章检测/强化
    "第一章素养检测": "第一章 空间向量与立体几何",
    "第一章高考强化": "第一章 空间向量与立体几何",
    "第二章素养检测": "第二章 直线和圆的方程",
    "第二章高考强化": "第二章 直线和圆的方程",
    "第三章素养检测": "第三章 圆锥曲线的方程",
    "第三章高考强化": "第三章 圆锥曲线的方程",
    # 高考新题型
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


def kp_for_section(section: str):
    """小节目录名/章目录名 -> 知识点节点名。"""
    if section in SECTION_KP_MAP:
        return SECTION_KP_MAP[section]
    if section in CHAPTER_KP_MAP:
        return CHAPTER_KP_MAP[section]
    # 精确匹配：小节名 == 知识点名（去编号前缀）
    s = re.sub(r"^\d+(\.\d+)*_", "", section)
    if (KP_DIR / f"{s}.md").is_file():
        return s
    # 模糊：知识点名是小节名的子串
    for kp in os.listdir(KP_DIR):
        if kp.endswith(".md"):
            kp_stem = os.path.splitext(kp)[0]
            if len(kp_stem) >= 3 and (kp_stem in s or s in kp_stem):
                return kp_stem
    return None


def mount_kp(kp: str, tier: str, stem: str, src_vp: str) -> bool:
    """把 (tier, stem) 挂载到知识点节点 kp 的 # 题型 章节，并回写反向链接。

    返回 True 表示本次新增挂载。
    """
    kp_path = KP_DIR / f"{kp}.md"
    if not kp_path.is_file():
        print(f"  !! 知识点节点缺失: {kp}")
        return False
    text = kp_path.read_text(encoding="utf-8-sig")
    embed = f"![[mathmap/习题/{tier}/{stem}|{clean_title(stem)}]]"
    if embed in text:
        return False
    source_heading = f"## 来源：{BOOK_SHORT}"

    if "# 题型" not in text:
        text = text.rstrip() + "\n\n# 题型\n"
    q_idx = text.find("# 题型")
    q_part = text[q_idx:]
    if source_heading in q_part:
        # 追加到已有来源分组内（分组末尾）
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


def main():
    for d in (Q_DEST, A_DEST, QT_DEST, PAPER_DEST):
        d.mkdir(parents=True, exist_ok=True)

    # existing_* 只统计 git 已跟踪（旧书）文件 —— 本轮新创建的不计入，
    # 保证 safe_dest_name 对相同源文件始终给出相同目标名（幂等）。
    def tracked_in(d: Path):
        out = subprocess.run(
            ["git", "-C", str(VAULT), "-c", "core.quotepath=false", "ls-files", str(d)],
            capture_output=True, text=True,
        ).stdout
        return {os.path.basename(p) for p in out.splitlines() if p}

    existing_qt = tracked_in(QT_DEST)
    existing_paper = tracked_in(PAPER_DEST)
    existing_q = tracked_in(Q_DEST)
    existing_a = tracked_in(A_DEST)

    q_copied = a_copied = qt_copied = paper_copied = 0
    q_skipped = a_skipped = 0

    # 第一遍扫描：收集新书所有 .md 源文件（去重名）
    # 收集 Tier2 的「小节目录名」用于冲突前缀
    tier2_used: set = set()
    tier3_used: set = set()
    name_map: dict = {}   # 源文件全路径(相对 vault) -> mathmap stem
    tier_map: dict = {}

    def vault_rel(p: str) -> str:
        """链接中使用的路径：书目录名 + 相对书根的路径。

        源笔记里的 ![[...]] 链接以书目录名开头（如
        '2026版 必刷题 数学选择性必修第一册RJA/01-.../刷基础_b1.md'），
        而非完整 vault 路径（'课堂同步/教辅/...'）。
        """
        rel = os.path.relpath(p, SOURCE_BOOK)
        return os.path.join(SOURCE_BOOK.name, rel)

    # 先复制 Tier1 questions/answers（文件名唯一，无冲突）
    for root, dirs, files in os.walk(SOURCE_BOOK):
        rel_dir = os.path.relpath(root, SOURCE_BOOK)
        parts = rel_dir.split(os.sep)
        if "questions" in parts:
            for f in files:
                if f.endswith(".md") and not f.startswith("."):
                    src = os.path.join(root, f)
                    dst = Q_DEST / f
                    if f in existing_q:
                        q_skipped += 1
                        continue
                    content = Path(src).read_text(encoding="utf-8-sig")
                    # 重写答案嵌入
                    content = re.sub(
                        r"!\[\[(Q\d+A\d+)(\.md)?\]\]",
                        r"![[mathmap/习题/answers/\1|\1]]",
                        content,
                    )
                    dst.write_text(content, encoding="utf-8")
                    q_copied += 1
                    name_map[vault_rel(src)] = os.path.splitext(f)[0]
                    tier_map[vault_rel(src)] = "questions"
        if "answers" in parts or "答案" in parts:
            for f in files:
                if f.endswith(".md") and not f.startswith("."):
                    src = os.path.join(root, f)
                    dst = A_DEST / f
                    if f in existing_a:
                        a_skipped += 1
                        continue
                    shutil.copy2(src, dst)
                    a_copied += 1
                    name_map[vault_rel(src)] = os.path.splitext(f)[0]
                    tier_map[vault_rel(src)] = "answers"

    # 第二遍：Tier2 题型整理 + Tier3 题集
    # 先计算 Tier3 的 clean_name（可能带小节前缀），再决定 Tier2 命名，
    # 以便 Tier2 的冲突前缀能引用到正确的小节目录。
    paper_plans = []   # (src, clean_name, rel_dir)
    qt_plans = []      # (src, fname, section_dir)

    for root, dirs, files in os.walk(SOURCE_BOOK):
        rel_dir = os.path.relpath(root, SOURCE_BOOK)
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

    # Tier3 先落盘（同名冲突加前缀），记录最终 stem
    # name_map 键 = 源文件全路径(相对 vault) —— 链接里引用的就是它
    for src, clean_name, rel_dir in paper_plans:
        base = clean_name
        vp = vault_rel(src)
        final_name = base
        if base in existing_paper or base in tier3_used:
            final_name = f"{BOOK_SHORT}_{base}"
            n = 2
            while final_name in existing_paper or final_name in tier3_used:
                final_name = f"{BOOK_SHORT}_{n}_{base}"
                n += 1
        tier3_used.add(final_name)
        content = Path(src).read_text(encoding="utf-8-sig")
        name_map[vp] = os.path.splitext(final_name)[0]
        tier_map[vp] = "题集"
        dst = PAPER_DEST / final_name
        if dst.is_file() and dst.read_text(encoding="utf-8-sig") == content:
            pass  # 幂等：内容相同则跳过写入
        else:
            dst.write_text(content, encoding="utf-8")
        paper_copied += 1

    # Tier2 落盘：冲突时用「小节目录名_原名」，再冲突加书短名
    for src, fname, section_dir in qt_plans:
        vp = vault_rel(src)
        stem = os.path.splitext(fname)[0]
        final_name = safe_dest_name(fname, section_dir, existing_qt, tier2_used)
        name_map[vp] = os.path.splitext(final_name)[0]
        tier_map[vp] = "题型整理"
        dst = QT_DEST / final_name
        if dst.is_file():
            src_content = Path(src).read_bytes()
            if dst.read_bytes() == src_content:
                pass  # 幂等：内容相同则跳过写入
            else:
                shutil.copy2(src, dst)
        else:
            shutil.copy2(src, dst)
        qt_copied += 1

    # 第三遍：统一重写所有已落盘笔记的链接（依据 name_map / tier_map）
    # 需要把 mathmap 落盘文件里的链接重写为 mathmap 相对路径。
    # Tier2 与 Tier3 里链接指向的源文件名 stem 都在 name_map 中（Q 链接除外）。
    for d, tier in ((QT_DEST, "题型整理"), (PAPER_DEST, "题集")):
        for f in os.listdir(d):
            if not f.endswith(".md"):
                continue
            p = d / f
            # 只重写本次新写入的文件（通过 mtime 判断不可靠，重写全部也无害——
            # 但已有旧文件链接已是 mathmap 形式，重写后仍保持 mathmap 形式）
            content = p.read_text(encoding="utf-8-sig")
            new_content = rewrite_links(content, name_map, tier_map)
            if new_content != content:
                p.write_text(new_content, encoding="utf-8")

    print(f"Tier 1: 原始题目归档 (mathmap/习题/questions): {q_copied} 个 (跳过已存在 {q_skipped})")
    print(f"Tier 1: 原始解析归档 (mathmap/习题/answers): {a_copied} 个 (跳过已存在 {a_skipped})")
    print(f"Tier 2: 题型整理归档 (mathmap/习题/题型整理): {qt_copied} 个")
    print(f"Tier 3: 题集总集归档 (mathmap/习题/题集): {paper_copied} 个")

    # ---- 第四遍：知识点挂载 ----
    # 每个新归档的题型整理/题集节点 -> 挂载到 mathmap/知识点 对应节点的 # 题型 章节。
    # 反向：同时给题型/题集笔记写入到知识点的链接（双向）。
    mount_qt = [vp for vp, tier in tier_map.items() if tier == "题型整理"]
    mount_paper = [vp for vp, tier in tier_map.items() if tier == "题集"]
    kp_mounted, kp_skipped = 0, 0
    for vp in mount_qt + mount_paper:
        tier = tier_map[vp]
        stem = name_map[vp]
        # 从源路径提取所属章节/小节目录：第一个含编号/课时/专题/章检测的路径段
        vp_parts = vp.split(os.sep)
        section = None
        for part in reversed(vp_parts[:-1]):  # 跳过文件名段
            if re.match(r"^(\d+(\.\d+)*|课时|专题|专练|第\d|模块|第一章|第二章|第三章)", part):
                section = part
                break
        if section is None:
            section = vp_parts[0]
        kp = kp_for_section(section)
        if kp is None:
            print(f"  !! 未匹配知识点: {vp} (section={section})")
            continue
        if mount_kp(kp, tier, stem, vp):
            kp_mounted += 1
        else:
            kp_skipped += 1
    print(f"知识点挂载: 新增 {kp_mounted}, 跳过已存在 {kp_skipped}")


if __name__ == "__main__":
    main()
