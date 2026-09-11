# -*- coding: utf-8 -*-
"""
Baidu Pan Helper CLI & Generator
为 Agent 快速生成 Chrome DevTools evaluate_script 的执行脚本，以及解析分享元数据。
"""

import re
import json
import argparse
from typing import Dict, Any, List

def extract_share_info(share_url: str) -> Dict[str, str]:
    """从分享 URL 提取 share key 和提取码"""
    pwd_match = re.search(r"pwd=([a-zA-Z0-9]{4})", share_url)
    pwd = pwd_match.group(1) if pwd_match else ""
    
    key_match = re.search(r"/s/1?([a-zA-Z0-9_\-]+)", share_url)
    surl = key_match.group(1) if key_match else ""
    
    return {
        "url": share_url,
        "surl": surl,
        "pwd": pwd
    }

def generate_transfer_js(fs_ids: List[int], target_path: str = "/数学妙呀/未分类") -> str:
    """生成一键批量转存的 JS 代码字符串 (用于 DevTools evaluate_script)"""
    fs_list_json = json.dumps(fs_ids)
    return f"""async () => {{
  const shareid = window.yunData.shareid;
  const from = window.yunData.share_uk;
  const bdstoken = window.yunData.bdstoken;
  const bdclnd = (document.cookie.match(/BDCLND=([^;]+)/) || [])[1];
  const sekey = decodeURIComponent(bdclnd || '');

  const fsids = {fs_list_json};
  const results = [];
  const url = `/share/transfer?shareid=${{shareid}}&from=${{from}}&bdstoken=${{bdstoken}}&channel=chunlei&clienttype=0&web=1&app_id=250528`;

  for (const fid of fsids) {{
    const formData = new URLSearchParams();
    formData.append('fsidlist', JSON.stringify([fid]));
    formData.append('path', '{target_path}');
    if (sekey) {{
      formData.append('sekey', sekey);
    }}

    try {{
      const res = await fetch(url, {{
        method: 'POST',
        headers: {{
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          'X-Requested-With': 'XMLHttpRequest'
        }},
        body: formData.toString()
      }}).then(r => r.json());
      results.push({{ fs_id: fid, errno: res.errno, msg: res.show_msg || res.errno }});
    }} catch (e) {{
      results.push({{ fs_id: fid, error: e.message }});
    }}
  }}
  return results;
}}"""

def generate_organize_js(filelist: List[Dict[str, str]]) -> str:
    """生成移动归类文件的 JS 代码"""
    payload = json.dumps(filelist, ensure_ascii=False)
    return f"""async () => {{
  const bdstoken = window.locals.userInfo.bdstoken;
  const filelist = {payload};
  const form = new URLSearchParams();
  form.append('filelist', JSON.stringify(filelist));

  const res = await fetch(`/api/filemanager?opera=move&bdstoken=${{bdstoken}}&channel=chunlei&web=1&app_id=250528&clienttype=0`, {{
    method: 'POST',
    headers: {{
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'X-Requested-With': 'XMLHttpRequest'
    }},
    body: form.toString()
  }}).then(r => r.json()).catch(e => ({{ error: e.message }}));

  return res;
}}"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baidu Pan Assistant")
    parser.add_argument("--url", type=str, help="Baidu Pan share URL")
    args = parser.parse_args()
    if args.url:
        print(json.dumps(extract_share_info(args.url), ensure_ascii=False, indent=2))
