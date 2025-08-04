from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, join, select

from app.dependencies import get_db
from app.models.recommendation_plan import RecommendationPlan
from app.models.recommendation import Recommendation
from app.models.selected_content import SelectedContent
from app.schemas.recommendation_plan import (
    RecommendationPlanItem,
    RecommendationPlanList,
    RecommendationPlanResponse,
)
from app.services.recommendation_plan_service import generate_recommendation_plan

router = APIRouter(prefix="/recommendation_plans", tags=["Recommendation Plans"])


@router.get("/", response_model=RecommendationPlanList)
def get_recommendation_plans(
    start_time: str = Query(...),
    end_time: str = Query(...),
    db: Session = Depends(get_db),
):
    # Parse the input start and end times from ISO format
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)
    except ValueError:
        # Return 422 if the datetime format is invalid
        raise HTTPException(status_code=422, detail="Invalid datetime format")

    # Query for existing recommendation plans in the given time range
    stmt = (
        select(RecommendationPlan, Recommendation)
        .join(Recommendation, Recommendation.id == RecommendationPlan.recommendation_id)
        .where(RecommendationPlan.scheduled_for >= start_dt)
        .where(RecommendationPlan.scheduled_for <= end_dt)
        .where(RecommendationPlan.is_deleted == False)
    )

    results = db.exec(stmt).all()

    if results:
        # If plans exist, group them by user_id and format the response
        user_plans = {}
        for plan, rec in results:
            if plan.user_id not in user_plans:
                user_plans[plan.user_id] = []
            user_plans[plan.user_id].append(
                RecommendationPlanItem(
                    content_id=rec.content_id,
                    scheduled_for=plan.scheduled_for,
                    plan_id=plan.plan_id,
                )
            )
        # Build the response as a list of RecommendationPlanResponse objects
        response = [
            RecommendationPlanResponse(user_id=user_id, plans=items)
            for user_id, items in user_plans.items()
        ]
        return RecommendationPlanList(recommendation_plans=response)

    # If no plans exist, generate new plans
    # Fetch all non-deleted SelectedContents
    selected_contents = db.exec(
        select(SelectedContent).where(SelectedContent.is_deleted == False)
    ).all()

    new_plans = []
    for content in selected_contents:
        # Extract content_id -> mission_id mapping from list of dicts in SelectedContent
        content_missions = {c["id"]: c["mission_id"] for c in content.contents}
        # Generate recommendation plans for each user/content
        new_plans += generate_recommendation_plan(
            content.user_id, content_missions, content.id, start_dt, end_dt, db
        )

    # Commit all new plans to the database
    db.commit()

    # Format the response for the newly created plans
    user_plans = {}
    recommendation_ids = [p.recommendation_id for p in new_plans]
    recommendation_map = {
        r.id: r.content_id
        for r in db.exec(
            select(Recommendation).where(Recommendation.id.in_(recommendation_ids))
        ).all()
    }
    for plan in new_plans:
        if plan.user_id not in user_plans:
            user_plans[plan.user_id] = []
        content_id = recommendation_map.get(plan.recommendation_id)
        user_plans[plan.user_id].append(
            RecommendationPlanItem(
                content_id=content_id,
                scheduled_for=plan.scheduled_for,
                plan_id=plan.plan_id,
            )
        )
    response = [
        RecommendationPlanResponse(user_id=user_id, plans=items)
        for user_id, items in user_plans.items()
    ]
    return RecommendationPlanList(recommendation_plans=response)
