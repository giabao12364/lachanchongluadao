import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

# Bản sync (psycopg2) — dùng cho Alembic migration.
# App backend thật (FastAPI) khi code API sẽ dùng bản async (asyncpg) riêng.
DATABASE_URL_SYNC = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://lachan_user:lachan_pass@localhost:5432/lachan_db",
)

engine = create_engine(DATABASE_URL_SYNC, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency cho FastAPI route: with get_db() as db: ..."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
