"""Admin API schemas."""
from pydantic import BaseModel, Field


class AdminNoteCreate(BaseModel):
    note: str = Field(..., min_length=1, max_length=5000)
