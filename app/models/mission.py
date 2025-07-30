import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Mission(SQLModel, table=True):
    __tablename__ = "Mission"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    mission_id: str = Field(unique=True, index=True)
    weekly_frequency: Optional[int] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)
