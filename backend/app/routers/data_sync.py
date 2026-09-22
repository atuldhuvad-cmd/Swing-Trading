from fastapi import APIRouter, HTTPException, Body

from app.services import data_sync_service as svc

router = APIRouter(prefix="/api/data-sync", tags=["Data Sync"])


@router.get("/jobs")
def list_jobs():
    return {"jobs": svc.list_jobs()}


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str, confirm_production: bool = Body(False, embed=True)):
    job = svc.JOBS.get(job_id)
    if job and job.writes_db and not confirm_production:
        raise HTTPException(409, "Explicit production-import confirmation is required")
    try:
        return svc.run_job(job_id, confirm_production=confirm_production)
    except svc.DataSyncBusyError as e:
        raise HTTPException(409, str(e))
    except svc.DataSyncError as e:
        raise HTTPException(404, str(e))
