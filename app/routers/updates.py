import json
import logging
from datetime import datetime, timezone
from typing import Dict, Set
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session, select

from app.dependencies import get_db
from app.models.escalation_level import EscalationLevel
from app.models.event import Event
from app.models.mission import Mission
from app.models.recommendation import Recommendation
from app.models.user import HealthHabitAssessment, MissionContent, User
from app.schemas.update import UpdateCreate

router = APIRouter(prefix="/updates", tags=["Updates"])

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@router.post("/", response_model=UpdateCreate)
def create_updates(updates: UpdateCreate, db: Session = Depends(get_db)):
    with db.no_autoflush:
        # Collect all user_ids from all sections of the payload
        user_ids: Set[str] = set()
        user_ids.update(updates.new_users.keys())
        user_ids.update(updates.disabled_users.keys())
        user_ids.update(updates.user_feedback.keys())
        user_ids.update(updates.health_habit_assessments.keys())
        user_ids.update(updates.new_missions_and_contents.keys())
        user_ids.update(getattr(updates, "escalation_level", {}).keys())

        # Create missing users
        for user_id in user_ids:
            existing_user = db.exec(select(User).where(User.id == user_id)).first()
            if not existing_user:
                logger.debug(f"Creating new user with user_id: {user_id}")
                # Access characteristics directly from NewUser object or use empty dict
                new_user = updates.new_users.get(user_id)
                characteristics = new_user.model_dump() if new_user else {}
                db_user = User(
                    id=UUID(user_id),
                    characteristics=characteristics,
                    created_at=datetime.now(timezone.utc),
                    is_deleted=False,
                )
                db.add(db_user)
        db.flush()
        logger.debug("All users created and flushed")

        # ------------------------ COLLECT AND INSERT MISSIONS ------------------------
        mission_ids: Set[str] = set()

        # From new_missions_and_contents
        for nmc in updates.new_missions_and_contents.values():
            for mission in nmc.new_missions:
                if hasattr(mission, "mission"):
                    mission_ids.add(mission.mission)

        # From user_feedback (event.properties.mission_id)
        for feedback in updates.user_feedback.values():
            for event in feedback.events:
                props = event.properties
                if isinstance(props, dict) and "mission_id" in props:
                    mission_ids.add(props["mission_id"])

        # Insert missing Missions
        for m_id in mission_ids:
            existing = db.exec(
                select(Mission).where(
                    Mission.mission_id == m_id,
                    Mission.is_deleted == False,
                )
            ).first()
            if not existing:
                db_mission = Mission(
                    mission_id=m_id,
                    created_at=datetime.now(timezone.utc),
                    is_deleted=False,
                )
                db.add(db_mission)
                logger.debug(f"Created new Mission with mission_id: {m_id}")

        db.flush()

        # --------------- COLLECT AND INSERT RECOMMENDATIONS + RESOURCES --------------
        content_id_type_map: Dict[str, str] = {}  # Maps content_id → content_type
        mission_content_links: Dict[str, Set[str]] = {}  # Maps content_id → mission_ids

        # From new_missions_and_contents
        for nmc in updates.new_missions_and_contents.values():
            for mission in nmc.new_missions:
                mission_id = getattr(mission, "mission", None)
                if mission_id:
                    for rec_id in getattr(mission, "recommendations", []):
                        content_id_type_map[rec_id] = "recommendation"
                        mission_content_links.setdefault(rec_id, set()).add(mission_id)
                    for res_id in getattr(mission, "resources", []):
                        content_id_type_map[res_id] = "resource"
                        mission_content_links.setdefault(res_id, set()).add(mission_id)

        # From user_feedback
        for feedback in updates.user_feedback.values():
            for event in feedback.events:
                props = event.properties
                if isinstance(props, dict):
                    content_id = props.get("content_id")
                    content_type = props.get(
                        "content_type"
                    )  # "recommendation" or "resource"
                    mission_id = props.get("mission_id")

                    if content_id and content_type:
                        content_id_type_map[content_id] = content_type
                        if mission_id:
                            mission_content_links.setdefault(content_id, set()).add(
                                mission_id
                            )

        # Insert missing Recommendations and Resources
        for content_id, content_type in content_id_type_map.items():
            existing = db.exec(
                select(Recommendation).where(
                    Recommendation.content_id == content_id,
                    Recommendation.is_deleted == False,
                )
            ).first()

            linked_missions = list(mission_content_links.get(content_id, []))

            if not existing:
                db_rec = Recommendation(
                    content_id=content_id,
                    content_type=content_type.lower(),
                    missions=linked_missions,
                    objective=[],
                    hapa=[],
                    comb=[],
                    intervention_type=[],
                    created_at=datetime.now(timezone.utc),
                    is_deleted=False,
                )
                db.add(db_rec)
                logger.debug(
                    f"Created new {content_type} with content_id: {content_id}"
                )
            else:
                to_add = [
                    m_id for m_id in linked_missions if m_id not in existing.missions
                ]
                if to_add:
                    existing.missions = existing.missions + to_add
                    db.add(existing)
                    logger.debug(
                        "Updated missions for existing "
                        + f"{content_type} with content_id: {content_id}"
                    )

        db.flush()
        logger.debug(
            "Flushed DB after inserting Missions, Recommendations, and Resources"
        )

        # Handle disabled users
        for user_id, disable_info in updates.disabled_users.items():
            user = db.exec(select(User).where(User.id == user_id)).first()
            if user:
                date_disabled = disable_info.get("date_disabled")
                user.deleteUser(date_disabled)
                db.add(user)
                logger.debug(f"Disabled user {user_id}")
        # Handle user feedback
        for user_id, feedback in updates.user_feedback.items():
            for e in feedback.events:
                event_start_time = e.timestamp
                props_json = json.loads(json.dumps(e.properties, sort_keys=True))
                user_uuid = UUID(user_id)

                # Check for existing event with same user, name, and start time
                existing_event = db.exec(
                    select(Event).where(
                        Event.user_id == user_uuid,
                        Event.event_name == e.event_name,
                        Event.event_start_time == event_start_time,
                        Event.is_deleted == False,
                    )
                ).first()

                if existing_event:
                    # If characteristics differ, update them
                    if existing_event.characteristics != props_json:
                        existing_event.characteristics = props_json
                        existing_event.modified_at = datetime.now(timezone.utc)
                        db.add(existing_event)
                        logger.debug(
                            f"Updated Event for user {user_id} at {event_start_time}"
                        )
                    else:
                        logger.debug(
                            "Skipped duplicate Event for user "
                            + f"{user_id} at {event_start_time}"
                        )
                else:
                    db_event = Event(
                        user_id=user_uuid,
                        process_id=e.process_id,
                        event_name=e.event_name,
                        event_start_time=event_start_time,
                        event_end_time=getattr(e, "end_timestamp", event_start_time),
                        characteristics=props_json,
                    )
                    db.add(db_event)
                    logger.debug(
                        f"Added new Event for user {user_id} at {event_start_time}"
                    )

        db.flush()
        logger.debug("Flushed DB after inserting user feedback")
        # Handle health habit assessments
        for user_id, hha_list in updates.health_habit_assessments.items():
            user_uuid = UUID(user_id)
            for assessment in hha_list:
                assessment_ts = assessment.assessment_timestamp
                hhs_dict = json.loads(json.dumps(assessment.hhs, sort_keys=True))

                # Look for an existing assessment with the same timestamp
                existing = db.exec(
                    select(HealthHabitAssessment).where(
                        HealthHabitAssessment.user_id == user_uuid,
                        HealthHabitAssessment.assessment_timestamp == assessment_ts,
                        HealthHabitAssessment.is_deleted == False,
                    )
                ).first()

                if existing:
                    # If the hhs differs, update
                    if existing.hhs != hhs_dict:
                        existing.hhs = hhs_dict
                        existing.modified_at = datetime.now(timezone.utc)
                        db.add(existing)
                        logger.debug(
                            "Updated HealthHabitAssessment for "
                            + f"user {user_id} at {assessment_ts}"
                        )
                    else:
                        logger.debug(
                            "Skipped duplicate HealthHabitAssessment for "
                            + f"user {user_id} at {assessment_ts}"
                        )
                else:
                    # New assessment
                    db_hha = HealthHabitAssessment(
                        user_id=user_uuid,
                        hhs=hhs_dict,
                        assessment_timestamp=assessment_ts,
                        created_at=datetime.now(timezone.utc),
                        is_deleted=False,
                    )
                    db.add(db_hha)
                    logger.debug(
                        "Added new HealthHabitAssessment for "
                        + f"user {user_id} at {assessment_ts}"
                    )

        db.flush()
        logger.debug("Flushed DB after inserting health habit assessments")

        # Handle new missions and contents
        processed_user_mission = {}

        for user_id, nmc in updates.new_missions_and_contents.items():
            # sort by selection_timestamp (oldest first)
            sorted_missions = sorted(
                nmc.new_missions, key=lambda m: m.selection_timestamp
            )
            for mission in nmc.new_missions:
                mission_obj = db.exec(
                    select(Mission).where(
                        Mission.mission_id == mission.mission,
                        Mission.is_deleted == False,
                    )
                ).first()

                user_mission_key = (user_id, mission_obj.id)

                # Check if this user/mission combo is already processed in this batch
                if user_mission_key in processed_user_mission:
                    existing_mc = processed_user_mission[user_mission_key]
                else:
                    existing_mc = db.exec(
                        select(MissionContent).where(
                            MissionContent.user_id == UUID(user_id),
                            MissionContent.mission_id == mission_obj.id,
                            MissionContent.is_deleted == False,
                        )
                    ).first()
                    if existing_mc:
                        processed_user_mission[user_mission_key] = existing_mc

                if existing_mc:
                    # Only update if timestamps have changed
                    if (
                        existing_mc.mission_start_time != mission.selection_timestamp
                        or existing_mc.mission_end_time != mission.finish_timestamp
                        or existing_mc.selection_timestamp
                        != mission.selection_timestamp
                    ):
                        existing_mc.selection_timestamp = mission.selection_timestamp
                        existing_mc.mission_start_time = mission.selection_timestamp
                        existing_mc.mission_end_time = mission.finish_timestamp
                        existing_mc.modified_at = datetime.now(timezone.utc)
                        db.add(existing_mc)
                        logger.debug(
                            "Updated MissionContent for user "
                            + f"{user_id}, mission {mission.mission}"
                        )
                    else:
                        logger.debug(
                            "Skipped duplicate MissionContent for "
                            + f"user {user_id}, mission {mission.mission}"
                        )
                else:
                    # New mission content
                    db_nmc = MissionContent(
                        user_id=UUID(user_id),
                        selection_timestamp=mission.selection_timestamp,
                        mission_id=mission_obj.id,
                        mission_start_time=mission.selection_timestamp,
                        mission_end_time=mission.finish_timestamp,
                        created_at=datetime.now(timezone.utc),
                        is_deleted=False,
                    )
                    db.add(db_nmc)
                    processed_user_mission[user_mission_key] = db_nmc
                    logger.debug(
                        "Created new MissionContent for user "
                        + f"{user_id}, mission {mission.mission}"
                    )

        db.flush()
        logger.debug("Flushed DB after inserting new missions and contents")
        # Handle escalation levels
        escalation_levels = getattr(updates, "escalation_level", {})
        for user_id, levels in escalation_levels.items():
            user_uuid = UUID(user_id)
            for level_info in levels:
                exists = db.exec(
                    select(EscalationLevel).where(
                        EscalationLevel.user_id == user_uuid,
                        EscalationLevel.update_timestamp == level_info.update_timestamp,
                        EscalationLevel.level == level_info.level,
                        EscalationLevel.pillar_id == level_info.pillar_id,
                        EscalationLevel.is_deleted == False,
                    )
                ).first()

                if exists:
                    logger.debug(
                        "Skipped duplicate EscalationLevel for "
                        + f"user {user_id} on {level_info.update_timestamp}"
                    )
                    continue

                db_el = EscalationLevel(
                    user_id=user_uuid,
                    update_timestamp=level_info.update_timestamp,
                    level=level_info.level,
                    pillar_id=level_info.pillar_id,
                    created_at=datetime.now(timezone.utc),
                    is_deleted=False,
                )
                db.add(db_el)
                logger.debug(f"Added EscalationLevel for user {user_id}")

        db.commit()
        logger.debug("Committed all changes")
    return updates
