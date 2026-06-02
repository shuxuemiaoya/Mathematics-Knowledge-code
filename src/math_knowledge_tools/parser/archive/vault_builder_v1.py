import os
import re
from pathlib import Path
from typing import List, Dict, Any
from .categorizer import Categorizer
from .vault_models import ObsidianNode

class VaultBuilder:
    def __init__(self, vault_dir: str):
        self.vault_dir = Path(vault_dir)
        self.categorizer = Categorizer()
        self.nodes: Dict[str, ObsidianNode] = {}
        
    def _get_or_create_node(self, title: str, category: str) -> ObsidianNode:
        if title not in self.nodes:
            self.nodes[title] = ObsidianNode(title=title, category=category)
        return self.nodes[title]
        
    def _extract_title_from_callout(self, content: str) -> str:
        # e.g., "> [!example] 例1" -> "例1"
        match = re.search(r'^>\s*\[!\w+\](?:-|\+)?\s*(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        # Fallback if no title found
        return f"Block_{hash(content)}"

    def build_from_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        for chunk in chunks:
            hierarchy = chunk.get("parent_hierarchy", [])
            content = chunk.get("content", "")
            category = self.categorizer.categorize(chunk)
            
            # Make sure all parents exist and link to each other (Strict RKDT)
            for i in range(len(hierarchy)):
                parent_title = hierarchy[i]
                parent_node = self._get_or_create_node(parent_title, "知识点")
                if i < len(hierarchy) - 1:
                    child_title = hierarchy[i+1]
                    parent_node.add_link(child_title)
            
            if not hierarchy:
                continue
                
            leaf_title = hierarchy[-1]
            leaf_node = self._get_or_create_node(leaf_title, "知识点")
            
            # If it's just a text block under a heading, append it to the leaf node
            if chunk.get("type") == "text":
                if leaf_node.content:
                    leaf_node.content += f"\n\n{content}"
                else:
                    leaf_node.content = content
            
            # If it's a callout, it becomes its own separate node and is linked by the leaf node
            elif chunk.get("type") == "callout":
                callout_title = self._extract_title_from_callout(content)
                callout_node = self._get_or_create_node(callout_title, category)
                callout_node.content = content
                
                # Link from leaf to callout
                leaf_node.add_link(callout_title)
                
        self._write_to_disk()
        
    def _write_to_disk(self) -> None:
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        for node in self.nodes.values():
            cat_dir = self.vault_dir / node.category
            cat_dir.mkdir(parents=True, exist_ok=True)
            
            safe_title = re.sub(r'[\\/*?:"<>|]', '_', node.title)
            file_path = cat_dir / f"{safe_title}.md"
            file_path.write_text(node.to_markdown(), encoding="utf-8")
