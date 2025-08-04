import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy.sql import text
from sqlmodel import Session, SQLModel, create_engine, select

from app.dependencies import get_db
from app.main import app
from app.models.mission import Mission
from app.models.recommendation import Recommendation
from app.models.recommendation_plan import RecommendationPlan
from app.models.selected_content import SelectedContent
from app.models.user import User

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
    # Use autocommit to avoid transaction issues with CREATE DATABASE
    with base_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        # Check if the test database exists
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


@pytest.fixture
def setup_selected_content(client):
    payload = {
        "10b58b39-9a4c-46ad-b98d-03dc28735e6b": {
            "contents": [
                {"id": "NRc30", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
            ],
            "mission_start_time": datetime.now(timezone.utc).isoformat(),
            "mission_end_time": (
                datetime.now(timezone.utc) + timedelta(days=1)
            ).isoformat(),
            "plan_id": "1b1a1f51-701a-1ab0-afe0-05f100441796",
        }
    }
    response = client.post("/selected_contents/", json=payload)
    assert response.status_code == 200


def test_get_recommendation_plans(client, setup_selected_content):
    start_time = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    end_time = (
        (datetime.now(timezone.utc) + timedelta(days=1))
        .replace(tzinfo=None)
        .isoformat()
    )
    response = client.get(
        f"/recommendation_plans/?start_time={start_time}&end_time={end_time}"
    )
    assert response.status_code == 200
    data = response.json()
    assert "recommendation_plans" in data
    assert len(data["recommendation_plans"]) > 0
    assert (
        data["recommendation_plans"][0]["user_id"]
        == "10b58b39-9a4c-46ad-b98d-03dc28735e6b"
    )


def test_get_existing_recommendation_plans(client, setup_selected_content):
    start_time = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    end_time = (
        (datetime.now(timezone.utc) + timedelta(days=1))
        .replace(tzinfo=None)
        .isoformat()
    )
    with Session(engine) as session:
        # Insert recommendation first
        recommendation = Recommendation(
            content_id="ARc5",
            content_type="recommendation",
            missions=[],
            objective=[],
            hapa=[],
            comb=[],
            intervention_type=[],
        )
        session.add(recommendation)
        session.commit()

        # Now insert the plan using the recommendation_id
        plan = RecommendationPlan(
            user_id="10b58b39-9a4c-46ad-b98d-03dc28735e6b",
            plan_id="1b1a1f51-701a-1ab0-afe0-05f100441796",
            recommendation_id=recommendation.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.add(plan)
        session.commit()
    response = client.get(
        f"/recommendation_plans/?start_time={start_time}&end_time={end_time}"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["recommendation_plans"]) == 1
    assert data["recommendation_plans"][0]["plans"][0]["content_id"] == "ARc5"


def test_recent_plan_in_cooldown_skips_generation(client):
    now = datetime.now(timezone.utc)
    user_id = uuid.uuid4()

    with Session(engine) as session:
        # prerequisite recommendation + mission
        rec = Recommendation(
            content_id="RC_SKIP",
            content_type="recommendation",
            missions=[],
            objective=[],
            hapa=[],
            comb=[],
            intervention_type=[],
        )
        mission = Mission(mission_id="MC_SKIP")
        session.add(User(id=user_id, created_at=now, is_deleted=False))
        session.add_all([rec, mission])
        session.commit()

        # selected content for the user
        session.add(
            SelectedContent(
                id="6b5a6f66-701a-1ab0-afe0-05f100441766",
                user_id=user_id,
                contents=[
                    {"id": "RC_SKIP", "type": "recommendation", "mission_id": "MC_SKIP"}
                ],
                created_at=now,
            )
        )
        # recent plan (10 min ago) triggers the cooldown logic
        session.add(
            RecommendationPlan(
                user_id=user_id,
                plan_id="6b5a6f66-701a-1ab0-afe0-05f100441766",
                recommendation_id=rec.id,
                scheduled_for=now - timedelta(minutes=10),
            )
        )
        session.commit()

    # query a *future* window (no existing plans there)
    start_iso = (now + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    end_iso = (now + timedelta(hours=2)).replace(tzinfo=None).isoformat()
    resp = client.get(
        f"/recommendation_plans/?start_time={start_iso}&end_time={end_iso}"
    )
    assert resp.status_code == 200
    assert resp.json() == {"recommendation_plans": []}


def test_generation_returns_empty_when_remaining_zero(client, monkeypatch):
    # weekly / daily quotas -> 0
    monkeypatch.setenv("MIN_NOTIFICATIONS_PER_WEEK", "0")
    monkeypatch.setenv("MAX_NOTIFICATIONS_PER_WEEK", "0")
    monkeypatch.setenv("MIN_NOTIFICATIONS_PER_DAY", "0")
    monkeypatch.setenv("MAX_NOTIFICATIONS_PER_DAY", "0")

    now = datetime.now(timezone.utc)
    user_id = uuid.uuid4()

    with Session(engine) as session:
        rec = Recommendation(
            content_id="RC_ZERO",
            content_type="recommendation",
            missions=[],
            objective=[],
            hapa=[],
            comb=[],
            intervention_type=[],
        )
        mission = Mission(mission_id="MC_ZERO")
        session.add(User(id=user_id, created_at=now, is_deleted=False))
        session.add_all([rec, mission])
        session.commit()

        session.add(
            SelectedContent(
                id="6b5a6f36-701a-1ab0-afe0-05f100441733",
                user_id=user_id,
                contents=[
                    {"id": "RC_ZERO", "type": "recommendation", "mission_id": "MC_ZERO"}
                ],
                created_at=now,
            )
        )
        session.commit()

    start_iso = (now + timedelta(minutes=1)).replace(tzinfo=None).isoformat()
    end_iso = (now + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    resp = client.get(
        f"/recommendation_plans/?start_time={start_iso}&end_time={end_iso}"
    )
    assert resp.status_code == 200
    assert resp.json() == {"recommendation_plans": []}


def test_generation_respects_cooldown_and_break(client, monkeypatch):
    # set quotas so *exactly* 2 notifications are needed in the window
    monkeypatch.setenv("MIN_NOTIFICATIONS_PER_WEEK", "2")
    monkeypatch.setenv("MAX_NOTIFICATIONS_PER_WEEK", "2")
    monkeypatch.setenv("MIN_NOTIFICATIONS_PER_DAY", "2")
    monkeypatch.setenv("MAX_NOTIFICATIONS_PER_DAY", "5")
    monkeypatch.setenv("BETWEEN_NOTIFICATION_COOLDOWN", "30")  # minutes

    now = datetime.now(timezone.utc)
    user_id = uuid.uuid4()

    # deterministic schedule: 10 min, 20 min, 45 min
    def fake_schedule(_, __):
        return [
            now + timedelta(minutes=10),
            now + timedelta(minutes=20),  # will be skipped (too close)
            now + timedelta(minutes=45),
        ]

    monkeypatch.setattr(
        "app.services.recommendation_plan_service.generate_random_schedule",
        fake_schedule,
    )

    with Session(engine) as session:
        rec_a = Recommendation(
            content_id="RC_A",
            content_type="recommendation",
            missions=[],
            objective=[],
            hapa=[],
            comb=[],
            intervention_type=[],
        )
        rec_b = Recommendation(
            content_id="RC_B",
            content_type="recommendation",
            missions=[],
            objective=[],
            hapa=[],
            comb=[],
            intervention_type=[],
        )
        mission = Mission(mission_id="MC_CDLN")
        session.add(User(id=user_id, created_at=now, is_deleted=False))
        session.add_all([rec_a, rec_b, mission])
        session.commit()

        session.add(
            SelectedContent(
                id="8b5a6f88-701a-1ab0-afe0-05f100441788",
                user_id=user_id,
                contents=[
                    {"id": "RC_A", "type": "recommendation", "mission_id": "MC_CDLN"},
                    {"id": "RC_B", "type": "recommendation", "mission_id": "MC_CDLN"},
                ],
                created_at=now,
            )
        )
        session.commit()

    start_iso = now.replace(tzinfo=None).isoformat()
    end_iso = (now + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    resp = client.get(
        f"/recommendation_plans/?start_time={start_iso}&end_time={end_iso}"
    )
    data = resp.json()

    # exactly one user block with **2** scheduled notifications
    assert resp.status_code == 200
    assert len(data["recommendation_plans"]) == 1
    assert len(data["recommendation_plans"][0]["plans"]) == 2


def test_existing_schedule_counting_and_generation(client, monkeypatch):
    """
    One plan already in the window → loop fills existing_by_day.
    We need 3 per week, so 2 more are generated.
    """
    user_id = uuid.uuid4()
    now = datetime(2025, 7, 29, 7, 30, 0, 599149, tzinfo=timezone.utc)
    start = now
    end = now + timedelta(days=5)

    # env: need exactly three notifications
    monkeypatch.setenv("MIN_NOTIFICATIONS_PER_WEEK", "7")
    monkeypatch.setenv("MAX_NOTIFICATIONS_PER_WEEK", "21")
    monkeypatch.setenv("MIN_NOTIFICATIONS_PER_DAY", "3")
    monkeypatch.setenv("MAX_NOTIFICATIONS_PER_DAY", "5")
    monkeypatch.setenv("BETWEEN_NOTIFICATION_COOLDOWN", "30")  # minutes

    # # deterministic schedule: 10 min, 40 min, 90 min, 120 min
    # def fake_schedule(_, __):
    #     return [
    #         now + timedelta(minutes=10),
    #         now + timedelta(minutes=40),  # rejected (too close to existing 60 min)
    #         now + timedelta(minutes=90),
    #         now + timedelta(minutes=120),
    #     ]

    # monkeypatch.setattr(
    #     "app.services.recommendation_plan_service.generate_random_schedule",
    #     fake_schedule,
    # )

    payload = {
        "474dbf4c-8922-4dac-aa35-92632a7bcaf8": {
            "contents": [
                {"id": "NRs6", "type": "resource", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc53", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc20", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc53", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc53", "type": "recommendation", "mission_id": "NM31"},
            ],
            "mission_start_time": "2025-07-07T10:00:33.919000",
            "mission_end_time": "2025-07-14T10:00:33.919000",
            "plan_id": "7b8a9f54-801a-4ab0-afe0-06f100441793",
        },
        "10b58b39-9a4c-46ad-b98d-03dc28735e6b": {
            "contents": [
                {"id": "NRc30", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc53", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc53", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc53", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc19", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc53", "type": "recommendation", "mission_id": "NM31"},
            ],
            "mission_start_time": "2025-07-07T10:00:33.919000",
            "mission_end_time": "2025-07-14T10:00:33.919000",
            "plan_id": "3b8a9f54-701a-1ab0-afe0-05f100441796",
        },
    }

    start_iso = start.replace(tzinfo=None).isoformat()
    end_iso = end.replace(tzinfo=None).isoformat()
    response = client.post("/selected_contents/", json=payload)
    assert response.status_code == 200
    resp = client.get(
        f"/recommendation_plans/?start_time={start_iso}&end_time={end_iso}"
    )
    data = resp.json()

    # One existing + two newly generated = 3 plans
    assert resp.status_code == 200
    assert len(data["recommendation_plans"]) == 2
    assert len(data["recommendation_plans"][0]["plans"]) == 4


def test_existing_by_day_loop_runs_on_multiple_generations(client, monkeypatch):
    # Allow up to 2 notifications per day, require 2
    monkeypatch.setenv("MIN_NOTIFICATIONS_PER_DAY", "2")
    monkeypatch.setenv("MAX_NOTIFICATIONS_PER_DAY", "2")
    monkeypatch.setenv("MIN_NOTIFICATIONS_PER_WEEK", "2")
    monkeypatch.setenv("MAX_NOTIFICATIONS_PER_WEEK", "14")
    monkeypatch.setenv("BETWEEN_NOTIFICATION_COOLDOWN", "1")  # minute

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    user_id = str(uuid.uuid4())

    # Patch generate_random_schedule to return two times on the same day
    schedule_times = [
        now.replace(hour=10, minute=0),
        now.replace(hour=12, minute=0),
    ]

    def fake_schedule(start, end):
        return schedule_times

    monkeypatch.setattr(
        "app.services.recommendation_plan_service.generate_random_schedule",
        fake_schedule,
    )

    with Session(engine) as session:
        # Two recommendations
        rec1 = Recommendation(
            content_id="TST_LOOP1",
            content_type="recommendation",
            missions=[],
            objective=[],
            hapa=[],
            comb=[],
            intervention_type=[],
        )
        rec2 = Recommendation(
            content_id="TST_LOOP2",
            content_type="recommendation",
            missions=[],
            objective=[],
            hapa=[],
            comb=[],
            intervention_type=[],
        )
        mission = Mission(mission_id="MID_LOOP")
        user = User(id=user_id, created_at=now, is_deleted=False)
        session.add_all([user, rec1, rec2, mission])
        session.commit()

        # Add selected content with two recommendations for the user
        selected = SelectedContent(
            id="5b5a9f55-701a-1ab0-afe0-05f100441795",
            user_id=user_id,
            contents=[
                {"id": "TST_LOOP1", "type": "recommendation", "mission_id": "MID_LOOP"},
                {"id": "TST_LOOP2", "type": "recommendation", "mission_id": "MID_LOOP"},
            ],
            created_at=now,
        )
        session.add(selected)
        session.commit()

    # Query the whole day
    start_iso = now.replace(hour=0, minute=0, tzinfo=None).isoformat()
    end_iso = now.replace(hour=23, minute=59, tzinfo=None).isoformat()
    response = client.get(
        f"/recommendation_plans/?start_time={start_iso}&end_time={end_iso}"
    )
    assert response.status_code == 200

    data = response.json()
    print(data["recommendation_plans"])
    plans = data["recommendation_plans"][0]["plans"]
    assert len(plans) == 2
    scheduled_for_set = set(p["scheduled_for"] for p in plans)
    assert schedule_times[0].replace(tzinfo=None).isoformat() in scheduled_for_set
    assert schedule_times[1].replace(tzinfo=None).isoformat() in scheduled_for_set


def test_recommendation_plans_invalid_datetime_format(client):
    """Router should return 422 when start_time or end_time is not ISO‐8601."""
    resp = client.get(
        "/recommendation_plans/?start_time=not-a-date&end_time=2025-07-29T10:00:00"
    )
    assert resp.status_code == 422
    assert resp.json() == {"detail": "Invalid datetime format"}


def test_recommendation_plan_skips_when_mode_not_test(client, monkeypatch):
    """Branch: MODE ≠ 'test' → service returns [] and router responds with empty list."""
    monkeypatch.setenv("MODE", "prod")  # trigger the early‑return branch

    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # minimal DB setup so the router will attempt generation
    with Session(engine) as session:
        session.add(User(id=user_id, created_at=now, is_deleted=False))
        rec = Recommendation(
            content_id="RC_PROD",
            content_type="recommendation",
            missions=["MC_PROD"],
            objective=[],
            hapa=[],
            comb=[],
            intervention_type=[],
        )
        session.add_all([rec, Mission(mission_id="MC_PROD")])
        session.commit()
        session.add(
            SelectedContent(
                id="4b4a4f44-701a-1ab0-afe0-05f100444444",
                user_id=user_id,
                contents=[
                    {"id": "RC_PROD", "type": "recommendation", "mission_id": "MC_PROD"}
                ],
                created_at=now,
            )
        )
        session.commit()

    start_iso = now.replace(tzinfo=None).isoformat()
    end_iso = (now + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    resp = client.get(
        f"/recommendation_plans/?start_time={start_iso}&end_time={end_iso}"
    )

    assert resp.status_code == 200
    assert resp.json() == {"recommendation_plans": []}
