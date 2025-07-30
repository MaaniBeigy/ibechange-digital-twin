import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.dependencies import get_db
from app.main import app

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


def test_root_endpoint(client):
    """GET / should return the app banner message."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"message": "OMI Recommendation Timing Module"}


def test_get_db_yields_and_closes_session():
    gen = get_db()
    session = next(gen)

    # 1. generator yielded a usable Session
    assert isinstance(session, Session)
    assert session.exec(text("SELECT 1")).scalar() == 1

    # 2. exhaust the generator to trigger __exit__
    with pytest.raises(StopIteration):
        next(gen)

    # 3. session is now closed
    assert session.close
