# -*- coding: utf-8 -*-
"""
Aria2 RPC Dispatcher
将下载任务批量派发给本地 Aria2 服务或直接以多线程模式调用 aria2c 命令。
"""

import json
import urllib.request
import argparse
import subprocess
import shutil
from typing import List, Dict, Any, Optional

DEFAULT_RPC_URL = "http://127.0.0.1:6800/jsonrpc"

def send_rpc_task(
    url: str,
    output_dir: str,
    filename: str,
    cookie: str = "",
    rpc_url: str = DEFAULT_RPC_URL,
    rpc_token: str = ""
) -> Dict[str, Any]:
    """通过 JSON-RPC 向 Aria2 提交下载任务"""
    headers = ["User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"]
    if cookie:
        headers.append(f"Cookie: {cookie}")

    options = {
        "dir": output_dir,
        "out": filename,
        "header": headers,
        "split": "16",
        "max-connection-per-server": "16",
        "continue": "true"
    }

    params = [[url], options]
    if rpc_token:
        params.insert(0, f"token:{rpc_token}")

    payload = {
        "jsonrpc": "2.0",
        "id": "antigravity",
        "method": "aria2.addUri",
        "params": params
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(rpc_url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def download_via_cli(url: str, output_dir: str, filename: str, cookie: str = "") -> bool:
    """直接调用系统已安装的 aria2c 命令行"""
    if not shutil.which("aria2c"):
        print("系统未检测到 aria2c 命令，请先通过 brew install aria2 安装。")
        return False

    cmd = [
        "aria2c",
        "-s", "16",
        "-x", "16",
        "-d", output_dir,
        "-o", filename,
        "-c"
    ]
    if cookie:
        cmd.extend(["--header", f"Cookie: {cookie}"])
    cmd.append(url)

    proc = subprocess.run(cmd)
    return proc.returncode == 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aria2 Task Dispatcher")
    parser.add_argument("--url", required=True, help="Download URL")
    parser.add_argument("--dir", required=True, help="Target directory")
    parser.add_argument("--out", required=True, help="Target file name")
    parser.add_argument("--cookie", default="", help="Cookie string")
    parser.add_argument("--mode", choices=["rpc", "cli"], default="rpc", help="Dispatch mode")
    args = parser.parse_args()

    if args.mode == "rpc":
        res = send_rpc_task(args.url, args.dir, args.out, cookie=args.cookie)
        print("RPC Result:", res)
    else:
        success = download_via_cli(args.url, args.dir, args.out, cookie=args.cookie)
        print("CLI Result:", success)
