import os
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
from app.models.selected_content import SelectedContent
from app.models.user import User

load_dotenv()

# -----------------------------------------------------------------------------
# Database + dependency override helpers
# -----------------------------------------------------------------------------

DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:"
    f"{os.getenv('POSTGRES_PASSWORD')}@db:5432/"
    f"{os.getenv('POSTGRES_DB')}_test"
)
engine = create_engine(DATABASE_URL)


def override_get_db():
    """Yield a session bound to the dedicated *_test* database used by the suite."""
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


# -----------------------------------------------------------------------------
# Pytest fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="function")
def client():
    """Start each test with a pristine schema and tear it down afterwards."""
    # Ensure the actual database exists (happens once per container lifecycle).
    bootstrap_engine = create_engine(
        f"postgresql://{os.getenv('POSTGRES_USER')}:"
        f"{os.getenv('POSTGRES_PASSWORD')}@db:5432/postgres"
    )
    with bootstrap_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :db"),
            {"db": f"{os.getenv('POSTGRES_DB')}_test"},
        ).fetchone()
        if not exists:
            conn.execute(text(f"CREATE DATABASE {os.getenv('POSTGRES_DB')}_test"))

    # Build a clean schema for this test function.
    SQLModel.metadata.create_all(engine)

    with TestClient(app) as c:
        yield c

    # Drop all tables so that the next test starts blank.
    SQLModel.metadata.drop_all(engine)


# -----------------------------------------------------------------------------
# Helper payload builders
# -----------------------------------------------------------------------------


def _build_payload_single_user():
    """Return a SelectedContent payload for **one** user."""
    return {
        "474dbf4c-8922-4dac-aa35-92632a7bcaf8": {
            "contents": [
                {"id": "NRs6", "type": "resource", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
            ],
            "mission_start_time": "2025-07-29T13:00:03+00:00",
            "mission_end_time": "2025-08-05T13:00:03+00:00",
        }
    }


def _build_payload_two_users():
    """Extend the single-user payload with an extra user block."""
    payload = _build_payload_single_user()
    now = "2025-07-29T13:00:03+00:00"
    payload["10b58b39-9a4c-46ad-b98d-03dc28735e6b"] = {
        "contents": [{"id": "NRc20", "type": "recommendation", "mission_id": "NM31"}],
        "mission_start_time": "2025-07-29T13:00:03+00:00",
        "mission_end_time": "2025-08-05T13:00:03+00:00",
    }
    return payload


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


def test_create_selected_contents_creates_records(client):
    payload = _build_payload_single_user()
    resp = client.post("/selected_contents/", json=payload)
    assert resp.status_code == 200

    with Session(engine) as session:
        # Exactly **one** SelectedContent row and it contains de‑duplicated entries.
        sc_rows = session.exec(select(SelectedContent)).all()
        assert len(sc_rows) == 1
        assert len(sc_rows[0].contents) == 2  # NRs6 + NRc54

        # User table contains our user (compare as strings for UUID).
        users = session.exec(select(User)).all()
        assert {str(u.id) for u in users} == {"474dbf4c-8922-4dac-aa35-92632a7bcaf8"}

        # Recommendation rows were created for each unique content_id.
        recs = session.exec(select(Recommendation)).all()
        assert {r.content_id for r in recs} == {"NRs6", "NRc54"}

        # Mission NM31 exists exactly once.
        missions = session.exec(select(Mission)).all()
        assert {m.mission_id for m in missions} == {"NM31"}


def test_posting_same_payload_twice_is_idempotent_1(client):
    # payload = _build_payload_single_user()
    client.post(
        "/selected_contents/",
        json={
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
            },
        },
    )
    client.post(  # identical second call
        "/selected_contents/",
        json={
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
            },
        },
    )

    with Session(engine) as session:
        # Should still only be **one** SelectedContent row for that user.
        sc_rows = session.exec(select(SelectedContent)).all()
        assert len(sc_rows) == 1

        # Recommendation & Mission counts remain unchanged.
        assert len(session.exec(select(Recommendation)).all()) == 4
        assert len(session.exec(select(Mission)).all()) == 1


def test_posting_same_payload_twice_is_idempotent_2(client):
    # payload = _build_payload_single_user()
    client.post(
        "/selected_contents/",
        json={
            "474dbf4c-8922-4dac-aa35-92632a7bcaf8": {
                "contents": [
                    {"id": "NRs6", "type": "resource", "mission_id": "NM31"},
                    {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                    {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                ],
                "mission_start_time": "2025-07-29T13:00:03+00:00",
                "mission_end_time": "2025-08-05T13:00:03+00:00",
            }
        },
    )
    client.post(  # identical second call
        "/selected_contents/",
        json={
            "474dbf4c-8922-4dac-aa35-92632a7bcaf8": {
                "contents": [
                    {"id": "NRs6", "type": "resource", "mission_id": "NM31"},
                    {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                    {"id": "NRc54", "type": "recommendation", "mission_id": "NM31"},
                ],
                "mission_start_time": "2025-07-29T13:00:03+00:00",
                "mission_end_time": "2025-08-05T13:00:03+00:00",
            }
        },
    )

    with Session(engine) as session:
        # Should still only be **one** SelectedContent row for that user.
        sc_rows = session.exec(select(SelectedContent)).all()
        assert len(sc_rows) == 1

        # Recommendation & Mission counts remain unchanged.
        assert len(session.exec(select(Recommendation)).all()) == 2
        assert len(session.exec(select(Mission)).all()) == 1


def test_payload_with_multiple_users(client):
    payload = _build_payload_two_users()
    client.post("/selected_contents/", json=payload)

    with Session(engine) as session:
        # Two users should now exist.
        assert len(session.exec(select(User)).all()) == 2

        # Each user gets one SelectedContent row.
        assert len(session.exec(select(SelectedContent)).all()) == 2

        # Mission NM31 only stored once (shared by both users).
        assert len(session.exec(select(Mission)).all()) == 1


def test_recommendation_mission_append(client):
    """Existing Recommendation gets an extra mission when a new mission_id arrives."""
    user_id = "474dbf4c-8922-4dac-aa35-92632a7bcaf8"

    first_payload = {
        user_id: {
            "contents": [
                {"id": "NRx1", "type": "recommendation", "mission_id": "NM31"}
            ],
            "mission_start_time": "2025-07-29T13:00:03+00:00",
            "mission_end_time": "2025-08-05T13:00:03+00:00",
        }
    }

    second_payload = {
        user_id: {
            "contents": [
                {"id": "NRx1", "type": "recommendation", "mission_id": "NM32"}
            ],
            "mission_start_time": "2025-07-29T13:00:03+00:00",
            "mission_end_time": "2025-08-05T13:00:03+00:00",
        }
    }

    client.post("/selected_contents/", json=first_payload)
    client.post("/selected_contents/", json=second_payload)

    with Session(engine) as session:
        # Still one Recommendation row for NRx1 but with **two** missions now.
        recs = session.exec(
            select(Recommendation).where(Recommendation.content_id == "NRx1")
        ).all()
        assert len(recs) == 1
        assert set(recs[0].missions) == {"NM31", "NM32"}


def test_selected_content_null_timestamps_idempotent(client):
    """When mission_start_time / mission_end_time are null, duplicate detection still works."""
    user_id = "474dbf4c-8922-4dac-aa35-92632a7bcaf8"

    payload = {
        user_id: {
            "contents": [{"id": "NRz1", "type": "resource", "mission_id": "NM40"}],
            "mission_start_time": None,
            "mission_end_time": None,
        }
    }

    client.post("/selected_contents/", json=payload)
    client.post("/selected_contents/", json=payload)

    with Session(engine) as session:
        sc_rows = session.exec(select(SelectedContent)).all()
        assert len(sc_rows) == 1
        assert sc_rows[0].mission_start_time is None
        assert sc_rows[0].mission_end_time is None
