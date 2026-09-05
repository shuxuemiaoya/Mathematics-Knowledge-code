# -*- coding: utf-8 -*-
import os, sys, json, re, time, random, urllib.request, urllib.parse
from io import BytesIO
from PIL import Image
from adapters.base_adapter import BaseResourceAdapter
from safari_helper import eval_safari

BANK_ID_DEFAULT = "8a2ef0e4-ef7d-4f69-b1c3-1bc81562877e"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Referer": "https://basic.smartedu.cn/"
}

class PrepareMaterialAdapter(BaseResourceAdapter):
    """处理 /syncClassroom/prepare 备课资源（课件/教学设计/整套试卷）的适配器"""
    
    def match(self, url: str) -> bool:
        return "syncClassroom/prepare" in url
        
    def extract_current_book_data(self):
        js = """
        const treeEl = document.querySelector('.fish-tree');
        if (!treeEl) return JSON.stringify({ error: 'no fish-tree' });
        const fiberKey = Object.keys(treeEl).find(k => k.startsWith('__reactFiber'));
        let curr = treeEl[fiberKey];
        let textBookInfo = null;
        let chapterNodes = null;
        while (curr) {
          if (curr.memoizedProps) {
            if (!textBookInfo && curr.memoizedProps.textBookInfo) textBookInfo = curr.memoizedProps.textBookInfo;
            if (!chapterNodes && Array.isArray(curr.memoizedProps.children) && curr.memoizedProps.children.length >= 2) {
              const first = curr.memoizedProps.children[0];
              if (first && first.key && typeof first.key === 'string' && first.key.length > 20) {
                chapterNodes = curr.memoizedProps.children;
              }
            }
          }
          curr = curr.return;
        }
        if (!textBookInfo) return JSON.stringify({ error: 'no textBookInfo' });
        function parseNode(node) {
          if (!node) return null;
          const p = node.props || {};
          const d = p.data || {};
          const title = typeof p.title === 'string' ? p.title : (d.title || d.name || node.key);
          let sub = [];
          if (Array.isArray(p.children)) sub = p.children.map(parseNode).filter(Boolean);
          return { id: node.key || d.id, title: title, children: sub };
        }
        return JSON.stringify({
          detail: textBookInfo.detail || {},
          tree: (chapterNodes || []).map(parseNode).filter(Boolean),
          courseList: textBookInfo.courseList || []
        });
        """
        res = eval_safari(js)
        data = json.loads(res)
        if "error" in data:
            raise RuntimeError(data["error"])
        return data

    def run(self, output_dir: str, **kwargs):
        data = self.extract_current_book_data()
        detail = data.get("detail", {})
        book_title = detail.get("title", "未命名教材")
        print(f"📖 正在通过 PrepareMaterialAdapter 处理: {book_title}")
        # 执行原有的三合一多类型资源下载逻辑
        # ...
