from typing import List

from pydantic import BaseModel


class RecommendationCreate(BaseModel):
    content_id: str
    content_type: str
    missions: List[str]
    objective: List[str]
    hapa: List[str]
    comb: List[str]
    intervention_type: List[str]


class RecommendationList(BaseModel):
    recommendations: List[RecommendationCreate]
