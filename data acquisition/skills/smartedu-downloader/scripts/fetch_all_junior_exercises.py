#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
国家中小学智慧教育平台 (basic.smartedu.cn) 初中数学全套同步练习题库批量抓取引擎
涵盖：北师大版 & 人教版（七、八、九年级 全册）
功能：
1. 智能匹配平台真实有习题的教材体系（新教材 / 旧教材）
2. 自动控制 Safari 进行册次切换与页面就绪校验
3. 逐章逐节提取题目、LaTeX 公式、标准答案、知识点及主讲名师
4. 100% 本地化下载原画 1080P MP4 微课讲解视频并归档至同级 videos/ 目录
5. 自动在小节 Markdown 中渲染 Obsidian HTML5 播放器 ( ![[videos/...]] ) 与本地播放链接
6. 完全幂等与断点续传：已抓取完成的小节和视频自动秒级跳过，永不重复下载
"""

import os, sys, time, json, argparse
from safari_helper import eval_safari
from adapters.exercise_bank_adapter import ExerciseBankAdapter

CHUZHONG_TAG = "e7bbce2c-0590-11ed-9c79-92fc3b3249d5"
SHUXUE_TAG = "e7bbcf80-0590-11ed-9c79-92fc3b3249d5"

BOOKS_CATALOG = [
    # ─── 北师大版 ───────────────────────────────────────────────────────────
    {
        "edition": "北师大版",
        "grade": "七年级",
        "volume": "上册",
        "curriculum": "新教材",
        "curriculum_tag": "5136342961",
        "edition_tag": "e7bbd21e-0590-11ed-9c79-92fc3b3249d5",
        "grade_tag": "44bebf7c-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390f883db0453",
    },
    {
        "edition": "北师大版",
        "grade": "七年级",
        "volume": "下册",
        "curriculum": "新教材",
        "curriculum_tag": "5136342961",
        "edition_tag": "e7bbd21e-0590-11ed-9c79-92fc3b3249d5",
        "grade_tag": "44bebf7c-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390fcdce504bd",
    },
    {
        "edition": "北师大版",
        "grade": "八年级",
        "volume": "上册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "e7bbd21e-0590-11ed-9c79-92fc3b3249d5",
        "grade_tag": "44bec67a-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390f883db0453",
    },
    {
        "edition": "北师大版",
        "grade": "八年级",
        "volume": "下册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "e7bbd21e-0590-11ed-9c79-92fc3b3249d5",
        "grade_tag": "44bec67a-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390fcdce504bd",
    },
    {
        "edition": "北师大版",
        "grade": "九年级",
        "volume": "上册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "e7bbd21e-0590-11ed-9c79-92fc3b3249d5",
        "grade_tag": "44bec0c6-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390f883db0453",
    },
    {
        "edition": "北师大版",
        "grade": "九年级",
        "volume": "下册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "e7bbd21e-0590-11ed-9c79-92fc3b3249d5",
        "grade_tag": "44bec0c6-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390fcdce504bd",
    },
    # ─── 人教版 ───────────────────────────────────────────────────────────
    {
        "edition": "人教版",
        "grade": "七年级",
        "volume": "上册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "ff8080814371757b01437c363a187b0a",
        "grade_tag": "44bebf7c-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390f883db0453",
    },
    {
        "edition": "人教版",
        "grade": "七年级",
        "volume": "下册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "ff8080814371757b01437c363a187b0a",
        "grade_tag": "44bebf7c-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390fcdce504bd",
    },
    {
        "edition": "人教版",
        "grade": "八年级",
        "volume": "上册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "ff8080814371757b01437c363a187b0a",
        "grade_tag": "44bec67a-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390f883db0453",
    },
    {
        "edition": "人教版",
        "grade": "八年级",
        "volume": "下册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "ff8080814371757b01437c363a187b0a",
        "grade_tag": "44bec67a-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390fcdce504bd",
    },
    {
        "edition": "人教版",
        "grade": "九年级",
        "volume": "上册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "ff8080814371757b01437c363a187b0a",
        "grade_tag": "44bec0c6-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390f883db0453",
    },
    {
        "edition": "人教版",
        "grade": "九年级",
        "volume": "下册",
        "curriculum": "旧教材",
        "curriculum_tag": "5136342960",
        "edition_tag": "ff8080814371757b01437c363a187b0a",
        "grade_tag": "44bec0c6-54e6-11ed-9c34-850ba61fa9f4",
        "volume_tag": "ff8080814371757b014390fcdce504bd",
    }
]

def build_mypaper_url(book: dict) -> str:
    tags = [
        CHUZHONG_TAG,
        SHUXUE_TAG,
        book["edition_tag"],
        book["grade_tag"],
        book["volume_tag"],
        book["curriculum_tag"]
    ]
    tag_params = "&".join([f"tagIds={t}" for t in tags])
    return f"https://basic.smartedu.cn/myPaper?_maf_show_navigationbar=false&mode=2&subject=math&{tag_params}"

def navigate_and_wait(url: str, max_wait: int = 6):
    eval_safari(f"window.location.href = \"{url}\";")
    for _ in range(max_wait * 2):
        time.sleep(0.5)
        check_js = r"""
        (() => {
          const treeEl = document.querySelector(".fish-tree");
          return Boolean(treeEl && treeEl.children.length > 0);
        })()
        """
        try:
            ready = eval_safari(check_js)
            if ready == "true":
                time.sleep(1.0)
                return True
        except Exception:
            pass
    return False

def main():
    parser = argparse.ArgumentParser(description="初中数学（北师大版 & 人教版）七八九年级同步练习全量批量抓取引擎")
    parser.add_argument("-e", "--edition", choices=["all", "beishida", "renjiao"], default="all", help="指定教材版本 (默认 all)")
    parser.add_argument("-g", "--grade", choices=["all", "7", "8", "9"], default="all", help="指定年级 (7/8/9/all)")
    parser.add_argument("-v", "--volume", choices=["all", "up", "down"], default="all", help="指定册次 (up/down/all)")
    parser.add_argument("-o", "--output", default="/Users/oven/Downloads/中小学智慧平台资源/习题库/初中", help="输出根目录")
    args = parser.parse_args()

    target_books = []
    for b in BOOKS_CATALOG:
        if args.edition == "beishida" and b["edition"] != "北师大版":
            continue
        if args.edition == "renjiao" and b["edition"] != "人教版":
            continue
        if args.grade == "7" and b["grade"] != "七年级":
            continue
        if args.grade == "8" and b["grade"] != "八年级":
            continue
        if args.grade == "9" and b["grade"] != "九年级":
            continue
        if args.volume == "up" and b["volume"] != "上册":
            continue
        if args.volume == "down" and b["volume"] != "下册":
            continue
        target_books.append(b)

    print("=" * 60, flush=True)
    print("📚 初中数学全套同步练习题库批量抓取引擎 (微课视频 1080P 本地化版)", flush=True)
    print(f"🎯 待处理册次总数: {len(target_books)} 本", flush=True)
    print(f"📂 存储基础路径: {args.output}", flush=True)
    print("=" * 60 + "\n", flush=True)

    adapter = ExerciseBankAdapter()
    overall_books_count = len(target_books)

    for idx, book in enumerate(target_books, 1):
        ed = book["edition"]
        gr = book["grade"]
        vol = book["volume"]
        curr = book["curriculum"]
        book_title = f"{ed} {gr}{vol} ({curr})"
        book_out_dir = os.path.join(args.output, ed, f"{gr}{vol}")

        print(f"\n[{idx:2d}/{overall_books_count}] 🚀 正在载入册次: 【{book_title}】 ...", flush=True)
        url = build_mypaper_url(book)
        ok = navigate_and_wait(url)
        if not ok:
            print("    ⚠️ 页面加载超时或目录树未渲染，尝试继续提取...", flush=True)

        time.sleep(1.0)
        adapter.run(book_out_dir)
        print(f"[{idx:2d}/{overall_books_count}] 🎉 册次完成: 【{book_title}】\n", flush=True)
        time.sleep(2.0)

    print("\n" + "=" * 60, flush=True)
    print("🏆 全部指定初中数学教材册次抓取与微课视频提取完成！", flush=True)
    print(f"📂 成果保存在: {args.output}", flush=True)
    print("=" * 60, flush=True)

if __name__ == "__main__":
    main()
