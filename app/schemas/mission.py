from typing import List

from pydantic import BaseModel


class MissionCreate(BaseModel):
    mission_id: str
    weekly_frequency: int


class MissionList(BaseModel):
    missions: List[MissionCreate]
