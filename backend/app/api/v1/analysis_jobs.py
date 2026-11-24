from fastapi import APIRouter, Depends, HTTPException

from app.core.analysis_jobs import get_job_payload
from app.core.db.models import User
from app.core.security.auth import get_current_user

router = APIRouter()


@router.get("/analysis-jobs/{job_id}")
def analysis_job(job_id: str, user: User = Depends(get_current_user)):
    payload = get_job_payload(job_id, user.id)
    if not payload:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return payload
