# -*- coding: utf-8 -*-
"""
Quark Pan Helper CLI & URL Parser
提取夸克网盘分享链接的 pwd_id 与提取码，并辅助生成自动化操作参数。
"""

import re
import json
import argparse
from typing import Dict, Any

def extract_quark_share_info(share_url: str) -> Dict[str, str]:
    """从夸克分享 URL 提取 pwd_id 与 passcode"""
    # 典型格式: https://pan.quark.cn/s/c527e0fa1234?pwd=abcd 或 https://pan.quark.cn/s/c527e0fa1234
    pwd_match = re.search(r"[?&]pwd=([a-zA-Z0-9]+)", share_url)
    passcode = pwd_match.group(1) if pwd_match else ""

    id_match = re.search(r"/s/([a-zA-Z0-9]+)", share_url)
    pwd_id = id_match.group(1) if id_match else ""

    return {
        "url": share_url,
        "pwd_id": pwd_id,
        "passcode": passcode
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quark Pan Assistant")
    parser.add_argument("--url", type=str, help="Quark Pan share URL")
    args = parser.parse_args()
    if args.url:
        print(json.dumps(extract_quark_share_info(args.url), ensure_ascii=False, indent=2))
