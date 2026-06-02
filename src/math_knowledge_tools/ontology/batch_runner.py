import os
import json
import logging
from pathlib import Path
from .extractor import DeepSeekExtractor

logger = logging.getLogger(__name__)

class OntologyBatchRunner:
    def __init__(self, vault_dir: str, extractor: DeepSeekExtractor):
        self.vault_dir = Path(vault_dir)
        self.extractor = extractor
        
    def run(self):
        for root, dirs, files in os.walk(self.vault_dir):
            for file in files:
                if not file.endswith(".md"):
                    continue
                # Skip files named 【人教版】*.md
                if file.startswith("【人教版】"):
                    continue
                
                md_path = Path(root) / file
                json_path = md_path.with_suffix(".candidates.json")
                
                if json_path.exists():
                    logger.debug(f"Skipping {md_path}, candidates JSON already exists.")
                    continue
                
                logger.info(f"Processing {md_path}")
                try:
                    content = md_path.read_text(encoding="utf-8")
                    result = self.extractor.extract(content)
                    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info(f"Successfully saved candidates to {json_path}")
                except Exception as e:
                    logger.error(f"Error processing {md_path}: {e}")
