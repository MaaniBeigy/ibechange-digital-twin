import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from dotenv import load_dotenv
from sqlalchemy import select
from sqlmodel import Session

from app.models.mission import Mission
from app.models.recommendation import Recommendation
from app.models.recommendation_plan import RecommendationPlan
from app.utils.scheduling import generate_random_schedule

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def generate_recommendation_plan(
    user_id: uuid.UUID,
    content_missions: dict,
    start_time: datetime,
    end_time: datetime,
    db: Session,
) -> List[RecommendationPlan]:
    mode = os.getenv("MODE", "test")
    plans = []

    if mode != "test":
        # ToDO: needs cleaning up; will be imported from private repo
        return plans

    # Load constraints
    min_per_day = int(os.getenv("MIN_NOTIFICATIONS_PER_DAY", 1))
    max_per_day = int(os.getenv("MAX_NOTIFICATIONS_PER_DAY", 5))
    min_per_week = int(os.getenv("MIN_NOTIFICATIONS_PER_WEEK", 5))
    max_per_week = int(os.getenv("MAX_NOTIFICATIONS_PER_WEEK", 20))
    cooldown_minutes = int(os.getenv("BETWEEN_NOTIFICATION_COOLDOWN", 180))

    now = datetime.now(timezone.utc)

    # ----------------------------- Check cooldown window -----------------------------
    cooldown_cutoff = now - timedelta(minutes=cooldown_minutes)
    recent_plan = db.exec(
        select(RecommendationPlan)
        .where(RecommendationPlan.user_id == user_id)
        .where(RecommendationPlan.scheduled_for >= cooldown_cutoff)
        .where(RecommendationPlan.scheduled_for <= now)
        .where(RecommendationPlan.is_deleted == False)
    ).first()
    if recent_plan:
        # Skip if the last recommendation is too recent
        return []

    # ----------------------- Fetch existing plans in the window ----------------------
    existing_plans = db.exec(
        select(RecommendationPlan)
        .where(RecommendationPlan.user_id == user_id)
        .where(RecommendationPlan.scheduled_for >= start_time)
        .where(RecommendationPlan.scheduled_for <= end_time)
        .where(RecommendationPlan.is_deleted == False)
    ).all()

    existing_schedule = [p.scheduled_for for p in existing_plans]
    existing_by_day = {}

    total_existing = len(existing_schedule)
    total_days = (end_time.date() - start_time.date()).days + 1
    total_needed = max(min_per_week, min(max_per_week, max_per_day * total_days))
    remaining = max(0, total_needed - total_existing)

    if remaining == 0:
        return []

    # --------------------------- Generate fresh candidates ---------------------------
    cooldown_delta = timedelta(minutes=cooldown_minutes)
    all_schedules = generate_random_schedule(start_time, end_time)
    new_schedules = []
    scheduled_times = set(existing_schedule)  # existing times in window

    for scheduled_time in all_schedules:
        # Check cooldown against existing + already scheduled
        too_close = any(
            abs((scheduled_time - t).total_seconds()) < cooldown_delta.total_seconds()
            for t in scheduled_times
        )
        if too_close:
            continue

        day = scheduled_time.date()
        if existing_by_day.get(day, 0) < max_per_day:
            new_schedules.append(scheduled_time)
            scheduled_times.add(scheduled_time)
            existing_by_day[day] = existing_by_day.get(day, 0) + 1

        if len(new_schedules) >= remaining:
            break

    # -------------------------------- Assign schedules -------------------------------
    recommendation_lookup = {
        r.content_id: r.id
        for r in db.exec(
            select(Recommendation).where(Recommendation.is_deleted == False)
        )
        .scalars()
        .all()
    }

    for (content_id, mission_id_str), scheduled_time in zip(
        content_missions.items(), new_schedules
    ):
        recommendation_uuid = recommendation_lookup.get(content_id)

        mission_obj = (
            db.exec(
                select(Mission).where(
                    Mission.mission_id == mission_id_str,
                    Mission.is_deleted == False,
                )
            )
            .scalars()
            .first()
        )
        mission_uuid = mission_obj.id if mission_obj else None

        plan = RecommendationPlan(
            user_id=user_id,
            recommendation_id=recommendation_uuid,
            mission_id=mission_uuid,
            scheduled_for=scheduled_time,
        )
        db.add(plan)
        plans.append(plan)

    return plans
