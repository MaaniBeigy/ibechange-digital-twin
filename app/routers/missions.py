from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.dependencies import get_db
from app.models.mission import Mission
from app.schemas.mission import MissionList

router = APIRouter(prefix="/missions", tags=["Missions"])


@router.post("/", response_model=MissionList)
def create_missions(missions: MissionList, db: Session = Depends(get_db)):
    for mission in missions.missions:
        existing_mission = db.exec(
            select(Mission).where(Mission.mission_id == mission.mission_id)
        ).first()
        if existing_mission:
            continue
        db_mission = Mission(**mission.model_dump())
        db.add(db_mission)
    db.commit()
    return missions
