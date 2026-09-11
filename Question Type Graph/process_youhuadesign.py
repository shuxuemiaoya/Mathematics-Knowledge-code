#!/usr/bin/env python3
"""Batch processor for 《优化设计》(高中数学全套5册) into Obsidian Question Type Graphs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SOURCE_BASE = Path("/Volumes/Whw/数学妙呀资料/高中/课堂同步/教辅/优化设计")
VAULT_ROOT = Path("/Users/oven/Documents/ovenmathmap")
GRAPH_BASE = VAULT_ROOT / "高中" / "课堂同步" / "教辅" / "优化设计"
REGISTRY_PATH = VAULT_ROOT / ".question-type-graph" / "question-id-registry.json"

BOOKS_CONFIG = [
    {
        "id": 1,
        "src_folder": "2026高中同步测控优化设计数学必修第一册配人教A版增强版全国",
        "target_title": "2026版 高中同步测控优化设计 数学 必修第一册",
        "short_title": "必修第一册",
    },
    {
        "id": 2,
        "src_folder": "2026高中同步测控优化设计数学必修第二册配人教A版增强版全国",
        "target_title": "2026版 高中同步测控优化设计 数学 必修第二册",
        "short_title": "必修第二册",
    },
    {
        "id": 3,
        "src_folder": "2026高中同步测控优化设计数学选择性必修第一册配人教A版增强版全国",
        "target_title": "2026版 高中同步测控优化设计 数学 选择性必修第一册",
        "short_title": "选择性必修第一册",
    },
    {
        "id": 4,
        "src_folder": "2026高中同步测控优化设计数学选择性必修第二册配人教A版增强版全国",
        "target_title": "2026版 高中同步测控优化设计 数学 选择性必修第二册",
        "short_title": "选择性必修第二册",
    },
    {
        "id": 5,
        "src_folder": "2026高中同步测控优化设计数学选择性必修第三册配人教A版增强版全国",
        "target_title": "2026版 高中同步测控优化设计 数学 选择性必修第三册",
        "short_title": "选择性必修第三册",
    },
]

NUM_TO_CN = {
    1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
    6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
    11: "十一", 12: "十二"
}
CN_TO_NUM = {v: k for k, v in NUM_TO_CN.items()}

CHAPTER_NAMES_BY_BOOK = {
    1: {1: "集合与常用逻辑用语", 2: "一元二次函数_方程和不等式", 3: "函数的概念与性质", 4: "指数函数与对数函数", 5: "三角函数"},
    2: {6: "平面向量及其应用", 7: "复数", 8: "立体几何初步", 9: "统计", 10: "概率"},
    3: {1: "空间向量与立体几何", 2: "直线和圆的方程", 3: "圆锥曲线的方程"},
    4: {4: "数列", 5: "一元函数的导数及其应用"},
    5: {6: "计数原理", 7: "随机变量及其分布", 8: "成对数据的统计分析"},
}

SPECIAL_CHAPTERS_ORDER = {
    1: {"复习课": "06-复习课", "全书综合测评": "07-全书综合测评"},
    2: {"复习课": "11-复习课", "全书综合测评": "12-全书综合测评"},
    3: {"复习课": "04-复习课", "全书综合测评": "05-全书综合测评"},
    4: {"复习课": "06-复习课", "全书综合测评": "07-全书综合测评"},
    5: {"复习课": "09-复习课", "全书综合测评": "10-全书综合测评"},
}


def safe_name(text: str, max_len: int = 31) -> str:
    """Sanitize title for cross-platform files and directories (Windows MAX_PATH safe)."""
    text = text.replace(":", "_").replace("：", "_")
    text = text.replace("/", "_").replace("\\", "_")
    text = text.replace("*", "_").replace("?", "_")
    text = text.replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
    text = text.replace("\u3000", "_").replace("  ", "_").replace(" ", "_")
    text = re.sub(r"_+", "_", text).strip("._ ")
    if len(text) > max_len:
        text = text[:max_len].rstrip("._ ")
    return text


def load_registry() -> dict[str, Any]:
    if REGISTRY_PATH.is_file():
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "schema_version": 1,
        "next_number": 1,
        "assignments": {}
    }


def save_registry(registry: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = REGISTRY_PATH.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, REGISTRY_PATH)


class QIDAllocator:
    def __init__(self):
        self.registry = load_registry()
        self.assignments = self.registry.setdefault("assignments", {})
        self.used_codes = set(self.assignments.values())
        self.next_number = max(int(self.registry.get("next_number", 1)), 1)
        self.dirty = False

    def allocate(self, identity: str) -> str:
        if identity in self.assignments:
            return self.assignments[identity]
        while f"Q{self.next_number:08d}" in self.used_codes:
            self.next_number += 1
        code = f"Q{self.next_number:08d}"
        self.next_number += 1
        self.assignments[identity] = code
        self.used_codes.add(code)
        self.dirty = True
        return code

    def commit(self):
        if self.dirty:
            self.registry["next_number"] = self.next_number
            save_registry(self.registry)
            self.dirty = False


def clean_markdown_text(text: str) -> str:
    """Normalize pandoc markdown quirks into standard clean Obsidian LaTeX."""
    # 1. Remove pandoc image attributes: {width="..." height="..."}
    text = re.sub(r'\{width="[^"]*"[^}]*\}', '', text)
    # 2. Fix variable superscripts: e.g. *a*^2^ -> $a^2$, *x*^2^ -> $x^2$
    text = re.sub(r'\*([a-zA-Z0-9]+)\*\^([0-9a-zA-Z+-]+)\^', r'$\1^{\2}$', text)
    # 3. Fix math subscripts: e.g. *x*~1~ -> $x_1$
    text = re.sub(r'\*([a-zA-Z0-9]+)\*~([0-9a-zA-Z+-]+)~', r'$\1_{\2}$', text)
    # 4. Clean bold italic numbers: **1***.* -> 1.
    text = re.sub(r'\*\*(\d{1,2})\*\*\*?\.\*?', r'\1. ', text)
    # 5. Fix underline placeholders: [　　　　　]{.underline} -> `______`
    text = re.sub(r'\[\s*[\u3000\s_]*\s*\]\{\.underline\}', '______', text)
    # 6. Normalize standalone single italic variables: *x* -> $x$
    text = re.sub(r'(?<![a-zA-Z0-9$\\])\*([a-zA-Z])\*(?![a-zA-Z0-9$\\])', r'$\1$', text)
    return text


def parse_pandoc_markdown(md_text: str) -> list[dict[str, Any]]:
    """Parse converted markdown lines into groups and questions."""
    lines = md_text.splitlines()
    q_start_re = re.compile(r"^(?:\*{0,2}(\d{1,2})\*{0,2}[\s*]*[、.．*]+[\s*]*)(.*)$")
    pat_head = re.compile(r"^(?:\*{0,2}\d+\*{0,2}[\s*]*[、.．*]+[\s*]*)+\d+")
    ans_re = re.compile(r"^(?:答案|【答案】)[:：\s]*(.*)$")
    fenxi_re = re.compile(r"^(?:【?(?:思路)?分析】?|分析)[:：\s]*(.*)$")
    analysis_re = re.compile(r"^(?:解析|【解析】|解)[:：\s]*(.*)$")
    zongjie_re = re.compile(r"^(?:【?(?:总结|题后反思|规律方法|反思感悟|方法规律)】?|总结|题后反思|规律方法)[:：\s]*(.*)$")
    group_re = re.compile(r"^(?:[一二三四五六七八九十]+[、.．\s]*)?([ABＡＢ]组.*)$")

    groups: list[dict[str, Any]] = []
    cur_group: dict[str, Any] = {"name": "默认", "questions": []}
    cur_q: dict[str, Any] | None = None

    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue

        # Ignore section number headings like 1.1.1 or **1**.**1**.**1** or 课后训练巩固提升
        if pat_head.match(line_s) or "课后训练" in line_s or "巩固提升" in line_s:
            continue

        m_grp = group_re.match(line_s)
        if m_grp:
            if cur_q:
                cur_group["questions"].append(cur_q)
                cur_q = None
            if cur_group["questions"]:
                groups.append(cur_group)
            grp_name = m_grp.group(1).replace("Ａ", "A").replace("Ｂ", "B").strip()
            cur_group = {"name": grp_name, "questions": []}
            continue

        m_q = q_start_re.match(line_s)
        if m_q and (cur_q is None or cur_q.get("state") in ["ans", "analysis", "fenxi", "zongjie"]):
            if cur_q:
                cur_group["questions"].append(cur_q)
            cur_q = {
                "num": int(m_q.group(1)),
                "stem": [m_q.group(2)],
                "answer": "",
                "fenxi": [],
                "analysis": [],
                "zongjie": [],
                "state": "stem"
            }
            continue

        if cur_q is not None:
            m_ans = ans_re.match(line_s)
            m_fenxi = fenxi_re.match(line_s)
            m_ana = analysis_re.match(line_s)
            m_zongjie = zongjie_re.match(line_s)

            if m_ans:
                cur_q["answer"] = m_ans.group(1)
                cur_q["state"] = "ans"
            elif m_fenxi:
                if m_fenxi.group(1):
                    cur_q["fenxi"].append(m_fenxi.group(1))
                cur_q["state"] = "fenxi"
            elif m_ana:
                if m_ana.group(1):
                    cur_q["analysis"].append(m_ana.group(1))
                cur_q["state"] = "analysis"
            elif m_zongjie:
                if m_zongjie.group(1):
                    cur_q["zongjie"].append(m_zongjie.group(1))
                cur_q["state"] = "zongjie"
            elif cur_q["state"] == "stem":
                cur_q["stem"].append(line_s)
            elif cur_q["state"] == "fenxi":
                cur_q["fenxi"].append(line_s)
            elif cur_q["state"] == "analysis":
                cur_q["analysis"].append(line_s)
            elif cur_q["state"] == "zongjie":
                cur_q["zongjie"].append(line_s)

    if cur_q:
        cur_group["questions"].append(cur_q)
    if cur_group["questions"]:
        groups.append(cur_group)

    return groups


def classify_question(stem_text: str, ans_text: str) -> str:
    """Infer question type: 单选题, 多选题, 填空题, 解答题."""
    if "(多选题)" in stem_text or "（多选题）" in stem_text or "多项符合" in stem_text:
        return "多选题"
    has_options = bool(re.search(r"\b[A-D][.．、\s]", stem_text) or re.search(r"A\..*B\.", stem_text))
    if has_options:
        if len(ans_text.strip()) > 1 and ans_text.strip().isalpha() and len(ans_text.strip()) <= 4:
            return "多选题"
        return "单选题"
    if "______" in stem_text or "填空" in stem_text or (ans_text.strip() and len(ans_text.strip()) <= 20 and "\n" not in ans_text):
        return "填空题"
    return "解答题"


def resolve_chapter(file_rel: str, book_id: int) -> tuple[str, str]:
    """Return (chapter_dir_name, chapter_title) for a given relative path."""
    filename = Path(file_rel).name
    parent = Path(file_rel).parent.name

    if "综合测评" in filename:
        return "全书综合测评", "全书综合测评"
    if "复习课" in parent or ("复习课" in filename and not re.search(r"第[0-9一二三四五六七八九十]+章", filename)):
        return "复习课", "复习课"

    target_str = parent if parent else filename
    m = re.search(r"第?([0-9]+|[一二三四五六七八九十]+)章", target_str)
    if not m:
        m = re.search(r"第?([0-9]+|[一二三四五六七八九十]+)章", filename)

    if m:
        val = m.group(1)
        num = int(val) if val.isdigit() else CN_TO_NUM.get(val, 1)
        cn = NUM_TO_CN.get(num, str(num))
        title = CHAPTER_NAMES_BY_BOOK.get(book_id, {}).get(num, "")
        if title:
            return f"第{cn}章_{title}", f"第{cn}章 {title}"
        return f"第{cn}章", f"第{cn}章"

    return "其他", "其他"


def process_lesson_docx(
    docx_path: Path,
    dest_lesson_dir: Path,
    book_config: dict[str, Any],
    chapter_title: str,
    allocator: QIDAllocator,
    vault_root: Path,
) -> dict[str, Any]:
    """Process a single docx lesson file into Obsidian question/answer notes."""
    lesson_title = docx_path.stem.strip()
    dest_lesson_dir.mkdir(parents=True, exist_ok=True)
    images_dir = dest_lesson_dir / "images"
    questions_dir = dest_lesson_dir / "questions"
    answers_dir = questions_dir / "answers"
    questions_dir.mkdir(parents=True, exist_ok=True)
    answers_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "pandoc",
            str(docx_path),
            "-f", "docx",
            "-t", "markdown-simple_tables-multiline_tables-grid_tables",
            "--wrap=none",
            f"--extract-media={tmpdir}",
            "-o", f"{tmpdir}/out.md"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"  [ERROR] Pandoc failed on {docx_path.name}: {res.stderr}")
            return {"status": "error", "error": res.stderr}

        with open(f"{tmpdir}/out.md", "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Copy extracted media to dest_lesson_dir/images
        media_src_dir = Path(tmpdir) / "media"
        if media_src_dir.is_dir():
            images_dir.mkdir(parents=True, exist_ok=True)
            for img_file in media_src_dir.iterdir():
                if img_file.is_file():
                    shutil.copy2(img_file, images_dir / img_file.name)

    # Clean markdown
    cleaned_text = clean_markdown_text(raw_text)

    # Rewrite media paths from /tmp/.../media/imageX.ext to images/imageX.ext
    cleaned_text = re.sub(r'!\[([^\]]*)\]\([^)]*?/media/([^)]+)\)', r'![\1](images/\2)', cleaned_text)

    # Parse groups and questions
    groups = parse_pandoc_markdown(cleaned_text)

    has_multi_groups = len(groups) > 1 and any("组" in g["name"] for g in groups)
    lesson_qids: list[str] = []
    total_questions = 0

    group_nodes: list[dict[str, Any]] = []

    for g in groups:
        grp_name = g["name"]
        grp_safe = safe_name(grp_name, max_len=31)
        grp_qids: list[str] = []

        if has_multi_groups:
            target_grp_dir = dest_lesson_dir / grp_safe
            target_q_dir = target_grp_dir / "questions"
            target_ans_dir = target_q_dir / "answers"
            target_q_dir.mkdir(parents=True, exist_ok=True)
            target_ans_dir.mkdir(parents=True, exist_ok=True)
        else:
            target_grp_dir = dest_lesson_dir
            target_q_dir = questions_dir
            target_ans_dir = answers_dir

        for q in g["questions"]:
            q_num = q["num"]
            stem_body = "\n".join(q["stem"]).strip()
            # rewrite images relative to question note if in subfolder
            if has_multi_groups:
                stem_body = stem_body.replace("(images/", "(../images/")

            ans_text = q["answer"].strip()
            fenxi_text = "\n".join(q.get("fenxi", [])).strip()
            ana_text = "\n".join(q["analysis"]).strip()
            zongjie_text = "\n".join(q.get("zongjie", [])).strip()
            if has_multi_groups:
                if fenxi_text:
                    fenxi_text = fenxi_text.replace("(images/", "(../../images/")
                ana_text = ana_text.replace("(images/", "(../../images/")
                if zongjie_text:
                    zongjie_text = zongjie_text.replace("(images/", "(../../images/")

            q_type = classify_question(stem_body, ans_text)

            # Generate stable identity
            identity_str = f"{book_config['target_title']}:{chapter_title}:{lesson_title}:{grp_name}:{q_num}"
            identity = hashlib.sha256(identity_str.encode("utf-8")).hexdigest()
            qid = allocator.allocate(identity)
            grp_qids.append(qid)
            lesson_qids.append(qid)
            total_questions += 1

            # Determine vault-relative answer path (without .md)
            ans_rel_path = (target_ans_dir / f"{qid}A1").relative_to(vault_root)

            # Write Question Note
            q_file = target_q_dir / f"{qid}.md"
            q_content = f"""---
question_id: "{qid}"
question_number: "{q_num}"
question_type: "{q_type}"
context_key: "{safe_name(chapter_title)}:{safe_name(lesson_title)}:{grp_safe}"
source_book: "{book_config['target_title']}"
chapter: "{chapter_title}"
lesson: "{lesson_title}"
tier: "{grp_name}"
answer_status: "matched"
---
<!-- question-source:start -->
{q_num}. {stem_body}
<!-- question-source:end -->

![[{ans_rel_path}]]
"""
            q_file.write_text(q_content, encoding="utf-8")

            # Write Answer Note
            ans_file = target_ans_dir / f"{qid}A1.md"
            ans_display = ans_text or "详见解析"
            ana_display = ana_text or "略"

            ans_json = json.dumps(ans_display, ensure_ascii=False)
            ans_body_lines = [
                "---",
                f'answer_id: "{qid}A1"',
                f'question_id: "{qid}"',
                f'target_question: "{qid}"',
                f'short_answer: {ans_json}',
                'confidence: "HIGH"',
                "---",
                "> [!success]- 优化设计",
                f"> > [!success] **【答案】** {ans_display}",
            ]

            if fenxi_text:
                ans_body_lines.extend([">", "> > [!note]- **【分析】**"])
                for fl in fenxi_text.splitlines():
                    ans_body_lines.append(f"> > {fl}" if fl else "> >")

            ans_body_lines.extend([">", "> > [!note]- **【解析】**"])
            for al in ana_display.splitlines():
                ans_body_lines.append(f"> > {al}" if al else "> >")

            if zongjie_text:
                ans_body_lines.extend([">", "> > [!tip]- **【总结】**"])
                for zl in zongjie_text.splitlines():
                    ans_body_lines.append(f"> > {zl}" if zl else "> >")

            ans_file.write_text("\n".join(ans_body_lines) + "\n", encoding="utf-8")

        if has_multi_groups:
            # Write group note embedding its questions (without .md)
            grp_note = target_grp_dir / f"{grp_safe}.md"
            embeds = "\n".join(f"![[{(target_q_dir / qid).relative_to(vault_root)}]]" for qid in grp_qids)
            grp_content = f"{embeds}\n"
            grp_note.write_text(grp_content, encoding="utf-8")
            group_nodes.append({
                "name": grp_name,
                "note_path": target_grp_dir / grp_safe,
                "q_count": len(grp_qids)
            })

    # Write Lesson Note embedding groups or questions (without .md)
    lesson_note = dest_lesson_dir / f"{safe_name(lesson_title, max_len=31)}.md"
    if has_multi_groups:
        lesson_embed_blocks = []
        for g in group_nodes:
            lesson_embed_blocks.append(f"## {g['name']}\n![[{(g['note_path']).relative_to(vault_root)}]]\n")
        lesson_content = "\n".join(lesson_embed_blocks).strip() + "\n"
    else:
        lesson_embeds = "\n".join(f"![[{(questions_dir / qid).relative_to(vault_root)}]]" for qid in lesson_qids)
        lesson_content = f"{lesson_embeds}\n"

    lesson_note.write_text(lesson_content, encoding="utf-8")

    return {
        "status": "ok",
        "lesson_title": lesson_title,
        "lesson_note_stem": dest_lesson_dir / safe_name(lesson_title, max_len=31),
        "question_count": total_questions,
        "groups_count": len(groups)
    }


def process_book(book_config: dict[str, Any]):
    print(f"\n==================================================")
    print(f"Processing: {book_config['target_title']}")
    print(f"==================================================")

    src_book_dir = SOURCE_BASE / book_config["src_folder"]
    if not src_book_dir.is_dir():
        print(f"[ERROR] Source folder not found: {src_book_dir}")
        return

    dest_book_dir = GRAPH_BASE / book_config["target_title"]
    dest_book_dir.mkdir(parents=True, exist_ok=True)

    allocator = QIDAllocator()

    # Find all docx in 课后习题
    docx_files: list[Path] = []
    exercise_root = None
    for item in src_book_dir.iterdir():
        if item.is_dir() and "课后" in item.name:
            exercise_root = item
            break

    if not exercise_root:
        print(f"[ERROR] 课后习题 directory not found in {src_book_dir}")
        return

    for root, dirs, files in os.walk(exercise_root):
        for f in sorted(files):
            if f.endswith(".docx") and not f.startswith("~$") and f != "目录.docx":
                docx_files.append(Path(root) / f)

    print(f"Found {len(docx_files)} docx exercise files in {exercise_root.name}.")

    # Group files by chapter
    chapters: dict[str, list[Path]] = {}
    for df in docx_files:
        rel = df.relative_to(exercise_root)
        c_dir_name, c_title = resolve_chapter(str(rel), book_config["id"])
        chapters.setdefault(c_dir_name, []).append(df)

    chapter_notes: list[tuple[str, Path]] = []
    total_book_questions = 0

    for c_dir_name in sorted(chapters.keys()):
        c_files = chapters[c_dir_name]
        c_title = c_dir_name.split("-", 1)[-1].replace("_", " ")
        c_dest_dir = dest_book_dir / safe_name(c_dir_name, max_len=31)
        c_dest_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n--- Chapter: {c_dir_name} ({len(c_files)} lessons) ---")
        lesson_note_stems: list[tuple[str, Path]] = []
        for df in c_files:
            lesson_slug = safe_name(df.stem, max_len=31)
            dest_lesson_dir = c_dest_dir / lesson_slug
            res = process_lesson_docx(
                docx_path=df,
                dest_lesson_dir=dest_lesson_dir,
                book_config=book_config,
                chapter_title=c_title,
                allocator=allocator,
                vault_root=VAULT_ROOT,
            )
            if res.get("status") == "ok":
                lesson_note_stems.append((res["lesson_title"], res["lesson_note_stem"]))
                total_book_questions += res["question_count"]
                print(f"  Processed {df.name} -> {res['question_count']} questions")

        # Write Chapter Note (with lesson headings before embeds)
        c_note = c_dest_dir / f"{safe_name(c_dir_name, max_len=31)}.md"
        c_embeds_list = []
        for l_title, ln in lesson_note_stems:
            c_embeds_list.append(f"## {l_title}\n![[{ln.relative_to(VAULT_ROOT)}]]\n")
        c_embeds = "\n".join(c_embeds_list).strip()
        c_content = f"{c_embeds}\n"
        c_note.write_text(c_content, encoding="utf-8")
        chapter_notes.append((c_title, c_dest_dir / safe_name(c_dir_name, max_len=31)))

    # Write Book Index Note (without .md in embeds)
    index_note = dest_book_dir / "index.md"
    index_embeds = "\n".join(f"![[{cn.relative_to(VAULT_ROOT)}]]" for _, cn in chapter_notes)
    index_content = f"""# {book_config['target_title']}

{index_embeds}
"""
    index_note.write_text(index_content, encoding="utf-8")

    # Commit registry updates
    allocator.commit()

    print(f"\n>>> Successfully finished {book_config['target_title']}:")
    print(f"    Chapters: {len(chapters)}")
    print(f"    Lessons: {len(docx_files)}")
    print(f"    Questions: {total_book_questions}")
    print(f"    Index Note: {index_note}")


def main():
    parser = argparse.ArgumentParser(description="Process 优化设计 series into Question Type Graph")
    parser.add_argument("--book", type=int, choices=[1, 2, 3, 4, 5], help="Book index to process (1..5)")
    parser.add_argument("--all", action="store_true", help="Process all 5 books")
    args = parser.parse_args()

    if args.all:
        for b in BOOKS_CONFIG:
            process_book(b)
    elif args.book:
        target = next(b for b in BOOKS_CONFIG if b["id"] == args.book)
        process_book(target)
    else:
        print("No specific book specified. Processing all 5 books in sequence...")
        for b in BOOKS_CONFIG:
            process_book(b)


if __name__ == "__main__":
    main()
