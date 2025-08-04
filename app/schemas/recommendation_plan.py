from datetime import datetime
from typing import Dict, List
from uuid import UUID

from pydantic import BaseModel


class RecommendationPlanItem(BaseModel):
    content_id: str
    scheduled_for: datetime
    plan_id: UUID


class RecommendationPlanResponse(BaseModel):
    user_id: UUID
    plans: List[RecommendationPlanItem]


class RecommendationPlanList(BaseModel):
    recommendation_plans: List[RecommendationPlanResponse]
