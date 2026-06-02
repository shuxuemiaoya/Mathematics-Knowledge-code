from typing import Dict, Any

class Categorizer:
    def __init__(self):
        # Mappings based on user specification
        self.callout_map = {
            "example": "题",
            "think": "思维或技巧",
            "observe": "思维或技巧",
            "explore": "思维或技巧"
        }
    
    def categorize(self, chunk: Dict[str, Any]) -> str:
        """
        Categorizes a chunk into one of the 6 physical directories:
        知识点, 题, 思维或技巧, 趣味知识, 数学历史, 定理公式
        """
        chunk_type = chunk.get("type")
        
        if chunk_type == "callout":
            callout_type = chunk.get("callout_type", "")
            return self.callout_map.get(callout_type, "知识点")
            
        # Default text blocks and H1/H2/H3 nodes are Knowledge Points
        return "知识点"
