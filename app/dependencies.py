import os

from dotenv import load_dotenv
from sqlmodel import Session, create_engine

load_dotenv()

# Database setup
user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
db = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql://{user}:{password}@{host}:{port}/{db}"
engine = create_engine(DATABASE_URL)


def get_db():
    with Session(engine) as session:
        yield session
