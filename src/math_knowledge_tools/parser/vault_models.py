from typing import List, Optional
from pydantic import BaseModel, Field

class ObsidianNode(BaseModel):
    title: str
    content: str = ""
    category: str
    links: list[str] = Field(default_factory=list)
    
    def add_link(self, target_title: str) -> None:
        if target_title not in self.links:
            self.links.append(target_title)
            
    def to_markdown(self) -> str:
        lines = []
        if self.title:
            lines.append(f"# {self.title}\n")
        if self.content:
            lines.append(f"{self.content}\n")
        if self.links:
            lines.append("## 下级链接\n")
            for link in self.links:
                lines.append(f"- [[{link}]]")
        return "\n".join(lines)
