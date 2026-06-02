from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class Citation(BaseModel):
    page: int | None = None
    text_quote: str

class BaseKnowledgeObject(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="@id")
    type: str = Field(alias="@type")
    title: str
    parent: str | None = None  # Strict parent linkage, no grandparent
    content: str
    citations: list[Citation] = Field(default_factory=list)
    
    # Lateral relations for KAG
    prerequisites: list[str] = Field(default_factory=list)
    used_by: list[str] = Field(default_factory=list)
    ideas: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)

class Concept(BaseKnowledgeObject):
    type: Literal["Concept"] = Field(default="Concept", alias="@type")

class Statement(BaseKnowledgeObject):
    type: Literal["Statement"] = Field(default="Statement", alias="@type")

class MicroConcept(BaseKnowledgeObject):
    type: Literal["MicroConcept"] = Field(default="MicroConcept", alias="@type")

class Problem(BaseKnowledgeObject):
    type: Literal["Problem"] = Field(default="Problem", alias="@type")
