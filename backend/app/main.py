from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from .database import get_db

app = FastAPI(title="Swing Trading Platform API")

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        # Verify db is reachable and foreign keys are on
        result = db.execute(text("PRAGMA foreign_keys")).scalar()
        return {"status": "ok", "foreign_keys": int(result)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
