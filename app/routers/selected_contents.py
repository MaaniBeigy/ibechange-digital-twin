import logging
from datetime import datetime, timezone
from typing import Dict, Set, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.dependencies import get_db
from app.models.mission import Mission
from app.models.recommendation import Recommendation
from app.models.selected_content import SelectedContent
from app.models.user import User
from app.schemas.selected_content import SelectedContentCreate, SelectedContentList

router = APIRouter(prefix="/selected_contents", tags=["Selected Contents"])

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@router.post("/", response_model=dict)
def create_selected_contents(
    selected_contents: Dict[str, SelectedContentCreate],
    db: Session = Depends(get_db),
):
    with db.no_autoflush:  # Disable autoflush for the entire operation
        for user_id, content in selected_contents.items():
            logger.debug(f"Processing user_id: {user_id}")

            # Check if user exists, create if not
            existing_user = db.exec(select(User).where(User.id == user_id)).first()
            if not existing_user:
                logger.debug(f"Creating new user with user_id: {user_id}")
                db_user = User(
                    id=user_id,
                    created_at=datetime.now(timezone.utc),
                    is_deleted=False,
                )
                db.add(db_user)
                db.flush()  # Ensure user is persisted before referencing
                logger.debug(f"User {user_id} created and flushed")
            else:
                logger.debug(f"User {user_id} already exists")

            # Fetch existing SelectedContent for this user
            user_contents = db.exec(
                select(SelectedContent).where(SelectedContent.user_id == user_id)
            ).all()

            # Deduplicate contents by content_id
            unique_contents_dict = {}
            for c in content.contents:
                # If the same content_id already seen, skip
                if c.id not in unique_contents_dict:
                    unique_contents_dict[c.id] = c
            unique_contents = list(unique_contents_dict.values())

            def _naive_utc(dt: datetime | None) -> datetime | None:
                """Strip tzinfo after converting to UTC so DB / JSON timestamps match."""
                if dt is None:
                    return None
                return dt.astimezone(timezone.utc).replace(tzinfo=None)

            def _canonical_contents(raw: list[dict]) -> list[dict]:
                """Sort by content_id so order differences don’t matter."""
                return sorted(raw, key=lambda x: x["id"])

            incoming_contents = [c.model_dump() for c in unique_contents]
            canonical_incoming = _canonical_contents(incoming_contents)
            start_naive = _naive_utc(content.mission_start_time)
            end_naive = _naive_utc(content.mission_end_time)
            # Check if SelectedContent with same contents and times already exists
            already_exists = any(
                _canonical_contents(sc.contents) == canonical_incoming
                and _naive_utc(sc.mission_start_time) == start_naive
                and _naive_utc(sc.mission_end_time) == end_naive
                and not sc.is_deleted
                for sc in user_contents
            )
            if already_exists:
                logger.debug(
                    f"SelectedContent already exists for user {user_id}, skipping"
                )
                continue

            # Insert new SelectedContent
            db_content = SelectedContent(
                user_id=user_id,
                contents=[c.model_dump() for c in unique_contents],
                mission_start_time=content.mission_start_time,
                mission_end_time=content.mission_end_time,
                created_at=datetime.now(timezone.utc),
                is_deleted=False,
            )
            db.add(db_content)
            logger.debug(f"Added SelectedContent for user {user_id}")

            # Collect unique mission_ids
            mission_ids: Set[str] = {c.mission_id for c in unique_contents}
            logger.debug(f"Unique mission_ids: {mission_ids}")

            # Process Recommendations and Missions
            for c in unique_contents:
                existing_recommendation = db.exec(
                    select(Recommendation).where(
                        Recommendation.content_id == c.id,
                        Recommendation.is_deleted == False,
                    )
                ).first()
                if not existing_recommendation:
                    db_recommendation = Recommendation(
                        content_id=c.id,
                        content_type=c.type.lower(),
                        missions=[c.mission_id],
                        objective=[],
                        hapa=[],
                        comb=[],
                        intervention_type=[],
                        created_at=datetime.now(timezone.utc),
                        is_deleted=False,
                    )
                    db.add(db_recommendation)
                    logger.debug(f"Created new Recommendation for content_id: {c.id}")
                else:
                    # Update missions field if mission_id not present
                    if c.mission_id not in existing_recommendation.missions:
                        # reassignment so SQLAlchemy notices the change
                        existing_recommendation.missions = (
                            existing_recommendation.missions + [c.mission_id]
                        )
                        logger.debug(
                            f"Updated Recommendation missions for content_id: {c.id}"
                        )

            # Check/create Missions for unique mission_ids
            for mission_id in mission_ids:
                existing_mission = db.exec(
                    select(Mission).where(
                        Mission.mission_id == mission_id,
                        Mission.is_deleted == False,
                    )
                ).first()
                if not existing_mission:
                    db_mission = Mission(
                        mission_id=mission_id,
                        created_at=datetime.now(timezone.utc),
                        is_deleted=False,
                    )
                    db.add(db_mission)
                    logger.debug(f"Created new Mission with mission_id: {mission_id}")
                else:
                    logger.debug(f"Mission {mission_id} already exists")

        db.commit()
        logger.debug("Committed all changes")
    return selected_contents
