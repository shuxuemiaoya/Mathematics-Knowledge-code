from typing import Literal
from pydantic import BaseModel, Field

class Candidate(BaseModel):
    """
    Stage 4: Candidate
    The raw extraction output from the LLM (DeepSeek). 
    Represents an un-merged, locally extracted concept.
    """
    type: str = Field(description="The entity type (e.g., Concept, MicroConcept, Formula, Theorem).")
    category: Literal["知识点", "题", "思维或技巧", "趣味知识", "数学历史", "定理公式"] = Field(
        description="The strict categorization of the concept."
    )
    name: str = Field(description="The extracted name of the concept.")
    description: str = Field(description="A brief description or definition.")
    prerequisites: list[str] = Field(default_factory=list, description="List of prerequisite concepts.")
    
    # Internal metadata to track provenance during merge
    source_file: str | None = Field(default=None, description="The physical Obsidian file this was extracted from.")
