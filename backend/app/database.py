from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import Engine
from .config import settings
import os

# Create data directory if it doesn't exist
db_path = settings.database_url.replace("sqlite:///", "")
if ":memory:" not in db_path:
    if os.path.dirname(db_path): os.makedirs(os.path.dirname(db_path), exist_ok=True)

engine = create_engine(
    settings.database_url, connect_args={"check_same_thread": False}
)

def _attach_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

event.listen(Engine, "connect", _attach_sqlite_pragma)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
