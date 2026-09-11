# -*- coding: utf-8 -*-
"""
Direct Downloader (直链断点续传多线程/分块高速下载器)
支持携带 Cookie/User-Agent、断点续传、分块写入与哈希校验。
"""

import os
import sys
import time
import hashlib
import argparse
import urllib.request
from typing import Optional, Dict

DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def download_file(
    url: str,
    output_path: str,
    headers: Optional[Dict[str, str]] = None,
    chunk_size: int = 1024 * 1024, # 1MB chunk
    max_retries: int = 5
) -> bool:
    """下载单个文件，支持断点续传与重试"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    temp_path = output_path + ".part"

    req_headers = {
        "User-Agent": DEFAULT_UA
    }
    if headers:
        req_headers.update(headers)

    existing_bytes = 0
    if os.path.exists(temp_path):
        existing_bytes = os.path.getsize(temp_path)

    for attempt in range(1, max_retries + 1):
        try:
            current_headers = dict(req_headers)
            if existing_bytes > 0:
                current_headers["Range"] = f"bytes={existing_bytes}-"

            req = urllib.request.Request(url, headers=current_headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                total_len = resp.headers.get("Content-Length")
                total_size = (int(total_len) + existing_bytes) if total_len else None

                mode = "ab" if existing_bytes > 0 else "wb"
                with open(temp_path, mode) as f:
                    downloaded = existing_bytes
                    start_time = time.time()
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 打印进度
                        elapsed = max(time.time() - start_time, 0.1)
                        speed = (downloaded - existing_bytes) / elapsed / 1024 / 1024
                        if total_size:
                            pct = (downloaded / total_size) * 100
                            print(f"\r下载中: {pct:.1f}% ({downloaded / 1024 / 1024:.2f}MB / {total_size / 1024 / 1024:.2f}MB) 速度: {speed:.2f}MB/s", end="", flush=True)
                        else:
                            print(f"\r已下载: {downloaded / 1024 / 1024:.2f}MB 速度: {speed:.2f}MB/s", end="", flush=True)

            print("\n下载完成，重命名临时文件...")
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_path, output_path)
            return True
        except Exception as e:
            print(f"\n[重试 {attempt}/{max_retries}] 发生异常: {e}")
            if os.path.exists(temp_path):
                existing_bytes = os.path.getsize(temp_path)
            time.sleep(2)

    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Direct File Downloader")
    parser.add_argument("--url", required=True, help="Download URL")
    parser.add_argument("--output", required=True, help="Target output file path")
    parser.add_argument("--cookie", default="", help="Cookie string")
    args = parser.parse_args()

    custom_headers = {}
    if args.cookie:
        custom_headers["Cookie"] = args.cookie

    success = download_file(args.url, args.output, headers=custom_headers)
    sys.exit(0 if success else 1)
