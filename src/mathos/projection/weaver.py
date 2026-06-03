import os
import re
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class KnowledgeWeaver:
    def __init__(self, ontology_path: str):
        self.ontology_path = Path(ontology_path)
        self.concepts = self._load_concepts()
        # Regex to capture protected blocks: Code blocks, block math, inline math, existing wikilinks
        self.protected_pattern = re.compile(
            r'(```.*?```|\$\$.*?\$\$|\$.*?\$|\[\[.*?\]\])',
            flags=re.DOTALL
        )

    def _load_concepts(self) -> list:
        if not self.ontology_path.exists():
            logger.warning(f"Ontology file not found: {self.ontology_path}")
            return []
            
        data = json.loads(self.ontology_path.read_text(encoding="utf-8"))
        entities = data.get("ontology", [])
        
        # Extract names and sort by length descending to match longest phrases first
        names = set()
        for e in entities:
            name = e.get("name", "").strip()
            if name and len(name) >= 2: # Ignore single character concepts to prevent excessive false positives
                names.add(name)
                
        # Sort descending by length
        sorted_names = sorted(list(names), key=len, reverse=True)
        logger.info(f"Loaded {len(sorted_names)} valid concepts for weaving.")
        return sorted_names

    def weave_vault(self, vault_dir: str):
        vault_path = Path(vault_dir)
        processed_count = 0
        
        for md_path in vault_path.rglob("*.md"):
            # Skip original textbook files if they are in the vault
            if md_path.name.startswith("【人教版】"):
                continue
                
            try:
                content = md_path.read_text(encoding="utf-8")
                new_content = self.weave_text(content)
                
                if new_content != content:
                    md_path.write_text(new_content, encoding="utf-8")
                    processed_count += 1
            except Exception as e:
                logger.error(f"Failed to weave {md_path}: {e}")
                
        logger.info(f"Weaving complete. Modified {processed_count} files.")

    def weave_text(self, text: str) -> str:
        if not self.concepts:
            return text
            
        # Keep track of concepts already injected to guarantee "Once per file"
        injected_concepts = set()
        
        # Split text into protected and unprotected segments
        parts = self.protected_pattern.split(text)
        
        # Parts will alternate: [unprotected, protected, unprotected, protected, ...]
        for i in range(0, len(parts), 2):
            unprotected_text = parts[i]
            
            # For each concept, attempt replacement if not already injected
            for concept in self.concepts:
                if concept in injected_concepts:
                    continue
                    
                # Find the concept in the unprotected text
                # We use word boundary matching if it's English, but for Chinese we just use string replacement
                # Because we want to only inject ONCE per file, we replace with count=1
                if concept in unprotected_text:
                    # To avoid replacing inside words if necessary, we could do more complex checks,
                    # but pure Chinese strings generally don't suffer from word boundary issues.
                    # We do a single replacement.
                    unprotected_text = unprotected_text.replace(concept, f"[[{concept}]]", 1)
                    injected_concepts.add(concept)
                    
            parts[i] = unprotected_text
            
        # Rejoin all parts
        return "".join(parts)
