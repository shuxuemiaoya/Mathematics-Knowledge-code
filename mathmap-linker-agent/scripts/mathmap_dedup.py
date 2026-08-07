#!/usr/bin/env python3
"""mathmap 多层级语义去重与合并引擎 (mathmap-dedup).

支持功能：
  1. Tier 1 (questions/ answers/):
     - 结构化与公式归一化：格式/空格/LaTeX表达变体（如 \\frac 与 /，\\le 与 \\leq）视为同一题目，
       复用已存在的 Q*.md 节点，并将新解析关联为 Q*A2.md。
     - 极微小差异单字符敏感：若题干措辞、数值或符号差异达 1 个字符，严格认定为不同题目，保留独立 Q*.md。
  2. Tier 2 (题型整理/):
     - 严格语义匹配：同小节/知识点下，题型名称与考法意图高度相似时进行合并。
     - 链接求并集：合并后将新题型的独有单题链接 ![[Q...]] 嵌入已有题型笔记中，重写上层引用。
  3. Tier 3 (题集/):
     - 不合并（书名命名空间隔离）：套卷/检测/综合训练按书短名前缀隔离，保留独立性。
  4. 知识点挂载 (知识点/):
     - 宽泛归类映射：多层级匹配（手工表 -> 精确归一 -> 子串模糊 -> 语义同义词），确保题型挂载到既有知识点笔记。
"""
import argparse
import json
import os
import re
import difflib
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set


def normalize_latex(text: str) -> str:
    """归一化 LaTeX 公式表达与空白格式。"""
    # 替换常见的 LaTeX 命令变体
    text = re.sub(r"\\dfrac", r"\\frac", text)
    text = re.sub(r"\\tfrac", r"\\frac", text)
    text = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\(([0-9a-zA-Z]+)\)/\(([0-9a-zA-Z]+)\)", r"\1/\2", text)
    text = re.sub(r"\\vec\s*\{?([a-zA-Z0-9]+)\}?", r"vec(\1)", text)

    text = re.sub(r"\\leq", r"\\le", text)
    text = re.sub(r"\\geq", r"\\ge", text)
    text = re.sub(r"\\neq", r"\\ne", text)
    text = re.sub(r"\\times", r"*", text)
    text = re.sub(r"\\cdot", r"*", text)
    # 规范化空格与标点
    text = re.sub(r"\s+", "", text)
    text = text.replace("，", ",").replace("；", ";").replace("：", ":").replace("（", "(").replace("）", ")")
    return text



def extract_stem(content: str) -> str:
    """提取题目 md 的题干核心文本（移除答案嵌入、说明与格式标记）。"""
    # 去除解析嵌入 ![[...]]
    text = re.sub(r"!\[\[[^\]]+\]\]", "", content)
    # 去除 H1-H3 标题
    text = re.sub(r"^#+\s+.*$", "", text, flags=re.MULTILINE)
    # 去除 Markdown 加粗/斜体
    text = re.sub(r"\*\*|\*", "", text)
    return text.strip()


def compare_stems(stem1: str, stem2: str) -> Tuple[bool, float]:
    """比对两个题干文本。
    
    返回 (is_same_question, similarity_ratio)
    规则：
      - 若归一化后 100% 相同 -> 同一题目 (True, 1.0)
      - 若归一化后存在任何文字/数字/符号差异 -> 认为不同题目 (False, ratio)
    """
    norm1 = normalize_latex(stem1)
    norm2 = normalize_latex(stem2)
    if norm1 == norm2:
        return True, 1.0
    
    matcher = difflib.SequenceMatcher(None, norm1, norm2)
    ratio = matcher.ratio()
    return False, ratio


def clean_qt_title(title: str) -> str:
    """清理题型名称中的前缀编号、噪音修饰词与 _bN 后缀。"""
    title = os.path.splitext(title)[0]
    title = re.sub(r"_b\d+$", "", title)
    title = re.sub(r"^(题型|考点|专题|刷基础|刷提升|刷易错|刷难关|刷素养|刷能力|刷速度|刷真题|刷综合)\s*\d*[\._\s]*", "", title)
    title = re.sub(r"(整理|总结|微专题|探究|拓展|辨析)$", "", title)
    return title.strip()



def compare_qt_titles(title1: str, title2: str) -> Tuple[bool, float]:
    """比对两个题型整理标题。
    
    规则：严格语义比对，相似度大于 0.85 或核心名称一致判定为同一题型。
    """
    c1 = clean_qt_title(title1)
    c2 = clean_qt_title(title2)
    if c1 == c2 and len(c1) > 0:
        return True, 1.0
    
    if len(c1) == 0 or len(c2) == 0:
        return False, 0.0
        
    matcher = difflib.SequenceMatcher(None, c1, c2)
    ratio = matcher.ratio()
    norm1 = normalize_latex(c1)
    norm2 = normalize_latex(c2)
    if (len(norm1) >= 4 and norm1 in norm2) or (len(norm2) >= 4 and norm2 in norm1):
        return True, max(ratio, 0.9)
        
    if ratio >= 0.85:
        return True, ratio
    return False, ratio


class MathMapDedupEngine:
    """MathMap 知识库去重与合并分析引擎。"""

    def __init__(self, vault_root: Path):
        self.vault_root = vault_root
        self.mathmap = vault_root / "mathmap"
        self.q_dest = self.mathmap / "习题/questions"
        self.a_dest = self.mathmap / "习题/answers"
        self.qt_dest = self.mathmap / "习题/题型整理"
        self.paper_dest = self.mathmap / "习题/题集"
        self.kp_dir = self.mathmap / "知识点"
        
        self.existing_q_index: Dict[str, Tuple[str, str]] = {}  # norm_stem -> (file_name, original_content)
        self.existing_qt_index: Dict[str, str] = {}  # file_name -> original_content
        self._build_indexes()

    def _build_indexes(self):
        """构建既有题库的归一化索引。"""
        if self.q_dest.is_dir():
            for p in self.q_dest.glob("*.md"):
                try:
                    content = p.read_text(encoding="utf-8-sig")
                    stem = extract_stem(content)
                    norm = normalize_latex(stem)
                    self.existing_q_index[norm] = (p.name, content)
                except Exception:
                    pass
                
        if self.qt_dest.is_dir():
            for p in self.qt_dest.glob("*.md"):
                try:
                    content = p.read_text(encoding="utf-8-sig")
                    self.existing_qt_index[p.name] = content
                except Exception:
                    pass

    def match_question(self, candidate_stem: str) -> Optional[str]:
        """匹配单题。若归一化一致返回既有 Q*.md 文件名，否则返回 None。"""
        norm = normalize_latex(candidate_stem)
        if norm in self.existing_q_index:
            return self.existing_q_index[norm][0]
        return None

    def match_problem_type(self, candidate_name: str) -> Optional[Tuple[str, float]]:
        """匹配既有题型整理节点。若高度相似返回 (target_filename, ratio)。"""
        for exist_name in self.existing_qt_index.keys():
            is_match, ratio = compare_qt_titles(candidate_name, exist_name)
            if is_match:
                return exist_name, ratio
        return None

    def generate_dedup_plan(self, source_book_dir: Path, book_short: str) -> dict:
        """针对新书扫描并生成完整去重与合并计划。"""
        plan = {
            "book_short": book_short,
            "question_matches": {},     # candidate_rel_path -> existing_Q_name
            "qt_merges": {},            # candidate_qt_path -> { "target": exist_qt_name, "extra_links": [...] }
            "paper_isolated": [],       # candidate_paper_path
        }

        for root, dirs, files in os.walk(source_book_dir):
            rel_dir = os.path.relpath(root, source_book_dir)
            parts = rel_dir.split(os.sep)
            if "questions" in parts:
                for f in files:
                    if not f.endswith(".md") or f.startswith("."):
                        continue
                    src_p = os.path.join(root, f)
                    rel_p = os.path.relpath(src_p, source_book_dir)
                    content = Path(src_p).read_text(encoding="utf-8-sig")
                    stem = extract_stem(content)
                    matched_q = self.match_question(stem)
                    if matched_q:
                        plan["question_matches"][rel_p] = matched_q

            if not any(k in parts for k in ("questions", "answers", "images")):
                for f in files:
                    if not f.endswith(".md") or f.startswith(".") or f == "index.md":
                        continue
                    src_p = os.path.join(root, f)
                    rel_p = os.path.relpath(src_p, source_book_dir)
                    
                    from link_to_mathmap import is_qt_tier2_name, is_paper_tier3
                    if is_paper_tier3(parts, f):
                        plan["paper_isolated"].append(rel_p)
                    elif is_qt_tier2_name(f):
                        matched_qt = self.match_problem_type(f)
                        if matched_qt:
                            target_file, ratio = matched_qt
                            content = Path(src_p).read_text(encoding="utf-8-sig")
                            links = re.findall(r"!\[\[([^\]]+)\]\]", content)
                            plan["qt_merges"][rel_p] = {
                                "target": target_file,
                                "similarity": ratio,
                                "candidate_links": links
                            }

        return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MathMap 多层级语义去重与合并引擎")
    parser.add_argument("vault_root", help="vault 根目录")
    parser.add_argument("source_book_dir", help="源书目录")
    parser.add_argument("book_short", help="书短名")
    parser.add_argument("--out", help="输出 JSON 计划文件路径", default=None)
    args = parser.parse_args()

    engine = MathMapDedupEngine(Path(args.vault_root))
    plan = engine.generate_dedup_plan(Path(args.source_book_dir), args.book_short)
    
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"去重计划已保存至: {args.out}")
    else:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
