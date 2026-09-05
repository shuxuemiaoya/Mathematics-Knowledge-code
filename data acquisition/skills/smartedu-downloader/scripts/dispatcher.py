#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data Acquisition Agent 统一智能调度分发中心 (Dispatcher)
自动识别浏览器当前网页类型，智能路由至对应的资源获取适配器
"""

import sys, os, argparse
from safari_helper import eval_safari
from adapters.prepare_adapter import PrepareMaterialAdapter
from adapters.exercise_bank_adapter import ExerciseBankAdapter

ADAPTER_REGISTRY = [
    PrepareMaterialAdapter(),
    ExerciseBankAdapter()
]

def detect_and_dispatch(output_dir=None, adapter_name=None):
    # 1. 如果显式指定了适配器
    if adapter_name == "exercise" or adapter_name == "mypaper":
        selected_adapter = ExerciseBankAdapter()
    elif adapter_name == "prepare":
        selected_adapter = PrepareMaterialAdapter()
    else:
        # 2. 自动探查 Safari 当前 URL
        current_url = eval_safari("window.location.href")
        print(f"🌐 当前 Safari 前台 URL: {current_url}")
        
        selected_adapter = None
        for ad in ADAPTER_REGISTRY:
            if ad.match(current_url):
                selected_adapter = ad
                break
                
        if not selected_adapter:
            raise RuntimeError(f"未找到适配当前网页的抓取策略: {current_url}，请确认已打开智慧平台备课页或习题库页面！")

    print(f"🚀 自动匹配策略适配器: 【{selected_adapter.__class__.__name__}】")
    
    # 默认输出路径智能推断
    if not output_dir:
        if isinstance(selected_adapter, ExerciseBankAdapter):
            output_dir = "/Users/oven/Downloads/中小学智慧平台资源/习题库/北师大版/七年级上册"
        else:
            output_dir = "/Users/oven/Downloads/中小学智慧平台资源"

    selected_adapter.run(output_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Acquisition 统一智能调度入口")
    parser.add_argument("-o", "--output", default=None, help="自定义保存目录")
    parser.add_argument("-a", "--adapter", default=None, choices=["prepare", "exercise"], help="显式指定适配器")
    args = parser.parse_args()
    
    detect_and_dispatch(args.output, args.adapter)
