from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from .database import get_db

from .routers import stocks, brokers, recommendations, reference, imports, review, consensus, ohlcv, evidence, fundamentals, trades, data_sync, broker_uploads

app = FastAPI(title="Swing Trading Platform API")

# CORS: only the local Vite dev server may call the API from a browser; no
# cookies or credentials are used. The frontend normally reaches the API through
# the same-origin Vite /api proxy, which is unaffected.
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import settings

ALLOWED_ORIGINS = frozenset(settings.cors_allowed_origins)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@app.middleware("http")
async def reject_cross_site_writes(request, call_next):
    # CORS only hides responses; a cross-site form POST would still run. Refuse
    # state-changing requests that a browser marks as coming from another site.
    origin = request.headers.get("origin")
    if origin is not None and request.method not in _SAFE_METHODS and origin not in ALLOWED_ORIGINS:
        return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["Content-Type"],
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
