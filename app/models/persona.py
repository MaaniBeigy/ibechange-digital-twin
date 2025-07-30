import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, Field, SQLModel


class Persona(SQLModel, table=True):
    __tablename__ = "Persona"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    characteristics: Dict[str, Any] = Field(sa_type=JSONB)
    models: Optional[List[uuid.UUID]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)
    is_virtual: bool = Field(default=False)
