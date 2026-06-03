from pydantic import BaseModel, Field

class AtomicNote(BaseModel):
    """
    Stage 3: Atomic Note
    The output of the Vault Builder. Represents a physical file in the Obsidian vault.
    Carries the physical nested hierarchy to preserve the tree topology.
    """
    title: str = Field(description="The filename or title of the note.")
    content: str = Field(default="", description="The markdown content of the note.")
    hierarchy: list[str] = Field(default_factory=list, description="The parent directory path as a list (RKDT topology).")
    links: list[str] = Field(default_factory=list, description="Explicit wikilinks contained within the note.")
    
    def add_link(self, target_title: str) -> None:
        if target_title not in self.links:
            self.links.append(target_title)
