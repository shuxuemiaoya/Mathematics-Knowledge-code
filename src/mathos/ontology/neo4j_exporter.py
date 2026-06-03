import csv
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class Neo4jExporter:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def export(self, global_ontology_path: str):
        ontology_file = Path(global_ontology_path)
        if not ontology_file.exists():
            logger.error(f"Global ontology file not found: {ontology_file}")
            return
            
        data = json.loads(ontology_file.read_text(encoding="utf-8"))
        entities = data.get("ontology", [])
        
        if not entities:
            logger.warning("Ontology is empty. Nothing to export.")
            return
            
        nodes_path = self.output_dir / "nodes.csv"
        edges_path = self.output_dir / "edges.csv"
        
        self._write_nodes(entities, nodes_path)
        self._write_edges(entities, edges_path)
        
        logger.info(f"GraphRAG export complete. Nodes: {nodes_path}, Edges: {edges_path}")

    def _write_nodes(self, entities: list, out_path: Path):
        headers = ["id", "label", "name", "category", "description", "source_file"]
        
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for i, entity in enumerate(entities):
                # Ensure every entity has a unique ID for Neo4j
                node_id = entity.get("id") or f"NODE_{i}"
                entity["_node_id"] = node_id  # Cache it for edge creation
                
                writer.writerow({
                    "id": node_id,
                    "label": entity.get("type", "Concept"),
                    "name": entity.get("name", ""),
                    "category": entity.get("category", ""),
                    "description": entity.get("description", "").replace("\n", " "),
                    "source_file": entity.get("_source_file", "")
                })

    def _write_edges(self, entities: list, out_path: Path):
        headers = ["source", "target", "type"]
        
        # Build a lookup table from name to node_id to resolve prerequisites
        name_to_id = {e.get("name"): e.get("_node_id") for e in entities if e.get("name")}
        
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for entity in entities:
                source_id = entity.get("_node_id")
                prereqs = entity.get("prerequisites", [])
                
                for prereq_name in prereqs:
                    target_id = name_to_id.get(prereq_name)
                    if target_id:
                        writer.writerow({
                            "source": source_id,
                            "target": target_id,
                            "type": "REQUIRES"
                        })
                    else:
                        # Prerequisite exists outside the current graph or is a soft link
                        writer.writerow({
                            "source": source_id,
                            "target": prereq_name, # Fallback to raw name
                            "type": "REQUIRES_EXTERNAL"
                        })
