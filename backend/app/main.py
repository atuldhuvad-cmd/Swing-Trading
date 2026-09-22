from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from .database import get_db

from .routers import stocks, brokers, recommendations, reference, imports, review, consensus, ohlcv, evidence, fundamentals, trades, data_sync, broker_uploads

app = FastAPI(title="Swing Trading Platform API")

# Setup CORS for frontend dev
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router)
app.include_router(brokers.router)
app.include_router(recommendations.router)
app.include_router(reference.router)
app.include_router(imports.router)
app.include_router(review.router)
app.include_router(consensus.router)
app.include_router(ohlcv.router)
app.include_router(evidence.router)
app.include_router(fundamentals.router)
app.include_router(trades.router)
app.include_router(data_sync.router)
app.include_router(broker_uploads.router)

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        # Verify db is reachable and foreign keys are on
        result = db.execute(text("PRAGMA foreign_keys")).scalar()
        return {"status": "ok", "foreign_keys": int(result)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
