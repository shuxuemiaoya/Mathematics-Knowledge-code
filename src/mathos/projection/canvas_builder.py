import os
import json
import logging
import math
from pathlib import Path
import uuid

logger = logging.getLogger(__name__)

class HybridCanvasBuilder:
    def __init__(self, vault_dir: str, ontology_path: str):
        self.vault_dir = Path(vault_dir)
        self.ontology_path = Path(ontology_path)
        
        self.nodes = []
        self.edges = []
        
        # Track layout positions
        self.current_y = 0
        self.file_nodes_map = {}  # relative_file_path -> node_id

    def build(self, output_path: str):
        if not self.ontology_path.exists():
            logger.error(f"Ontology file missing: {self.ontology_path}")
            return
            
        # 1. Build physical tree (Vault structure)
        self._build_tree()
        
        # 2. Build star clusters (Concepts)
        self._build_star_clusters()
        
        # 3. Output canvas
        canvas_data = {
            "nodes": self.nodes,
            "edges": self.edges
        }
        
        out_file = Path(output_path)
        out_file.write_text(json.dumps(canvas_data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Successfully generated Canvas: {out_file}")

    def _build_tree(self):
        """Walks the vault directory to build the tree backbone."""
        # Simple vertical list layout with horizontal depth
        for root, dirs, files in os.walk(self.vault_dir):
            rel_root = Path(root).relative_to(self.vault_dir)
            
            # Skip hidden folders and candidate output folders
            if any(part.startswith('.') or part.endswith('candidates') for part in rel_root.parts):
                continue
                
            depth = len(rel_root.parts)
            
            for file in files:
                if not file.endswith(".md") or file.startswith("【人教版】"):
                    continue
                    
                rel_file_path = str(rel_root / file).replace("\\", "/")
                node_id = str(uuid.uuid4())
                
                # Create a file node
                self.nodes.append({
                    "id": node_id,
                    "type": "file",
                    "file": rel_file_path,
                    "x": depth * 600,
                    "y": self.current_y,
                    "width": 300,
                    "height": 100
                })
                
                self.file_nodes_map[rel_file_path] = node_id
                self.current_y += 600 # Space out vertically for star clusters

    def _build_star_clusters(self):
        """Places concepts in a circular orbit around their source file."""
        data = json.loads(self.ontology_path.read_text(encoding="utf-8"))
        entities = data.get("ontology", [])
        
        # Group entities by source file
        from collections import defaultdict
        source_map = defaultdict(list)
        name_to_node_id = {}
        
        for entity in entities:
            src = entity.get("_source_file", "")
            # Convert candidate JSON path to its source Markdown path
            # e.g. 知识点candidates/10.1.candidates.json -> 知识点/10.1.md
            if src.endswith(".candidates.json"):
                src_md = src.replace("candidates.json", ".md")
                parts = src_md.split("/")
                if len(parts) > 1 and parts[0].endswith("candidates"):
                    parts[0] = parts[0][:-10] # remove "candidates"
                src = "/".join(parts)
                
            source_map[src].append(entity)

        # Place concept nodes
        for src_file, concept_list in source_map.items():
            parent_id = self.file_nodes_map.get(src_file)
            if not parent_id:
                # If source file is not found (e.g., filtered out), put them at origin
                parent_x, parent_y = 0, 0
            else:
                parent_node = next(n for n in self.nodes if n["id"] == parent_id)
                parent_x, parent_y = parent_node["x"], parent_node["y"]
                
            num_concepts = len(concept_list)
            radius = 300
            
            for i, concept in enumerate(concept_list):
                angle = 2 * math.pi * i / num_concepts
                cx = parent_x + radius * math.cos(angle)
                cy = parent_y + radius * math.sin(angle)
                
                c_id = str(uuid.uuid4())
                name_to_node_id[concept.get("name")] = c_id
                
                color = "1" if concept.get("type") == "定理" else "2" # Red/Orange vs Blue
                
                self.nodes.append({
                    "id": c_id,
                    "type": "text",
                    "text": f"**{concept.get('name')}**\n{concept.get('category')}",
                    "x": int(cx),
                    "y": int(cy),
                    "width": 200,
                    "height": 80,
                    "color": color
                })
                
                # Edge from parent file to concept
                if parent_id:
                    self.edges.append({
                        "id": str(uuid.uuid4()),
                        "fromNode": parent_id,
                        "fromSide": "right",
                        "toNode": c_id,
                        "toSide": "left"
                    })

        # Place edges for prerequisites
        for entity in entities:
            c_id = name_to_node_id.get(entity.get("name"))
            if not c_id:
                continue
                
            for prereq in entity.get("prerequisites", []):
                prereq_id = name_to_node_id.get(prereq)
                if prereq_id:
                    self.edges.append({
                        "id": str(uuid.uuid4()),
                        "fromNode": prereq_id,
                        "fromSide": "bottom",
                        "toNode": c_id,
                        "toSide": "top",
                        "label": "requires",
                        "color": "3" # Green line
                    })
