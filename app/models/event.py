import uuid
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, Field, SQLModel


class Event(SQLModel, table=True):
    __tablename__ = "Event"

    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: UUID = Field(index=True, foreign_key="User.id")
    event_name: str
    event_start_time: datetime
    event_end_time: Optional[datetime] = Field(default=None)
    characteristics: Dict = Field(sa_type=JSONB)
    process_id: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)
    is_virtual: bool = Field(default=False)
