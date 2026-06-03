from typing import Any
from pydantic import BaseModel, Field, ConfigDict

class KnowledgeObject(BaseModel):
    """
    Stage 5: Knowledge Object
    The final, globally merged graph node.
    Complies with lightweight JSON-LD for semantic web and Neo4j injection.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    # JSON-LD Standard Fields
    context: str = Field(default="https://schema.org/", alias="@context")
    id: str = Field(alias="@id", description="Unique global identifier (e.g., MC_0012).")
    type: str = Field(alias="@type", description="The semantic type (e.g., MicroConcept).")
    
    # Core Data
    name: str = Field(description="The globally unique name of the concept.")
    description: str = Field(description="The merged/unified description.")
    category: str = Field(description="The broad category it belongs to.")
    
    # Graph Edges
    prerequisites: list[str] = Field(default_factory=list, description="Edges: Concepts that must be learned first.")
    source_files: list[str] = Field(default_factory=list, description="Provenance: All markdown files where this concept is mentioned.")
