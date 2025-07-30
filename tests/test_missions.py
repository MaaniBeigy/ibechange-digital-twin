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
        }
    }
    response = client.post("/selected_contents/", json=payload)
    assert response.status_code == 200


def test_create_missions_idempotent(client):
    """
    • first POST inserts two missions
    • second identical POST hits the existing_mission branch and inserts nothing
    """
    payload = {
        "missions": [
            {"mission_id": "NM01", "weekly_frequency": 3},
            {"mission_id": "NM02", "weekly_frequency": 2},
        ]
    }

    # first call — creates both missions
    resp1 = client.post("/missions/", json=payload)
    assert resp1.status_code == 200
    assert resp1.json() == payload

    # second call — should be a no‑op
    resp2 = client.post("/missions/", json=payload)
    assert resp2.status_code == 200

    # verify DB has still exactly two rows
    with Session(engine) as session:
        missions = session.exec(select(Mission)).all()
        assert {m.mission_id for m in missions} == {"NM01", "NM02"}
