import os
import json
import logging
from pathlib import Path
from openai import OpenAI
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class GlobalMerger:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required.")
        self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com/v1")

    def collect_candidates(self, vault_dir: str) -> List[Dict[str, Any]]:
        """Scans the vault directory specifically inside *candidates folders and aggregates them."""
        vault_path = Path(vault_dir)
        all_candidates = []
        
        # Only read from the specific directories where DeepSeek outputs were saved
        for candidate_dir in vault_path.iterdir():
            if candidate_dir.is_dir() and candidate_dir.name.endswith("candidates"):
                for json_path in candidate_dir.rglob("*.candidates.json"):
                    try:
                        data = json.loads(json_path.read_text(encoding="utf-8"))
                        if "candidates" in data:
                            for item in data["candidates"]:
                                # Tag each entity with its source file for provenance
                                item["_source_file"] = str(json_path.relative_to(vault_path))
                            all_candidates.extend(data["candidates"])
                    except Exception as e:
                        logger.error(f"Error reading {json_path}: {e}")
                
        logger.info(f"Collected {len(all_candidates)} candidate entities across the vault.")
        return all_candidates

    def merge_concepts(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rule-based merging of mathematical concepts to prevent LLM output truncation on large datasets."""
        if not candidates:
            return {"ontology": []}
            
        logger.info(f"Applying rule-based Map-Reduce to {len(candidates)} candidates...")
        
        merged_dict = {}
        for entity in candidates:
            name = entity.get("name", "").strip()
            if not name:
                continue
                
            if name not in merged_dict:
                merged_dict[name] = {
                    "name": name,
                    "type": entity.get("type", "Concept"),
                    "category": entity.get("category", ""),
                    "description": entity.get("description", ""),
                    "prerequisites": set(entity.get("prerequisites", [])),
                    "_source_file": [entity.get("_source_file", "")]
                }
            else:
                # Merge prerequisites
                merged_dict[name]["prerequisites"].update(entity.get("prerequisites", []))
                
                # Keep the longest description if multiple exist
                new_desc = entity.get("description", "")
                if len(new_desc) > len(merged_dict[name]["description"]):
                    merged_dict[name]["description"] = new_desc
                    
                # Aggregate source files
                src = entity.get("_source_file", "")
                if src and src not in merged_dict[name]["_source_file"]:
                    merged_dict[name]["_source_file"].append(src)
                    
        # Convert sets back to lists and format source files
        final_ontology = []
        for name, data in merged_dict.items():
            data["prerequisites"] = list(data["prerequisites"])
            # We pick the primary source file for the canvas rendering (or we can leave it as a list, but canvas builder expects a string)
            # Let's keep it as the first one for backwards compatibility with the canvas builder
            data["_source_file"] = data["_source_file"][0] if data["_source_file"] else ""
            final_ontology.append(data)
            
        logger.info(f"Consolidated into {len(final_ontology)} unique concepts.")
        return {"ontology": final_ontology}

    def run_pipeline(self, vault_dir: str, output_path: str):
        candidates = self.collect_candidates(vault_dir)
        merged_ontology = self.merge_concepts(candidates)
        
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(merged_ontology, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Successfully saved global ontology to {out_file}")
