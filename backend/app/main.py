from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .database import get_db, engine
from . import schema_readiness

from .routers import stocks, brokers, recommendations, reference, imports, review, consensus, ohlcv, evidence, fundamentals, trades, data_sync, broker_uploads


@asynccontextmanager
async def lifespan(_app):
    schema_readiness.log_startup_status(engine)  # report only; never migrates
    yield


app = FastAPI(title="Swing Trading Platform API", lifespan=lifespan)

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

# Every API router refuses service (controlled 503) until the schema is current;
# /health below stays reachable and reports the state.
_schema_guard = [Depends(schema_readiness.require_current_schema)]
for _router in (stocks, brokers, recommendations, reference, imports, review, consensus, ohlcv, evidence,
                fundamentals, trades, data_sync, broker_uploads):
    app.include_router(_router.router, dependencies=_schema_guard)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        # Verify db is reachable and foreign keys are on
        result = db.execute(text("PRAGMA foreign_keys")).scalar()
        schema = schema_readiness.check_schema(db.connection())
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Database is not reachable"})
    if not schema.ok:
        return JSONResponse(status_code=503, content={
            "status": "schema_not_current", "foreign_keys": int(result), "schema": schema.public(),
            "action": schema_readiness.MIGRATION_INSTRUCTION})
    return {"status": "ok", "foreign_keys": int(result), "schema": schema.public()}
