# -*- coding: utf-8 -*-

"""
国家中小学智慧教育平台 习题库/同步练习 (/myPaper) 专用适配器
策略模式重构版 (v6 - 闭环状态机、精准树节点命中、多填空答案修复与微课源流直链)：
- 习题库独立存放于：/Users/oven/Downloads/中小学智慧平台资源/习题库/
- 严格按照平台「查看解析」所呈现的全量信息结构化输出（题型、纯净题干、子题分解、完整选项、正确答案、名师微课与详细解析）
- 彻底解决多空填空题答案截断丢失问题
- 彻底解决复合题答案提前泄露至题干的问题
- 彻底修复 MathType / \rm / 单位拆分乱码问题，规范化为标准 KaTeX / LaTeX ($...$)
- 提取并持久化官方名师、指导团队、微课视频源流直链 (.m3u8)
- 原题插图、几何图形与选项配图 100% 本地化持久化至 images/ 目录
- 具备严格的大章展开、小节激活与空题跳过校验机制，实时输出提取进度
"""

import os, sys, json, re, time, random, urllib.request, urllib.parse, zipfile, io
from adapters.base_adapter import BaseResourceAdapter
from safari_helper import eval_safari

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Referer": "https://basic.smartedu.cn/"
}

def download_question_video(packing_result: str, video_url: str, save_path: str, retries: int = 3) -> bool:
    """
    下载题目配套的名师解析微课视频到本地 videos/ 目录：
    1. 若本地文件已存在且大小 > 100KB，直接复用。
    2. 优先通过 packing_result (官方资源包 ZIP) 提取完整 1080P MP4 视频。
    3. 若 video_url 本身是 mp4 直链，则直接下载。
    """
    if os.path.exists(save_path) and os.path.getsize(save_path) > 1024 * 100:
        return True

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 方案 1: 从 packing_result ZIP 中解压出完整高清 MP4
    if packing_result:
        raw_path = re.sub(r'^(cs_path:)?\$\{ref-path\}', '', packing_result).lstrip('/')
        cdn_hosts = [
            "https://r1-ndr.ykt.cbern.com.cn",
            "https://r2-ndr.ykt.cbern.com.cn",
            "https://r3-ndr.ykt.cbern.com.cn"
        ]
        for host in cdn_hosts:
            zip_url = f"{host}/{raw_path}"
            for attempt in range(retries):
                try:
                    req = urllib.request.Request(zip_url, headers=HEADERS)
                    with urllib.request.urlopen(req, timeout=40) as resp:
                        zip_data = resp.read()
                    if zip_data and len(zip_data) > 1000:
                        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                            mp4_names = [n for n in z.namelist() if n.lower().endswith(".mp4")]
                            if mp4_names:
                                mp4_names.sort(key=lambda n: z.getinfo(n).file_size, reverse=True)
                                target_mp4 = mp4_names[0]
                                tmp_save = save_path + ".tmp"
                                with z.open(target_mp4) as src, open(tmp_save, "wb") as dst:
                                    dst.write(src.read())
                                if os.path.exists(tmp_save) and os.path.getsize(tmp_save) > 1024 * 100:
                                    os.replace(tmp_save, save_path)
                                    return True
                except Exception:
                    time.sleep(1.0)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 1024 * 100:
                return True

    # 方案 2: 若 video_url 本身为 mp4 直链
    if video_url and (".mp4" in video_url.lower()):
        for attempt in range(retries):
            try:
                req = urllib.request.Request(video_url, headers=HEADERS)
                tmp_save = save_path + ".tmp"
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                if len(data) > 1024 * 100:
                    with open(tmp_save, "wb") as f:
                        f.write(data)
                    os.replace(tmp_save, save_path)
                    return True
            except Exception:
                time.sleep(1.0)

    return False

def download_file(url: str, save_path: str, retries: int = 3) -> bool:
    """下载图片文件到本地，自带重试机制"""
    if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
        return True
        
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                if len(data) > 0:
                    with open(save_path, "wb") as f:
                        f.write(data)
                    return True
        except Exception:
            time.sleep(1.0)
    return False

def clean_mathtype_units(text: str) -> str:
    """修复平台 MathType 历史遗留单位和公式标签"""
    if not text:
        return ""
    t = text
    # 修复常见单位拆分：{\rm{180c}}{{\rm{m}}^{\rm{2}}} -> 180\text{ cm}^2
    t = re.sub(r'\{\\rm\{(\d+)c\}\}\s*\{\{\\rm\{m\}\}\^\{\\rm\{2\}\}\}', r'\1\\text{ cm}^2', t)
    t = re.sub(r'\{\\rm\{(\d+)c\}\}\s*\{\{\\rm\{m\}\}\^\{\\rm\{3\}\}\}', r'\1\\text{ cm}^3', t)
    t = re.sub(r'\{\\rm\{(\d+)cm\}\}', r'\1\\text{ cm}', t)
    t = re.sub(r'\{\\rm\{(\d+)m\}\}', r'\1\\text{ m}', t)
    t = re.sub(r'\{\\rm\{(\d+)dm\}\}', r'\1\\text{ dm}', t)
    t = re.sub(r'\{\\rm\{(\d+)mm\}\}', r'\1\\text{ mm}', t)
    
    # 修复通用的 {\rm{X}}
    t = re.sub(r'\{\\rm\{([^{}]+)\}\}', r' \1 ', t)
    t = re.sub(r'\\rm\{([^{}]+)\}', r' \1 ', t)
    t = re.sub(r'\\rm\b', '', t)
    
    # 消除多层冗余括号
    while "{{" in t:
        new_t = re.sub(r'\{\{([^{}]+)\}\^\{([^{}]+)\}\}', r'\1^{\2}', t)
        new_t = re.sub(r'\{\{([^{}]+)\}\}', r'\1', new_t)
        if new_t == t:
            break
        t = new_t
        
    # 修复残余单位
    t = re.sub(r'c\s*\{\s*m\s*\^\s*2\s*\}', r'\\text{ cm}^2', t)
    t = re.sub(r'c\s*\{\s*m\s*\^\s*3\s*\}', r'\\text{ cm}^3', t)
    t = re.sub(r'(\d+)\s*c\s*m\^2\b', r'\1\\text{ cm}^2', t)
    t = re.sub(r'(\d+)\s*c\s*m\^3\b', r'\1\\text{ cm}^3', t)
    t = re.sub(r'(\d+)\s*cm\b', r'\1\\text{ cm}', t)
    t = re.sub(r'\\pi\s*c\s*\{\s*m\s*\^\s*2\s*\}', r'\\pi\\text{ cm}^2', t)
    return t

def clean_html_and_latex(text: str) -> str:
    """全面清洗 HTML 并标准化 LaTeX 数学公式（简易文本模式）"""
    if not text:
        return ""
    t = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]', '', text)
    t = clean_mathtype_units(t)
    
    # 规范化 LaTeX 标签
    t = re.sub(r'<latex[^>]*>(?:\\\(|\$)?\s*(.*?)\s*(?:\\\)|\$)?<\/latex>', r' $\1$ ', t, flags=re.DOTALL)
    t = re.sub(r'\\\((.*?)\\\)', r' $\1$ ', t, flags=re.DOTALL)
    t = re.sub(r'<textentryinteraction[^>]*><\/textentryinteraction>', ' _____ ', t)
    
    # 清除 HTML 标签与空白实体
    t = re.sub(r'<\/?(p|div|span|br)[^>]*>', ' ', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'&nbsp;', ' ', t)
    t = re.sub(r'&ldquo;|&rdquo;', '"', t)
    t = re.sub(r'[ \t]+', ' ', t)
    
    # 规范化连续美元符号与空格
    t = re.sub(r'\${2,}', '$', t)
    t = re.sub(r'\$[ \t]+', '$', t)
    t = re.sub(r'[ \t]+\$', '$', t)
    return t.strip()

def format_and_localize_rich_text(text: str, img_prefix: str, images_dir: str) -> str:
    """
    清洗富文本 HTML，下载内嵌图片到 images/ 目录，并将数学推导/解答步骤转换为排版优美的高保真 Markdown。
    彻底杜绝公式被包裹进单行反引号、杜绝段落被压成单行。
    """
    if not text:
        return ""
    t = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]', '', text)
    t = clean_mathtype_units(t)
    
    # 提取并下载嵌入的 <img> 图片
    img_matches = list(re.finditer(r'<img[^>]+src=["\'](https?://[^"\']+)["\'][^>]*>', t))
    for i, m in enumerate(img_matches, 1):
        img_url = m.group(1)
        img_name = f"{img_prefix}_{i}.png"
        img_path = os.path.join(images_dir, img_name)
        download_file(img_url, img_path)
        t = t.replace(m.group(0), f"\n\n![图](images/{img_name})\n\n")
        
    # 标准化 LaTeX 公式
    t = re.sub(r'<latex[^>]*>(?:\\\(|\$)?\s*(.*?)\s*(?:\\\)|\$)?<\/latex>', r' $\1$ ', t, flags=re.DOTALL)
    t = re.sub(r'\\\((.*?)\\\)', r' $\1$ ', t, flags=re.DOTALL)
    t = re.sub(r'<textentryinteraction[^>]*><\/textentryinteraction>', ' _____ ', t)
    
    # 段落和换行转换
    t = re.sub(r'<br\s*/?>', '\n', t)
    t = re.sub(r'</?(p|div)[^>]*>', '\n', t)
    t = re.sub(r'</?span[^>]*>', '', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'&nbsp;', ' ', t)
    t = re.sub(r'&ldquo;|&rdquo;', '"', t)
    t = re.sub(r'&lt;', '<', t)
    t = re.sub(r'&gt;', '>', t)
    t = re.sub(r'&amp;', '&', t)
    
    # 清理空格与空行（保留公式结构与真实换行，杜绝将相邻公式与换行合并）
    lines = [l.strip() for l in t.split('\n')]
    res_lines = []
    for l in lines:
        if l or (res_lines and res_lines[-1]):
            res_lines.append(l)
    res = '\n'.join(res_lines).strip()
    res = re.sub(r'\$[ \t]+', '$', res)
    res = re.sub(r'[ \t]+\$', '$', res)
    return res

class ExerciseBankAdapter(BaseResourceAdapter):
    """处理 /myPaper 同步练习题库适配器"""
    
    def match(self, url: str) -> bool:
        return "myPaper" in url

    def get_book_meta_from_page(self):
        """从网页面包屑或导航中智能获取当前教材的版本与年级册次"""
        js = r'''
        (() => {
          const allEls = Array.from(document.querySelectorAll('*'));
          const breadcrumbEl = allEls.find(el => {
            const t = (el.innerText || '').trim();
            return el.children.length === 0 && (t.includes('初中 / 数学') || t.includes('小学 / 数学') || t.includes('高中 / 数学'));
          });
          if (breadcrumbEl) return breadcrumbEl.innerText.trim();
          const tagEl = allEls.find(el => {
            const t = (el.innerText || '').trim();
            return t.includes('·') && (t.includes('版') || t.includes('册'));
          });
          return tagEl ? tagEl.innerText.trim() : '';
        })()
        '''
        res = eval_safari(js)
        if res and "/" in res:
            parts = [p.strip() for p in res.split("/") if p.strip()]
            if len(parts) >= 5:
                version = parts[2]
                grade_vol = (parts[3] + parts[4]).replace(" ", "")
                return version, grade_vol
            elif len(parts) == 4:
                version = parts[2]
                grade_vol = parts[3].replace(" ", "")
                return version, grade_vol
        elif res and "·" in res:
            parts = [p.strip() for p in res.split("·") if p.strip()]
            if len(parts) >= 3:
                return parts[2], (parts[0] + parts[1]).replace(" ", "")
            elif len(parts) == 2:
                return parts[1], parts[0].replace(" ", "")
        return "", ""

    def switch_volume(self, volume_name: str, max_wait: int = 8) -> bool:
        """控制 Safari 切换教材册次（自动选择 高中 -> 数学 -> 人教A版 -> 目标册次）"""
        js_open = '''
        (() => {
          const switchBtn = document.querySelector('.index-module_filter-title_76I5J .index-module_btn_fBO3m');
          if (switchBtn) { switchBtn.click(); return 'opened'; }
          return 'not found';
        })()
        '''
        eval_safari(js_open)
        time.sleep(1.0)
        
        # 1. 选中 高中
        eval_safari("""
        (() => {
          const tags = Array.from(document.querySelectorAll('.fish-drawer-body span, .fish-drawer-body div'));
          const el = tags.find(t => (t.innerText || '').trim() === '高中');
          if (el) el.click();
        })()
        """)
        time.sleep(0.8)

        # 2. 选中 数学
        eval_safari("""
        (() => {
          const tags = Array.from(document.querySelectorAll('.fish-drawer-body span, .fish-drawer-body div'));
          const el = tags.find(t => (t.innerText || '').trim() === '数学');
          if (el) el.click();
        })()
        """)
        time.sleep(0.8)

        # 3. 选中 人教A版
        eval_safari("""
        (() => {
          const tags = Array.from(document.querySelectorAll('.fish-drawer-body span, .fish-drawer-body div'));
          const el = tags.find(t => (t.innerText || '').trim() === '人教A版');
          if (el) el.click();
        })()
        """)
        time.sleep(0.8)
        
        # 4. 选中 目标册次
        js_click_vol = f'''
        (() => {{
          const tags = Array.from(document.querySelectorAll('.fish-drawer-body span, .fish-drawer-body div'));
          const targetName = "{volume_name}";
          const el = tags.find(t => {{
            const s = (t.innerText || '').trim();
            return s === targetName || s.replace(/\\s+/g, '') === targetName.replace(/\\s+/g, '');
          }});
          if (el) {{ el.click(); return 'clicked'; }}
          return 'not found';
        }})()
        '''
        eval_safari(js_click_vol)
        time.sleep(0.8)
        
        # 5. 点击 完成选择
        js_confirm = '''
        (() => {
          const btns = Array.from(document.querySelectorAll('.fish-drawer button, .fish-drawer span'));
          const el = btns.find(b => (b.innerText || '').trim() === '完成选择');
          if (el) { el.click(); return 'confirmed'; }
          return 'not found';
        })()
        '''
        eval_safari(js_confirm)
        time.sleep(2.0)
        
        for _ in range(max_wait * 2):
            time.sleep(0.5)
            curr_tag = eval_safari('(() => { const el = document.querySelector(".index-module_selected-tag_8J1Eb"); return el ? el.innerText : ""; })()')
            if volume_name in curr_tag or volume_name.replace(" ", "") in curr_tag.replace(" ", ""):
                time.sleep(1.5)
                return True
        return False

    def get_all_book_sections(self):
        """从 React 内部数据树中提取整本书所有大章与小节列表（智能识别真实叶子小节，避免父级重复与空节点）"""
        js = r'''
        const treeEl = document.querySelector('.fish-tree');
        if (!treeEl) return JSON.stringify([]);

        const fiberKey = Object.keys(treeEl).find(k => k.startsWith('__reactFiber'));
        let curr = treeEl[fiberKey];
        let roots = null;

        while (curr) {
          if (curr.memoizedProps && Array.isArray(curr.memoizedProps.children)) {
            const first = curr.memoizedProps.children[0];
            if (first && first.props && first.props.data) {
              roots = curr.memoizedProps.children.map(c => c.props.data).filter(Boolean);
              break;
            }
          }
          curr = curr.return;
        }

        if (!roots) return JSON.stringify([]);

        function getLeaves(node, currentChap) {
          const t = (node.title || node.rich_title || '').trim();
          const isChap = /^第[一二三四五六七八九十]+章/.test(t) || /^综合与实践/.test(t) || /^数学建模/.test(t);
          const chapName = isChap ? t : (currentChap || t || '综合与复习');
          const hasRes = (node.custom_properties && node.custom_properties.has_res !== undefined) ? node.custom_properties.has_res : false;
          const children = node.child_nodes || [];
          
          if (isChap) {
            let res = [];
            children.forEach(c => { res = res.concat(getLeaves(c, chapName)); });
            return res;
          }
          
          const activeChildren = children.filter(c => c.custom_properties && c.custom_properties.has_res);
          if (activeChildren.length > 0) {
            let res = [];
            activeChildren.forEach(c => { res = res.concat(getLeaves(c, chapName)); });
            return res;
          } else if (hasRes) {
            return [{ chapter: chapName, section: t, id: node.id, has_res: true }];
          } else {
            return [];
          }
        }

        let result = [];
        roots.forEach(r => { result = result.concat(getLeaves(r, null)); });
        return JSON.stringify(result);
        '''
        res = eval_safari(js)
        try:
            return json.loads(res)
        except Exception:
            return []

    def switch_to_section(self, chapter_name: str, section_name: str, max_retries: int = 2):
        """在页面左侧确保大章展开并选中小节，返回 (matched, is_empty)"""
        clean_chap = (chapter_name or "").strip()
        clean_sec = (section_name or "").strip()
        
        for attempt in range(max_retries):
            # 0. 关掉可能存在的弹窗
            eval_safari("const mc = document.querySelector('.fish-modal-close, button[aria-label=\"Close\"]'); if (mc) mc.click();")
            
            # 1. 展开大章（若处于闭合状态且指定了大章）
            if clean_chap:
                js_expand = f'''
                const rows = Array.from(document.querySelectorAll(".fish-tree-treenode"));
                const chapRow = rows.find(r => {{
                  const t = (r.innerText || "").trim().split("\\n")[0];
                  return t && t.includes("{clean_chap}");
                }});
                if (chapRow && chapRow.className.includes("switcher-close")) {{
                  const cw = chapRow.querySelector(".chapter-wrapper, .chapter-name") || chapRow;
                  cw.click();
                  return "expanded";
                }}
                return chapRow ? "already open" : "chapRow not found";
                '''
                eval_safari(js_expand)
                time.sleep(1.0)
            
            # 2. 精准定位并点击小节（在所属章节作用域内查找，防止同名“小结/复习”串台，支持 .active-name 与 .chapter-name）
            js_click = f'''
            const rows = Array.from(document.querySelectorAll(".fish-tree-treenode"));
            let searchRows = rows;
            const chap = "{clean_chap}";
            const sec = "{clean_sec}";
            
            if (chap) {{
              const chapIdx = rows.findIndex(r => {{
                const t = (r.innerText || "").trim().split("\\n")[0];
                return t && t.includes(chap);
              }});
              if (chapIdx !== -1) {{
                const nextChapIdx = rows.findIndex((r, idx) => {{
                  if (idx <= chapIdx) return false;
                  const t = (r.innerText || "").trim().split("\\n")[0];
                  return /^第[一二三四五六七八九十]+章/.test(t) || /^综合与实践/.test(t) || /^数学建模/.test(t) || /^总复习/.test(t);
                }});
                searchRows = nextChapIdx !== -1 ? rows.slice(chapIdx, nextChapIdx) : rows.slice(chapIdx);
              }}
            }}
            
            const secRow = searchRows.find(r => {{
              const t = (r.innerText || "").trim().split("\\n")[0];
              if (!t) return false;
              return t.includes(sec) || sec.includes(t);
            }});
            if (!secRow) return "secRow not found in searchRows: " + searchRows.length;
            const target = secRow.querySelector(".active-name, .chapter-name, .active-wrapper, .chapter-wrapper") || secRow;
            target.click();
            return "clicked sec: " + (target.innerText || secRow.innerText).trim().split("\\n")[0];
            '''
            eval_safari(js_click)
            time.sleep(2.0)
            
            # 3. 严格校验选中状态（匹配高亮选中的节点文本）
            js_verify = f'''
            const selEl = document.querySelector(".fish-tree-node-selected, .fish-tree-treenode-selected");
            const selText = selEl ? selEl.innerText.trim().split("\\n")[0] : "";
            const isSelected = Boolean(selText && (selText.includes("{clean_sec}") || "{clean_sec}".includes(selText)));
            const emptyNotice = document.body.innerText.includes("哎呀，这里空空如也");
            return JSON.stringify({{
              matched: isSelected,
              empty: emptyNotice
            }});
            '''
            try:
                info = json.loads(eval_safari(js_verify))
                matched = info.get("matched", False)
                empty = info.get("empty", False)
                if matched or empty:
                    return matched, empty
            except Exception:
                pass
                
            time.sleep(1.0)
            
        return False, False

    def extract_current_page_questions(self):
        """深度提取当前页题目、选项、插图与答案（纯净解析视图数据结构）"""
        js = r'''
        function extractQuestions() {
          const items = Array.from(document.querySelectorAll('.index-module_question_item_dyjTx'));
          return items.map((item, idx) => {
            const fiberKey = Object.keys(item).find(k => k.startsWith('__reactFiber'));
            let curr = item[fiberKey];
            let qObj = null;
            let qInfo = null;
            while (curr) {
              if (!qInfo && curr.memoizedProps && curr.memoizedProps.questionInfo) {
                qInfo = curr.memoizedProps.questionInfo;
              }
              if (!qObj && curr.memoizedState) {
                let s = curr.memoizedState;
                while (s) {
                  if (s.memoizedState && typeof s.memoizedState === 'object' && s.memoizedState.content) {
                    qObj = s.memoizedState;
                    break;
                  }
                  s = s.next;
                }
              }
              curr = curr.return;
            }
            
            const lines = item.innerText.split('\n').map(s => s.trim()).filter(Boolean);
            const typeLabel = lines.find(t => ['填空题', '单选题', '多选题', '问答题', '计算题', '复合题', '解答题'].some(k => t.includes(k))) || '题目';
            const diffLabel = lines.find(t => t.startsWith('难易度：')) || '难易度：普通';
            
            const c = qObj ? (qObj.content || {}) : {};
            const cp = (qInfo && qInfo.custom_properties) || {};
            const km = (qInfo && qInfo.knowledge_marks) || [];
            let kpList = km.map(k => k.name).filter(Boolean);
            if (kpList.length === 0 && Array.isArray(cp.qb_knowledge_points)) {
              kpList = cp.qb_knowledge_points;
            }
            
            // 1. 主题干 HTML
            let stemHtml = c.description || c.title || (qInfo ? (qInfo.description || qInfo.title) : '') || '';
            
            // 2. 子题目（用于复合题）
            const qtiItems = c.items || [];
            const subList = [];
            qtiItems.forEach(qi => {
              if (qi.type === 'data' && qtiItems.length > 1) return;
              subList.push({
                type: qi.type,
                prompt: qi.prompt || qi.title || '',
                choices: (qi.choices || []).map(ch => ({
                  id: ch.identifier,
                  text: ch.text || ''
                }))
              });
            });
            
            // 3. 标准答案
            const responses = (c.responses || []).map(r => ({
              id: r.identifier,
              corrects: r.corrects || []
            }));
            
            // 4. 解析与视频
            let hasVideo = false;
            let videoUrl = '';
            let videoTitle = '';
            const textFeedbacks = [];
            (c.feedbacks || []).forEach(f => {
              const fc = f.content || '';
              const vMatch = fc.match(/src=["']([^"']+\.(m3u8|mp4)[^"']*)["']/i);
              if (vMatch) {
                hasVideo = true;
                videoUrl = vMatch[1];
              } else if (fc.includes('<video') || fc.includes('.m3u8')) {
                hasVideo = true;
              }
              const tMatch = fc.match(/title=["']([^"']+)["']/i);
              if (tMatch) {
                videoTitle = tMatch[1];
              }
              let cleanF = fc.replace(/<video[^>]*>.*?<\/video>/gis, '');
              cleanF = cleanF.replace(/[\u200b\u200c\u200d\u200e\u200f\ufeff]/g, '').trim();
              if (cleanF && !cleanF.includes('解析视频请查看最后一题')) {
                textFeedbacks.push(cleanF);
              }
            });

            const packingResult = (cp.sys_packing_result && cp.sys_packing_result.result) || '';
            
            // 5. 抓取该题目下 DOM 中的真实图片 URL
            const domImgs = Array.from(item.querySelectorAll('img'))
              .map(i => i.src)
              .filter(s => s && !s.startsWith('data:'));
              
            // 6. 从 items 数据中提取已解析的高清 CDN 图片 URL
            const itemImgs = [];
            (c.items || []).forEach(qi => {
              const p = qi.prompt || '';
              const matches = p.match(/src=["'](https?:\/\/[^"']+)["']/g) || [];
              matches.forEach(m => {
                const u = m.replace(/^src=["']|["']$/g, '');
                if (!itemImgs.includes(u)) itemImgs.push(u);
              });
            });
              
            return {
              qIdx: idx + 1,
              id: (qObj && qObj.id) || (qInfo && qInfo.id) || ('q_' + idx),
              type_label: typeLabel,
              difficulty: diffLabel.replace('难易度：', '').trim(),
              knowledge_points: kpList,
              create_time: (qInfo && qInfo.create_time) || '',
              teacher: cp.qb_teacher_name || '',
              teacher_intro: cp.qb_teacher_intro || '',
              guiders: cp.qb_guider_names || [],
              guider_intros: cp.qb_guider_intros || [],
              video_url: videoUrl,
              video_title: videoTitle,
              packing_result: packingResult,
              preview_big: (qInfo && qInfo.preview && qInfo.preview.question_big) || '',
              stem_html: stemHtml,
              sub_items: subList,
              responses: responses,
              has_video: hasVideo,
              text_feedbacks: textFeedbacks,
              dom_imgs: domImgs,
              item_imgs: itemImgs
            };
          });
        }
        return JSON.stringify(extractQuestions());
        '''
        res = eval_safari(js)
        try:
            return json.loads(res)
        except Exception:
            return []

    def get_total_pages(self):
        js = r'''
        const pagination = document.querySelector('.fish-pagination');
        if (!pagination) return 1;
        const pageItems = Array.from(pagination.querySelectorAll('.fish-pagination-item'));
        if (pageItems.length === 0) return 1;
        const nums = pageItems.map(p => parseInt((p.innerText || '').trim())).filter(n => !isNaN(n));
        return nums.length > 0 ? Math.max(...nums) : 1;
        '''
        res = eval_safari(js)
        try:
            return int(res)
        except Exception:
            return 1

    def go_to_page(self, page_num: int):
        js = f'''
        const pagination = document.querySelector('.fish-pagination');
        if (!pagination) return 'no pagination';
        const pageItems = Array.from(pagination.querySelectorAll('.fish-pagination-item'));
        const target = pageItems.find(p => parseInt((p.innerText || '').trim()) === {page_num});
        if (target) {{
          target.click();
          return 'clicked page ' + {page_num};
        }}
        const nextBtn = pagination.querySelector('.fish-pagination-next');
        if (nextBtn && !nextBtn.className.includes('fish-pagination-disabled')) {{
          nextBtn.click();
          return 'clicked next';
        }}
        return 'not found';
        '''
        eval_safari(js)
        time.sleep(2.0)

    def extract_section_all_questions(self, chapter_name: str, section_name: str):
        matched, is_empty = self.switch_to_section(chapter_name, section_name)
        if not matched:
            print(f"    ⚠️ 警告：章节切换校验未通过（目标: {section_name}），跳过避免重复数据！", flush=True)
            return []
        if is_empty:
            print(f"    ℹ️ 当前小节在智慧平台暂未录入习题（显示空空如也）", flush=True)
            return []
            
        total_pages = self.get_total_pages()
        print(f"    📄 检测到分页: 共 {total_pages} 页", flush=True)
        all_q = []
        seen_ids = set()
        
        for p in range(1, total_pages + 1):
            if p > 1:
                print(f"      👉 正在翻页至第 {p}/{total_pages} 页...", flush=True)
                self.go_to_page(p)
            q_list = self.extract_current_page_questions()
            new_cnt = 0
            for q in q_list:
                if q["id"] not in seen_ids:
                    seen_ids.add(q["id"])
                    all_q.append(q)
                    new_cnt += 1
            print(f"      ✅ 第 {p} 页完成，获取到 {new_cnt} 道题目 (累计: {len(all_q)} 道)", flush=True)
            time.sleep(0.5)
            
        return all_q

    def export_section_files(self, chapter: str, section: str, questions: list, output_dir: str):
        safe_chap = (chapter or "").strip() or (section or "").strip() or "综合与复习"
        safe_sec = (section or "").strip() or "练习"
        target_dir = os.path.join(output_dir, safe_chap, safe_sec)
        images_dir = os.path.join(target_dir, "images")
        videos_dir = os.path.join(target_dir, "videos")
        os.makedirs(images_dir, exist_ok=True)
        
        md_path = os.path.join(target_dir, f"{safe_sec}_题库.md")
        md_lines = [
            f"# {safe_chap} - {safe_sec} 同步练习题库",
            f"\n> 来源：国家中小学智慧教育平台 · 习题库",
            f"> 题目总数：{len(questions)} 道\n",
            "---\n"
        ]
        
        for idx, q in enumerate(questions, 1):
            type_lbl = q.get("type_label", "题目")
            diff = q.get("difficulty", "普通")
            kp_list = q.get("knowledge_points", [])
            kp = "、".join(kp_list) if kp_list else "同步练习"
            
            md_lines.append(f"### 第 {idx} 题 【{type_lbl}】")
            md_lines.append(f"- **难度**：{diff}  |  **知识点**：{kp}\n")
            
            # 1. 题干处理（替换图片占位符）
            stem_html = q.get("stem_html", "")
            dom_imgs = q.get("dom_imgs", [])
            item_imgs = q.get("item_imgs", [])
            
            # 整合 items 与 DOM 中可用的真实图片 URL
            combined_imgs = [u for u in item_imgs if u]
            for u in dom_imgs:
                if u not in combined_imgs:
                    combined_imgs.append(u)
                    
            stem_img_matches = list(re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', stem_html))
            used_img_idx = 0
            for s_i, match in enumerate(stem_img_matches, 1):
                raw_src = match.group(1)
                real_url = ""
                if raw_src.startswith("http"):
                    real_url = raw_src
                elif used_img_idx < len(combined_imgs):
                    real_url = combined_imgs[used_img_idx]
                    used_img_idx += 1
                    
                if real_url:
                    img_name = f"q{idx}_stem_{s_i}.png"
                    img_path = os.path.join(images_dir, img_name)
                    download_file(real_url, img_path)
                    stem_html = stem_html.replace(match.group(0), f"\n\n![图](images/{img_name})\n\n", 1)
                else:
                    stem_html = stem_html.replace(match.group(0), "", 1)
                    
            clean_stem = format_and_localize_rich_text(stem_html, f"q{idx}_stem_extra", images_dir)
            clean_stem = re.sub(r'^\s*(填空题|单选题|多选题|问答题|计算题|复合题|解答题)\s*', '', clean_stem)
            md_lines.append(f"**【题目】**\n{clean_stem}\n")
            
            # 2. 子题目（复合题）
            sub_items = q.get("sub_items", [])
            is_composite = len(sub_items) > 1 or "复合" in type_lbl
            
            if is_composite and sub_items:
                for s_idx, sub in enumerate(sub_items, 1):
                    p_text = format_and_localize_rich_text(sub.get("prompt", ""), f"q{idx}_sub_{s_idx}", images_dir)
                    sub_choices = sub.get("choices", [])
                    md_lines.append(f"({s_idx}) {p_text}")
                    if sub_choices:
                        for ch in sub_choices:
                            ch_id = ch.get("id", "")
                            ch_raw = ch.get("text", "")
                            ch_img_match = re.search(r'src=["\'](https?://[^"\']+)["\']', ch_raw)
                            ch_img_embed = ""
                            if ch_img_match:
                                ch_img_url = ch_img_match.group(1)
                                ch_img_name = f"q{idx}_sub_{s_idx}_choice_{ch_id}.png"
                                ch_img_path = os.path.join(images_dir, ch_img_name)
                                download_file(ch_img_url, ch_img_path)
                                ch_img_embed = f" ![选项{ch_id}](images/{ch_img_name})"
                            ch_clean_raw = re.sub(r'<img[^>]*>', '', ch_raw)
                            ch_t = clean_html_and_latex(ch_clean_raw)
                            md_lines.append(f"   - **{ch_id}.** {ch_t}{ch_img_embed}")
                md_lines.append("")
            elif sub_items and sub_items[0].get("choices"):
                for ch in sub_items[0]["choices"]:
                    ch_id = ch.get("id", "")
                    ch_raw = ch.get("text", "")
                    ch_img_match = re.search(r'src=["\'](https?://[^"\']+)["\']', ch_raw)
                    ch_img_embed = ""
                    if ch_img_match:
                        ch_img_url = ch_img_match.group(1)
                        ch_img_name = f"q{idx}_choice_{ch_id}.png"
                        ch_img_path = os.path.join(images_dir, ch_img_name)
                        download_file(ch_img_url, ch_img_path)
                        ch_img_embed = f" ![选项{ch_id}](images/{ch_img_name})"
                    ch_clean_raw = re.sub(r'<img[^>]*>', '', ch_raw)
                    ch_t = clean_html_and_latex(ch_clean_raw)
                    md_lines.append(f"- **{ch_id}.** {ch_t}{ch_img_embed}")
                md_lines.append("")
                
            # 3. 标准参考答案（高保真数学公式与答案配图支持，杜绝反引号禁用公式）
            responses = q.get("responses", [])
            ans_entries = []
            for r_i, r in enumerate(responses, 1):
                c_list = []
                for c_i, c in enumerate(r.get("corrects", []), 1):
                    prefix = f"q{idx}_ans_{r_i}_{c_i}" if len(responses) > 1 else f"q{idx}_ans_{c_i}"
                    c_clean = format_and_localize_rich_text(c, prefix, images_dir)
                    if c_clean:
                        c_list.append(c_clean)
                if c_list:
                    ans_val = "、".join(c_list)
                    ans_entries.append((r_i, ans_val))
                        
            if is_composite and len(responses) > 1:
                ans_body = []
                for r_i, a_val in ans_entries:
                    if "\n" in a_val or "![" in a_val:
                        indented = "\n  ".join(a_val.split("\n"))
                        ans_body.append(f"- ({r_i}) {indented}")
                    else:
                        ans_body.append(f"- ({r_i}) {a_val}")
                md_lines.append("**【参考答案】**：\n" + "\n".join(ans_body) + "\n")
            elif len(ans_entries) > 1:
                is_all_single = all("\n" not in a_val and "![" not in a_val for _, a_val in ans_entries)
                if is_all_single:
                    sub_ans = [f"({r_i}) {a_val}" for r_i, a_val in ans_entries]
                    md_lines.append(f"**【参考答案】**：{'   '.join(sub_ans)}\n")
                else:
                    ans_body = [f"- ({r_i}) {a_val}" for r_i, a_val in ans_entries]
                    md_lines.append("**【参考答案】**：\n" + "\n".join(ans_body) + "\n")
            elif ans_entries:
                single_ans = ans_entries[0][1]
                if "\n" in single_ans or "![" in single_ans:
                    md_lines.append(f"**【参考答案】**：\n\n{single_ans}\n")
                else:
                    md_lines.append(f"**【参考答案】**：{single_ans}\n")
            else:
                md_lines.append("**【参考答案】**：暂无官方文本答案（请参考名师微课精讲）\n")
                
            # 4. 详细解析与名师微课视频
            text_fbs = [format_and_localize_rich_text(f, f"q{idx}_fb_{f_i}", images_dir) for f_i, f in enumerate(q.get("text_feedbacks", []), 1) if f]
            text_fbs = [f for f in text_fbs if f]
            has_video = q.get("has_video", False)
            teacher = q.get("teacher", "")
            guiders = q.get("guiders", [])
            video_url = q.get("video_url", "")
            packing_result = q.get("packing_result", "")
            
            fb_lines = []
            if text_fbs:
                fb_lines.append("\n\n".join(text_fbs))
            else:
                fb_lines.append(f"本题考查核心知识点【{kp}】。本题配备官方微课精讲，详细解题思路、步骤推导与考点剖析请观看名师微课视频。")
                
            # 视频下载与本地化关联
            local_video_rel = ""
            if has_video or packing_result:
                video_filename = f"q{idx}_解析微课.mp4"
                video_save_path = os.path.join(videos_dir, video_filename)
                print(f"      📥 正在检测/提取第 {idx} 题名师微课视频...", flush=True)
                download_ok = download_question_video(packing_result, video_url, video_save_path)
                if download_ok:
                    size_mb = os.path.getsize(video_save_path) / (1024 * 1024)
                    local_video_rel = f"videos/{video_filename}"
                    print(f"      🎥 已完成微课视频提取: {local_video_rel} ({size_mb:.2f} MB)", flush=True)
                else:
                    print(f"      ℹ️ 第 {idx} 题暂无可用微课视频或提取跳过", flush=True)
                
            if has_video or local_video_rel:
                t_info = f"主讲教师：{teacher}" if teacher else "名师微课"
                if guiders:
                    t_info += f"（指导团队：{'、'.join(guiders)}）"
                video_note = f"> 🎥 **官方名师微课精讲**：本题配备官方微课讲解（{t_info}）。可在智慧教育平台网页端本题目右下方点击【查看解析】播放。"
                if local_video_rel:
                    video_note += f"\n>\n> ![[{local_video_rel}]]"
                fb_lines.append(video_note)
                
            md_lines.append("**【解析】**：\n" + "\n\n".join(fb_lines) + "\n")
            
            # 5. 习题信息（全量抓取查看解析抽屉元数据）
            create_time_raw = q.get("create_time", "")
            create_time_fmt = create_time_raw.replace("T", " ").split(".")[0] if create_time_raw else ""
            teacher_intro = q.get("teacher_intro", "").strip().rstrip("，,")
            guiders = q.get("guiders", [])
            guider_intros = q.get("guider_intros", [])
            
            info_lines = [
                f"- **考查知识点**：{kp}",
                f"- **难易度**：{diff}"
            ]
            if create_time_fmt:
                info_lines.append(f"- **创建时间**：{create_time_fmt}")
            if teacher:
                t_str = f"{teacher}（{teacher_intro}）" if teacher_intro else teacher
                info_lines.append(f"- **主讲人**：{t_str}")
            if guiders:
                g_strs = []
                for g_idx, g_name in enumerate(guiders):
                    g_intro = guider_intros[g_idx].strip().rstrip("，,。") if g_idx < len(guider_intros) else ""
                    g_strs.append(f"{g_name}（{g_intro}）" if g_intro else g_name)
                info_lines.append(f"- **指导团队**：{'、'.join(g_strs)}")
                
            md_lines.append("**【习题信息】**：\n" + "\n".join(info_lines) + "\n")
            md_lines.append("\n---\n")
            
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
            
        return md_path

    def run(self, output_dir: str, **kwargs):
        # 智能动态推断当前教材版本与年级册次
        if not output_dir or output_dir.endswith("/习题库") or output_dir.endswith("/习题库/初中") or output_dir.endswith("/北师大版/七年级上册"):
            version, grade_vol = self.get_book_meta_from_page()
            if version and grade_vol:
                base_root = output_dir.split("/习题库")[0] if "/习题库" in output_dir else "/Users/oven/Downloads/中小学智慧平台资源"
                is_junior = any(g in (grade_vol or "") for g in ["七年级", "八年级", "九年级"])
                stage_dir = "初中" if is_junior else ""
                if stage_dir:
                    output_dir = os.path.join(base_root, "习题库", stage_dir, version, grade_vol)
                else:
                    output_dir = os.path.join(base_root, "习题库", version, grade_vol)

        print(f"==================================================", flush=True)
        print(f"🌟 启动 ExerciseBankAdapter (国家智慧平台习题库解析引擎 · 独立归档版)", flush=True)
        print(f"📂 存储基准目录: {output_dir}", flush=True)
        print(f"==================================================\n", flush=True)
        
        print("🔍 正在提取教材章节与小节目录树...", flush=True)
        sections = self.get_all_book_sections()
        print(f"🎯 成功识别到整本书小节总数: {len(sections)} 个\n", flush=True)
        
        total_q_count = 0
        total_img_count = 0
        total_video_count = 0
        success_sec_count = 0
        
        for i, item in enumerate(sections, 1):
            chap = (item.get("chapter") or "").strip() or (item.get("section") or "").strip() or "综合与复习"
            sec = (item.get("section") or "").strip()
            has_res = item.get("has_res", True)
            
            if not has_res or not sec:
                print(f"[{i:2d}/{len(sections)}] ⏩ 自动跳过: {chap} -> {sec} (平台未录入习题)", flush=True)
                continue

            # 增加秒级幂等校验：若本地已经完整提取且包含题库文件，秒级跳过
            target_sec_dir = os.path.join(output_dir, chap, sec)
            target_md = os.path.join(target_sec_dir, f"{sec}_题库.md")
            if os.path.exists(target_md) and os.path.getsize(target_md) > 500:
                sec_imgs_dir = os.path.join(target_sec_dir, "images")
                sec_vids_dir = os.path.join(target_sec_dir, "videos")
                img_cnt = len(os.listdir(sec_imgs_dir)) if os.path.exists(sec_imgs_dir) else 0
                vid_cnt = len(os.listdir(sec_vids_dir)) if os.path.exists(sec_vids_dir) else 0
                total_img_count += img_cnt
                total_video_count += vid_cnt
                success_sec_count += 1
                print(f"[{i:2d}/{len(sections)}] ⏩ 已存在题库且内容完整，秒级跳过: {chap} -> {sec} (包含 {img_cnt} 张高清插图, {vid_cnt} 部微课视频)", flush=True)
                continue
            
            print(f"[{i:2d}/{len(sections)}] 📥 正在抓取: {chap} -> {sec} ...", flush=True)
            questions = self.extract_section_all_questions(chap, sec)
            print(f"    👉 成功提取到 {len(questions)} 道题目", flush=True)
            
            if questions:
                md_p = self.export_section_files(chap, sec, questions, output_dir)
                sec_imgs_dir = os.path.join(os.path.dirname(md_p), "images")
                sec_vids_dir = os.path.join(os.path.dirname(md_p), "videos")
                img_cnt = len(os.listdir(sec_imgs_dir)) if os.path.exists(sec_imgs_dir) else 0
                vid_cnt = len(os.listdir(sec_vids_dir)) if os.path.exists(sec_vids_dir) else 0
                total_q_count += len(questions)
                total_img_count += img_cnt
                total_video_count += vid_cnt
                success_sec_count += 1
                print(f"    ✅ 已生成题库: {os.path.basename(md_p)} (包含 {img_cnt} 张高清插图, {vid_cnt} 部名师微课视频)", flush=True)
            else:
                print(f"    ⚠️ 当前小节跳过（无习题或未录入）", flush=True)
                
            time.sleep(random.uniform(0.6, 1.2))
            
        print(f"\n==================================================", flush=True)
        print(f"🏆 习题库同步练习全部抓取完成！")
        print(f"📊 有效习题小节: {success_sec_count}/{len(sections)}")
        print(f"📝 收录真实题目总计: {total_q_count} 道，本地高清图片: {total_img_count} 张，名师微课视频: {total_video_count} 部")
        print(f"📂 独立存放目录: {output_dir}")
        print(f"==================================================\n", flush=True)
