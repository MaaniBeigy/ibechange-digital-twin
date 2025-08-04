from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel


class ContentItem(BaseModel):
    id: str
    type: str
    mission_id: str


class SelectedContentCreate(BaseModel):
    plan_id: UUID
    contents: List[ContentItem]
    mission_start_time: Optional[datetime]
    mission_end_time: Optional[datetime]


class SelectedContentList(BaseModel):
    selected_contents: Dict[str, SelectedContentCreate]
