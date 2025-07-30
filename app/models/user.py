import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "User"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    characteristics: Dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)
    is_virtual: bool = Field(default=False)

    def deleteUser(self, date_disabled: datetime):
        self.is_deleted = True
        self.deleted_at = date_disabled


class UserPersona(SQLModel, table=True):
    __tablename__ = "UserPersona"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(index=True, foreign_key="User.id")
    persona_id: uuid.UUID = Field(index=True, foreign_key="Persona.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)


class HealthHabitAssessment(SQLModel, table=True):
    __tablename__ = "HealthHabitAssessment"
    __table_args__ = (Index("ix_user_timestamp", "user_id", "assessment_timestamp"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(index=True, foreign_key="User.id")
    hhs: Dict = Field(sa_type=JSONB)
    assessment_timestamp: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(datetime.timezone.utc)
    )
    modified_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)


class MissionContent(SQLModel, table=True):
    __tablename__ = "MissionContent"
    __table_args__ = (Index("ix_user_mission", "user_id", "mission_id", unique=True),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(index=True, foreign_key="User.id")
    selection_timestamp: Optional[datetime] = Field(default=None)
    mission_id: uuid.UUID = Field(index=True, foreign_key="Mission.id")
    mission_start_time: Optional[datetime] = Field(default=None)
    mission_end_time: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)
