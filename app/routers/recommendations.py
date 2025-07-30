from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.dependencies import get_db
from app.models.recommendation import Recommendation
from app.schemas.recommendation import RecommendationList

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.post("/", response_model=RecommendationList)
def create_recommendations(
    recommendations: RecommendationList, db: Session = Depends(get_db)
):
    for rec in recommendations.recommendations:
        existing_rec = db.exec(
            select(Recommendation).where(Recommendation.content_id == rec.content_id)
        ).first()
        if existing_rec:
            continue
        db_rec = Recommendation(**rec.model_dump())
        db.add(db_rec)
    db.commit()
    return recommendations
