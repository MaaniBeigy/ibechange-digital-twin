import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlmodel import SQLModel, create_engine

from app.routers import (
    missions,
    recommendation_plans,
    recommendations,
    selected_contents,
    updates,
)


load_dotenv()


# Database setup
user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
db_name = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
engine = create_engine(DATABASE_URL, echo=True)


def create_db_and_tables():
    import app.models

    SQLModel.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="OMI Recommendation Timing Module", lifespan=lifespan)

# Include routers
app.include_router(recommendations.router)
app.include_router(missions.router)
app.include_router(updates.router)
app.include_router(selected_contents.router)
app.include_router(recommendation_plans.router)


@app.get("/")
def read_root():
    return {"message": "OMI Recommendation Timing Module"}
