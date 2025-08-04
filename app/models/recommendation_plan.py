import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey
from sqlmodel import Field, SQLModel


class RecommendationPlan(SQLModel, table=True):
    __tablename__ = "RecommendationPlan"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(index=True, foreign_key="User.id")
    plan_id: uuid.UUID = Field(index=True, foreign_key="SelectedContent.id")
    recommendation_id: uuid.UUID = Field(index=True, foreign_key="Recommendation.id")
    mission_id: Optional[uuid.UUID] = Field(
        default=None, index=True, foreign_key="Mission.id"
    )
    scheduled_for: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)
