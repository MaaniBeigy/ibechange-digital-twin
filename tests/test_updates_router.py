import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy.sql import text
from sqlmodel import Session, SQLModel, create_engine, select

from app.dependencies import get_db
from app.main import app
from app.models.escalation_level import EscalationLevel
from app.models.event import Event
from app.models.mission import Mission
from app.models.recommendation import Recommendation
from app.models.user import HealthHabitAssessment, MissionContent, User
from tests.constants import updates_example

load_dotenv()

# Use 'db' as the host since tests run inside the Docker network
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@db:5432/{os.getenv('POSTGRES_DB')}_test"
engine = create_engine(DATABASE_URL)


def override_get_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def client():
    # Create test database if it doesn't exist
    base_db_url = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@db:5432/postgres"
    base_engine = create_engine(base_db_url)
    with base_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
            {"db_name": f"{os.getenv('POSTGRES_DB')}_test"},
        ).fetchone()
        if not result:
            conn.execute(text(f"CREATE DATABASE {os.getenv('POSTGRES_DB')}_test"))

    SQLModel.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    SQLModel.metadata.drop_all(engine)


def test_post_updates_inserts_user_and_escalation_and_disables_user(client):
    # prepare ids
    new_user_id = str(uuid4())
    disabled_user_id = str(uuid4())
    escalation_user_id = str(uuid4())

    # pre-insert a user to be disabled
    with Session(engine) as session:
        u = User(
            id=disabled_user_id,
            characteristics={"gender": "male"},
            is_deleted=False,
        )
        session.add(u)
        session.commit()

    payload = {
        "user_feedback": {
            new_user_id: {
                "events": [
                    {
                        "process_id": 123,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event_name": "notification_sent",
                        "properties": {
                            "content_id": "ERc1",
                            "content_type": "recommendation",
                            "mission_id": "PM1",
                        },
                    }
                ]
            }
        },
        "new_users": {
            new_user_id: {
                "gender": "female",
                "height": 165,
                "userAge": 30,
                "weight": 60,
                "wearable": "yes",
                "residence": "TestCity",
                "enrolmentDate": "2025-07-16",
                "informedConsent": "signed",
                "recruitmentCenter": "TEST",
                "level": 0,
            }
        },
        "disabled_users": {
            disabled_user_id: {"date_disabled": datetime.now(timezone.utc).isoformat()}
        },
        "health_habit_assessments": {
            new_user_id: [
                {
                    "hhs": {"smoking": 20.0},
                    "assessment_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        },
        "new_missions_and_contents": {
            new_user_id: {
                "update_timestamp": datetime.now(timezone.utc).isoformat(),
                "new_missions": [
                    {
                        "mission": "PM1",
                        "recommendations": ["PRc1", "PRc2"],
                        "resources": ["PRs1"],
                        "prescribed": False,
                        "selection_timestamp": datetime.now(timezone.utc).isoformat(),
                        "finish_timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
            }
        },
        "escalation_level": {
            escalation_user_id: [
                {
                    "update_timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": 1,
                    "pillar_id": "EO",
                }
            ]
        },
    }

    response = client.post("/updates", json=payload)
    print(response.json())
    assert response.status_code == 200

    with Session(engine) as session:
        from uuid import UUID

        new_user_obj = session.exec(
            select(User).where(User.id == UUID(new_user_id))
        ).first()
        assert new_user_obj is not None
        assert new_user_obj.characteristics.get("gender") == "female"

        disabled_user_obj = session.exec(
            select(User).where(User.id == UUID(disabled_user_id))
        ).first()
        assert disabled_user_obj.is_deleted is True
        assert disabled_user_obj.deleted_at is not None

        levels = session.exec(
            select(EscalationLevel).where(EscalationLevel.user_id == escalation_user_id)
        ).all()
        assert len(levels) == 1
        assert levels[0].pillar_id == "EO"
        assert levels[0].level == 1


def count_table_rows(session: Session):
    return {
        "missions": session.exec(select(Mission)).all().__len__(),
        "recommendations": session.exec(select(Recommendation)).all().__len__(),
        "events": session.exec(select(Event)).all().__len__(),
        "escalation_levels": session.exec(select(EscalationLevel)).all().__len__(),
        "mission_contents": session.exec(select(MissionContent)).all().__len__(),
        "users": session.exec(select(User)).all().__len__(),
    }


def test_post_updates_idempotency(client):
    # First POST
    response1 = client.post("/updates", json=updates_example)
    assert response1.status_code == 200

    with Session(engine) as session:
        counts_after_first = count_table_rows(session)

    # Second POST (same data)
    response2 = client.post("/updates", json=updates_example)
    assert response2.status_code == 200

    with Session(engine) as session:
        counts_after_second = count_table_rows(session)

    # Assert no new rows were added
    assert counts_after_first == counts_after_second


def test_recommendation_mission_update(client):
    from uuid import UUID, uuid4

    user_id = str(uuid4())
    rec_id = "RC1"
    mission_id1 = "M1"
    mission_id2 = "M2"

    # 1. Initial payload: Recommendation linked to mission_id1
    payload1 = {
        "user_feedback": {},
        "new_users": {user_id: {"gender": "other"}},
        "disabled_users": {},
        "health_habit_assessments": {},
        "new_missions_and_contents": {
            user_id: {
                "update_timestamp": datetime.now(timezone.utc).isoformat(),
                "new_missions": [
                    {
                        "mission": mission_id1,
                        "recommendations": [rec_id],
                        "resources": [],
                        "prescribed": False,
                        "selection_timestamp": datetime.now(timezone.utc).isoformat(),
                        "finish_timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
            }
        },
        "escalation_level": {},
    }

    # First POST
    r1 = client.post("/updates", json=payload1)
    assert r1.status_code == 200

    # Check that Recommendation has only mission_id1
    with Session(engine) as session:
        rec = session.exec(
            select(Recommendation).where(Recommendation.content_id == rec_id)
        ).first()
        assert rec is not None
        assert sorted(rec.missions) == [mission_id1]

    # 2. Second payload: Add new mission_id2 linked to the same Recommendation
    payload2 = {
        "user_feedback": {},
        "new_users": {},  # User already exists
        "disabled_users": {},
        "health_habit_assessments": {},
        "new_missions_and_contents": {
            user_id: {
                "update_timestamp": datetime.now(timezone.utc).isoformat(),
                "new_missions": [
                    {
                        "mission": mission_id2,
                        "recommendations": [rec_id],
                        "resources": [],
                        "prescribed": False,
                        "selection_timestamp": datetime.now(timezone.utc).isoformat(),
                        "finish_timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
            }
        },
        "escalation_level": {},
    }

    # Second POST
    r2 = client.post("/updates", json=payload2)
    assert r2.status_code == 200

    # Check that Recommendation now has both mission IDs
    with Session(engine) as session:
        rec = session.exec(
            select(Recommendation).where(Recommendation.content_id == rec_id)
        ).first()
        assert rec is not None
        # Order of missions may vary
        assert set(rec.missions) == {mission_id1, mission_id2}


def test_update_health_habit_assessment_hhs(client):
    from uuid import UUID, uuid4

    user_id = str(uuid4())
    assessment_time = datetime.now(timezone.utc).replace(microsecond=0)
    initial_hhs = {"smoking": 10.0}
    updated_hhs = {"smoking": 5.0, "exercise": 2.0}

    # Pre-insert the user and initial HealthHabitAssessment
    with Session(engine) as session:
        u = User(
            id=user_id,
            characteristics={"gender": "other"},
            is_deleted=False,
        )
        session.add(u)
        session.commit()
        hha = HealthHabitAssessment(
            user_id=UUID(user_id),
            hhs=initial_hhs,
            assessment_timestamp=assessment_time,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
        )
        session.add(hha)
        session.commit()

    # POST update with a different hhs (should trigger the update branch)
    payload = {
        "user_feedback": {},
        "new_users": {},
        "disabled_users": {},
        "health_habit_assessments": {
            user_id: [
                {
                    "hhs": updated_hhs,
                    "assessment_timestamp": assessment_time.isoformat(),
                }
            ]
        },
        "new_missions_and_contents": {},
        "escalation_level": {},
    }

    resp = client.post("/updates", json=payload)
    assert resp.status_code == 200

    # Verify the hhs has been updated, and modified_at is set
    with Session(engine) as session:
        assessment = session.exec(
            select(HealthHabitAssessment).where(
                HealthHabitAssessment.user_id == UUID(user_id),
                HealthHabitAssessment.assessment_timestamp == assessment_time,
                HealthHabitAssessment.is_deleted == False,
            )
        ).first()
        assert assessment is not None
        # Both keys/values should be present
        assert assessment.hhs == updated_hhs
        assert assessment.modified_at is not None


def test_updates_mission_content_timestamps(client):
    from uuid import uuid4, UUID

    user_id = str(uuid4())
    mission_id = "MISSION1"
    t1 = datetime(2025, 7, 28, 12, 0, tzinfo=timezone.utc)
    t2 = datetime(2025, 7, 29, 12, 0, tzinfo=timezone.utc)
    t3 = datetime(2025, 8, 1, 12, 0, tzinfo=timezone.utc)

    # Pre-insert user and mission
    with Session(engine) as session:
        u = User(id=user_id, characteristics={}, is_deleted=False)
        m = Mission(mission_id=mission_id, is_deleted=False)
        session.add(u)
        session.add(m)
        session.commit()
        # Insert initial MissionContent
        mc = MissionContent(
            user_id=UUID(user_id),
            mission_id=m.id,
            selection_timestamp=t1,
            mission_start_time=t1,
            mission_end_time=t2,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
        )
        session.add(mc)
        session.commit()

    # Now POST an update with new timestamps (should update existing MissionContent)
    payload = {
        "user_feedback": {},
        "new_users": {},
        "disabled_users": {},
        "health_habit_assessments": {},
        "new_missions_and_contents": {
            user_id: {
                "update_timestamp": datetime.now(timezone.utc).isoformat(),
                "new_missions": [
                    {
                        "mission": mission_id,
                        "recommendations": [],
                        "resources": [],
                        "prescribed": False,
                        "selection_timestamp": t3.isoformat(),
                        "finish_timestamp": t3.isoformat(),
                    }
                ],
            }
        },
        "escalation_level": {},
    }
    resp = client.post("/updates", json=payload)
    assert resp.status_code == 200

    # Check that the timestamps were updated
    with Session(engine) as session:
        m_obj = session.exec(
            select(Mission).where(Mission.mission_id == mission_id)
        ).first()
        mc = session.exec(
            select(MissionContent).where(
                MissionContent.user_id == UUID(user_id),
                MissionContent.mission_id == m_obj.id,
                MissionContent.is_deleted == False,
            )
        ).first()
        assert mc is not None
        assert mc.selection_timestamp.replace(tzinfo=timezone.utc) == t3
        assert mc.mission_start_time.replace(tzinfo=timezone.utc) == t3
        assert mc.mission_end_time.replace(tzinfo=timezone.utc) == t3
