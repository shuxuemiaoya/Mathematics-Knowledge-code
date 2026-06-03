from pydantic import BaseModel, Field

class Chunk(BaseModel):
    """
    Stage 2: Chunk
    The output of the text parser. Represents a logical block of markdown text.
    """
    title: str = Field(description="The heading or title of the text chunk.")
    content: str = Field(description="The raw markdown content belonging to this chunk.")
    level: int = Field(default=1, description="The heading level (e.g., 1 for H1).")
