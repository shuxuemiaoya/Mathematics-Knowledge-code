#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
国家中小学智慧教育平台 (basic.smartedu.cn) 高中数学人教A版全套5册
全量同步练习题库批量抓取与归档引擎：
- 涵盖：必修第一册、必修第二册、选择性必修第一册、选择性必修第二册、选择性必修第三册
- 自动化控制 Safari 切换册次、展开目录树并提取真实题目、LaTeX公式、标准答案、名师解析
- 100% 本地化提取原画 1080P MP4 解析微课视频并与题目双链关联
- 支持断点续传与秒级幂等跳过
"""

import os, sys, time, argparse
from safari_helper import eval_safari
from adapters.exercise_bank_adapter import ExerciseBankAdapter

HIGH_SCHOOL_VOLUMES = [
    "必修 第一册",
    "必修 第二册",
    "选择性必修 第一册",
    "选择性必修 第二册",
    "选择性必修 第三册"
]

def main():
    parser = argparse.ArgumentParser(description="高中数学人教A版同步练习题库批量获取引擎")
    parser.add_argument("-v", "--volume", default="all", help="指定册次，如 '必修 第一册'、'必修第二册'、'current'（仅当前页面）或 'all' (默认全套5册)")
    parser.add_argument("-o", "--output", default="/Users/oven/Downloads/中小学智慧平台资源/习题库", help="输出基准目录")
    args = parser.parse_args()

    adapter = ExerciseBankAdapter()

    # 1. 如果仅抓取当前 Safari 页面打开的册次
    if args.volume.lower() == "current":
        version, grade_vol = adapter.get_book_meta_from_page()
        if not version or not grade_vol:
            version = "人教A版"
            grade_vol = "必修第一册"
        vol_out_dir = os.path.join(args.output, version, grade_vol)
        print(f"📖 正在处理当前已打开册次: 【{version} {grade_vol}】 -> {vol_out_dir}")
        adapter.run(vol_out_dir)
        return

    # 2. 确定需要处理的册次列表
    target_vols = []
    if args.volume == "all":
        target_vols = HIGH_SCHOOL_VOLUMES
    else:
        req_parts = [p.strip() for p in args.volume.split(",") if p.strip()]
        for req in req_parts:
            req_norm = req.replace(" ", "")
            matched = False
            # 优先完全精确匹配（去除空格后完全相等）
            for v in HIGH_SCHOOL_VOLUMES:
                if req_norm == v.replace(" ", ""):
                    if v not in target_vols:
                        target_vols.append(v)
                    matched = True
                    break
            if not matched:
                for v in HIGH_SCHOOL_VOLUMES:
                    if req_norm in v.replace(" ", ""):
                        if v not in target_vols:
                            target_vols.append(v)
                        break
        if not target_vols:
            print(f"❌ 未识别的册次: {args.volume}，可选: {HIGH_SCHOOL_VOLUMES}")
            sys.exit(1)

    print("=" * 60, flush=True)
    print("📚 高中数学人教A版全套同步练习题库批量抓取引擎", flush=True)
    print(f"🎯 待处理册次总数: {len(target_vols)} 本 ({', '.join(target_vols)})", flush=True)
    print(f"📂 存储基础路径: {args.output}", flush=True)
    print("=" * 60 + "\n", flush=True)

    for idx, vol in enumerate(target_vols, 1):
        vol_clean = vol.replace(" ", "")
        vol_out_dir = os.path.join(args.output, "人教A版", vol_clean)
        print(f"\n[{idx:2d}/{len(target_vols)}] 🚀 准备处理册次: 【人教A版 {vol}】 ...", flush=True)
        
        # 检查 Safari 当前页面是否已经是该册次
        curr_tag = eval_safari('(() => { const el = document.querySelector(".index-module_selected-tag_8J1Eb"); return el ? el.innerText : ""; })()')
        if vol not in curr_tag and vol_clean not in curr_tag.replace(" ", ""):
            print(f"    🔄 正在控制 Safari 切换至: {vol} ...", flush=True)
            ok = adapter.switch_volume(vol)
            if not ok:
                print(f"    ⚠️ 切换册次可能未成功或超时，继续尝试提取...", flush=True)
            time.sleep(2.0)
        else:
            print(f"    ✅ Safari 当前已处于: {vol}", flush=True)

        adapter.run(vol_out_dir)
        print(f"[{idx:2d}/{len(target_vols)}] 🎉 册次完成: 【人教A版 {vol}】\n", flush=True)
        time.sleep(2.0)

    print("\n" + "=" * 60, flush=True)
    print("🏆 高中数学人教A版指定册次题库获取全部完成！", flush=True)
    print(f"📂 成果保存在: {args.output}/人教A版", flush=True)
    print("=" * 60, flush=True)

if __name__ == "__main__":
    main()
