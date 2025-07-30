import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.sql import text
from sqlmodel import Session, SQLModel, create_engine

from app.dependencies import get_db
from app.main import app
from app.models.recommendation import Recommendation

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


def test_create_recommendations(client):
    recommendations = {
        "recommendations": [
            {
                "content_id": "ERc1",
                "content_type": "recommendation",
                "missions": ["EM58", "EM59"],
                "objective": ["EO1"],
                "hapa": [],
                "comb": ["Psychological capability"],
                "intervention_type": ["Education"],
            }
        ]
    }
    response = client.post("/recommendations/", json=recommendations)
    assert response.status_code == 200
    assert response.json() == recommendations


def test_create_duplicate_recommendations(client):
    recommendations = {
        "recommendations": [
            {
                "content_id": "ERc1",
                "content_type": "recommendation",
                "missions": ["EM58", "EM59"],
                "objective": ["EO1"],
                "hapa": [],
                "comb": ["Psychological capability"],
                "intervention_type": ["Education"],
            }
        ]
    }
    response = client.post("/recommendations/", json=recommendations)
    assert response.status_code == 200
    response = client.post("/recommendations/", json=recommendations)
    assert response.status_code == 200
    with Session(engine) as session:
        count = session.exec(
            select(Recommendation).where(Recommendation.content_id == "ERc1")
        ).all()
        assert len(count) == 1
