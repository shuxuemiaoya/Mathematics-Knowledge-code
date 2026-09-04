#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
国家中小学智慧教育平台 (basic.smartedu.cn) 初中数学北师大版全套6册
全量教学资源（习题/教学设计/课件）批量下载与三层归档引擎
"""

import sys, os, json, re, time, random, urllib.request, urllib.parse, argparse
from io import BytesIO
from PIL import Image
from safari_helper import eval_safari

BANK_ID_DEFAULT = "8a2ef0e4-ef7d-4f69-b1c3-1bc81562877e"

BEISHIDA_JUNIOR_MATH_BOOKS = [
    {
        "name": "七年级上册",
        "title": "初中数学北师大版七年级上册",
        "url": "https://basic.smartedu.cn/syncClassroom/prepare?defaultTag=e7bbd21e-0590-11ed-9c79-92fc3b3249d5%2Fff8080814371757b014390f883db0453%2F44bebf7c-54e6-11ed-9c34-850ba61fa9f4%2Fe7bbce2c-0590-11ed-9c79-92fc3b3249d5%2F5136342960%2Fe7bbcf80-0590-11ed-9c79-92fc3b3249d5"
    },
    {
        "name": "七年级下册",
        "title": "初中数学北师大版七年级下册",
        "url": "https://basic.smartedu.cn/syncClassroom/prepare?defaultTag=e7bbd21e-0590-11ed-9c79-92fc3b3249d5%2Fff8080814371757b014390fcdce504bd%2F44bebf7c-54e6-11ed-9c34-850ba61fa9f4%2Fe7bbce2c-0590-11ed-9c79-92fc3b3249d5%2F5136342960%2Fe7bbcf80-0590-11ed-9c79-92fc3b3249d5"
    },
    {
        "name": "八年级上册",
        "title": "初中数学北师大版八年级上册",
        "url": "https://basic.smartedu.cn/syncClassroom/prepare?defaultTag=e7bbd21e-0590-11ed-9c79-92fc3b3249d5%2Fff8080814371757b014390f883db0453%2F44bec67a-54e6-11ed-9c34-850ba61fa9f4%2Fe7bbce2c-0590-11ed-9c79-92fc3b3249d5%2F5136342960%2Fe7bbcf80-0590-11ed-9c79-92fc3b3249d5"
    },
    {
        "name": "八年级下册",
        "title": "初中数学北师大版八年级下册",
        "url": "https://basic.smartedu.cn/syncClassroom/prepare?defaultTag=e7bbd21e-0590-11ed-9c79-92fc3b3249d5%2Fff8080814371757b014390fcdce504bd%2F44bec67a-54e6-11ed-9c34-850ba61fa9f4%2Fe7bbce2c-0590-11ed-9c79-92fc3b3249d5%2F5136342960%2Fe7bbcf80-0590-11ed-9c79-92fc3b3249d5"
    },
    {
        "name": "九年级上册",
        "title": "初中数学北师大版九年级上册",
        "url": "https://basic.smartedu.cn/syncClassroom/prepare?defaultTag=e7bbd21e-0590-11ed-9c79-92fc3b3249d5%2Fff8080814371757b014390f883db0453%2F44bec0c6-54e6-11ed-9c34-850ba61fa9f4%2Fe7bbce2c-0590-11ed-9c79-92fc3b3249d5%2F5136342960%2Fe7bbcf80-0590-11ed-9c79-92fc3b3249d5"
    },
    {
        "name": "九年级下册",
        "title": "初中数学北师大版九年级下册",
        "url": "https://basic.smartedu.cn/syncClassroom/prepare?defaultTag=e7bbd21e-0590-11ed-9c79-92fc3b3249d5%2Fff8080814371757b014390fcdce504bd%2F44bec0c6-54e6-11ed-9c34-850ba61fa9f4%2Fe7bbce2c-0590-11ed-9c79-92fc3b3249d5%2F5136342960%2Fe7bbcf80-0590-11ed-9c79-92fc3b3249d5"
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Referer": "https://basic.smartedu.cn/"
}

def navigate_safari_to_book(url, max_wait=5):
    eval_safari(f'window.location.href = "{url}";')
    time.sleep(max_wait)

def extract_current_book_data():
    js = """
    (function() {
      const treeEl = document.querySelector(".fish-tree");
      if (!treeEl) return JSON.stringify({ error: "no fish-tree" });
      
      const fiberKey = Object.keys(treeEl).find(k => k.startsWith("__reactFiber"));
      let curr = treeEl[fiberKey];
      
      let textBookInfo = null;
      let chapterNodes = null;
      
      while (curr) {
        if (curr.memoizedProps) {
          if (!textBookInfo && curr.memoizedProps.textBookInfo) {
            textBookInfo = curr.memoizedProps.textBookInfo;
          }
          if (!chapterNodes && Array.isArray(curr.memoizedProps.children) && curr.memoizedProps.children.length >= 2) {
            const first = curr.memoizedProps.children[0];
            if (first && first.key && typeof first.key === "string" && first.key.length > 20) {
              chapterNodes = curr.memoizedProps.children;
            }
          }
        }
        curr = curr.return;
      }
      
      if (!textBookInfo) return JSON.stringify({ error: "no textBookInfo" });
      
      function parseNode(node) {
        if (!node) return null;
        const p = node.props || {};
        const d = p.data || {};
        const title = typeof p.title === "string" ? p.title : (d.title || d.name || node.key);
        let sub = [];
        if (Array.isArray(p.children)) {
          sub = p.children.map(parseNode).filter(Boolean);
        }
        return { id: node.key || d.id, title: title, children: sub };
      }
      
      const tree = (chapterNodes || []).map(parseNode).filter(Boolean);
      
      return JSON.stringify({
        detail: textBookInfo.detail || {},
        tree: tree,
        courseList: textBookInfo.courseList || []
      });
    })()
    """
    res = eval_safari(js)
    data = json.loads(res)
    if "error" in data:
        raise RuntimeError(data["error"])
    return data

def build_chapter_id_map(tree):
    id_map = {}
    def walk(node, current_chapter, parent_titles):
        nid = node["id"]
        title = node["title"].strip()
        new_parents = parent_titles + [title]
        if not current_chapter:
            id_map[nid] = {"chapter": title, "title": title, "level": 1}
            for child in node.get("children", []):
                walk(child, title, new_parents)
        else:
            id_map[nid] = {"chapter": current_chapter, "title": title, "parents": parent_titles, "level": len(parent_titles)}
            for child in node.get("children", []):
                walk(child, current_chapter, new_parents)
    for root in tree:
        walk(root, None, [])
    return id_map

def normalize_section_name(matched_node, default_title):
    if not matched_node:
        return default_title
    sec_title = matched_node["title"].strip()
    if not re.match(r"^\d+(\.\d+)+", sec_title):
        for p in reversed(matched_node.get("parents", [])):
            if re.match(r"^\d+(\.\d+)+", p.strip()):
                sec_title = p.strip()
                break
    m = re.match(r"^(\d+(\.\d+)+)(.*)$", sec_title)
    if m:
        num = m.group(1)
        rest = m.group(3).strip()
        return f"{num} {rest}" if rest else num
    return sec_title

def generate_multi_type_plan(book_name, data, bank_id=BANK_ID_DEFAULT):
    tree = data.get("tree", [])
    course_list = data.get("courseList", [])
    id_map = build_chapter_id_map(tree)
    tasks = []
    
    for c in course_list:
        t_code = c.get("resource_type_code")
        title = c.get("title", "").strip()
        
        cid_candidates = []
        if c.get("chapter_ids"):
            cid_candidates.extend(c["chapter_ids"])
        if c.get("chapter_paths"):
            for p in c["chapter_paths"]:
                cid_candidates.extend(p.split("/"))
                
        matched = None
        for cid in reversed(cid_candidates):
            if cid in id_map:
                matched = id_map[cid]
                break
                
        chapter_dir = matched["chapter"].strip() if matched else "未分类大章"
        section_dir = normalize_section_name(matched, title)
        
        # 1. 习题试卷
        if t_code == "examinationpapers":
            filename = f"{title}（答案解析）.pdf"
            encoded_fn = urllib.parse.quote(filename)
            cdn_url = f"https://bdcs-file-2.ykt.cbern.com.cn/xedu_cs_paper_bank/export_papers/nwm/answer/{bank_id}/{c['id']}/{encoded_fn}"
            rel_path = f"{book_name}/{chapter_dir}/{section_dir}/{filename}"
            tasks.append({"type": "exam_pdf", "title": title, "rel_path": rel_path, "url": cdn_url})
            
        # 2. 课件
        elif t_code == "coursewares":
            custom = c.get("custom_properties", {})
            preview = custom.get("preview", {})
            clean_title = re.sub(r"\.(pptx|ppt|pdf)$", "", title, flags=re.I)
            filename = f"{clean_title}_课件.pdf"
            rel_path = f"{book_name}/{chapter_dir}/{section_dir}/{filename}"
            if preview and isinstance(preview, dict):
                tasks.append({"type": "slides_pdf", "title": title, "rel_path": rel_path, "slides": preview})
                
        # 3. 教学设计
        elif t_code == "lesson_plandesign":
            custom = c.get("custom_properties", {})
            preview = custom.get("preview", {})
            clean_title = re.sub(r"\.(docx|doc|pdf)$", "", title, flags=re.I)
            filename = f"{clean_title}_教学设计.pdf"
            rel_path = f"{book_name}/{chapter_dir}/{section_dir}/{filename}"
            if preview and isinstance(preview, dict):
                tasks.append({"type": "slides_pdf", "title": title, "rel_path": rel_path, "slides": preview})
                
    return tasks

def download_task(task, output_dir):
    rel_path = task["rel_path"]
    target_path = os.path.join(output_dir, rel_path)
    if os.path.exists(target_path) and os.path.getsize(target_path) > 10 * 1024:
        return True, "skipped"
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    if task["type"] == "exam_pdf":
        req = urllib.request.Request(task["url"], headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            with open(target_path, "wb") as f:
                f.write(content)
        return True, "downloaded"
        
    elif task["type"] == "slides_pdf":
        slides_dict = task["slides"]
        def slide_key(k):
            m = re.search(r"\d+", k)
            return int(m.group()) if m else 0
        sorted_keys = sorted(slides_dict.keys(), key=slide_key)
        imgs = []
        for sk in sorted_keys:
            s_url = slides_dict[sk]
            req = urllib.request.Request(s_url, headers=HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    im = Image.open(BytesIO(resp.read())).convert("RGB")
                    imgs.append(im)
            except Exception:
                pass
        if imgs:
            imgs[0].save(target_path, save_all=True, append_images=imgs[1:])
            return True, "downloaded"
        else:
            return False, "no images loaded"
            
    return False, "unknown type"

def run_pipeline(output_dir="/Users/oven/Downloads/中小学智慧平台资源/初中/北师大版", book_filter=None):
    print(f"==================================================", flush=True)
    print(f"🌟 启动国家智慧教育平台 初中数学北师大版 全套资源获取流水线", flush=True)
    print(f"📂 保存基准目录: {output_dir}", flush=True)
    print(f"==================================================\n", flush=True)
    
    target_books = BEISHIDA_JUNIOR_MATH_BOOKS
    if book_filter:
        target_books = [b for b in BEISHIDA_JUNIOR_MATH_BOOKS if b["name"] == book_filter or b["title"] == book_filter]
        
    grand_total = 0
    grand_success = 0
    
    for b_idx, book in enumerate(target_books, 1):
        b_name = book["name"]
        print(f"\n📚 [{b_idx}/{len(target_books)}] 正在处理: {book['title']} ({b_name}) ...", flush=True)
        
        print(f"  👉 正在切换 Safari 页面至 {b_name} ...", flush=True)
        navigate_safari_to_book(book["url"])
        
        try:
            data = extract_current_book_data()
        except Exception as e:
            print(f"  ❌ 提取数据失败: {e}，重试一次...", flush=True)
            time.sleep(3)
            data = extract_current_book_data()
            
        tasks = generate_multi_type_plan(b_name, data)
        print(f"  🎯 成功解析到资源总量: {len(tasks)} 份（习题/课件/教学设计）", flush=True)
        
        b_success = 0
        for t_idx, task in enumerate(tasks, 1):
            try:
                ok, action = download_task(task, output_dir)
                if ok:
                    b_success += 1
                    status_icon = "⏩ 已存在" if action == "skipped" else "✅ 完成"
                    print(f"    [{t_idx:3d}/{len(tasks)}] {status_icon} -> {task['rel_path']}", flush=True)
            except Exception as err:
                print(f"    [{t_idx:3d}/{len(tasks)}] ❌ 错误 -> {task['rel_path']} ({err})", flush=True)
            time.sleep(random.uniform(0.2, 0.5))
            
        grand_total += len(tasks)
        grand_success += b_success
        print(f"  🎉 {b_name} 处理完毕！本册成功: {b_success}/{len(tasks)}", flush=True)
        
    print(f"\n==================================================", flush=True)
    print(f"🏆 全套 6 册初中数学北师大版教学资源全部获取完毕！", flush=True)
    print(f"📊 总计成功: {grand_success} / {grand_total}", flush=True)
    print(f"📁 存储根目录: {output_dir}", flush=True)
    print(f"==================================================", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="初中数学北师大版全套6册资源批量获取")
    parser.add_argument("-o", "--output", default="/Users/oven/Downloads/中小学智慧平台资源/初中/北师大版", help="保存根路径")
    parser.add_argument("-b", "--book", default=None, help="仅处理单册（如 七年级上册 / 七年级下册 等）")
    args = parser.parse_args()
    
    run_pipeline(args.output, args.book)
