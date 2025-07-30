import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class SimulationClock(SQLModel, table=True):
    __tablename__ = "SimulationClock"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    start_timestamp: datetime
    end_timestamp: datetime
    recipe: Dict[str, Any] = Field(sa_type=JSONB)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)

    # ToDO: needs cleaning up; will be imported from private repo
