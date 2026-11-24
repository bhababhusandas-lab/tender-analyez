import asyncio
import os
import uuid
from datetime import datetime
from typing import Awaitable, Callable, TypeVar

from app.core.db.models import AnalysisJob, AnalysisStep
from app.core.db.session import SessionLocal
from app.core.compression import decode_json, decode_text, encode_json, encode_text

T = TypeVar("T")
STEP_TIMEOUT_SECONDS = max(10, int(os.getenv("ANALYSIS_STEP_TIMEOUT_SECONDS", "600")))
STEP_MAX_ATTEMPTS = max(1, int(os.getenv("ANALYSIS_STEP_MAX_ATTEMPTS", "2")))


def create_job(user_id: int, kind: str, tender_text: str, context: dict, steps: list[dict]) -> str:
    job_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(AnalysisJob(
            id=job_id, user_id=user_id, kind=kind, status="running",
            tender_text=encode_text(tender_text), context_json=encode_json(context),
        ))
        db.add_all([
            AnalysisStep(job_id=job_id, step_id=s["id"], step_name=s["name"], status="waiting")
            for s in steps
        ])
        db.commit()
    return job_id


def update_step(job_id: str, step_id: str, status: str, *, content: str | None = None,
                error: str | None = None, increment_attempt: bool = False) -> None:
    with SessionLocal() as db:
        step = db.query(AnalysisStep).filter_by(job_id=job_id, step_id=step_id).first()
        if not step:
            return
        step.status = status
        step.error = error
        if content is not None:
            step.content = encode_text(content)
        if increment_attempt:
            step.attempts += 1
            step.started_at = datetime.utcnow()
        if status in {"done", "error"}:
            step.finished_at = datetime.utcnow()
        db.commit()


def finish_job(job_id: str, status: str, *, final_content: str | None = None,
               error: str | None = None) -> None:
    with SessionLocal() as db:
        job = db.query(AnalysisJob).filter_by(id=job_id).first()
        if not job:
            return
        job.status = status
        job.error = error
        if final_content is not None:
            job.final_content = encode_text(final_content)
        db.commit()
    from app.core.tender_history import on_job_status  # local import avoids a cycle
    try:
        on_job_status(job_id, status)
    except Exception as exc:
        print(f"[history] on_job_status failed for {job_id}: {exc}")


def cancel_job(job_id: str, user_id: int, kind: str) -> bool:
    """Persist a user-requested stop and mark unfinished steps accordingly."""
    with SessionLocal() as db:
        job = db.query(AnalysisJob).filter_by(id=job_id, user_id=user_id, kind=kind).first()
        if not job:
            return False
        if job.status in {"completed", "cancelled"}:
            return True
        job.status = "cancelled"
        job.error = "Stopped by user"
        unfinished = db.query(AnalysisStep).filter(
            AnalysisStep.job_id == job_id,
            AnalysisStep.status.in_(["waiting", "running"]),
        ).all()
        for step in unfinished:
            step.status = "cancelled"
            step.error = "Stopped by user"
            step.finished_at = datetime.utcnow()
        db.commit()
    from app.core.tender_history import on_job_status
    try:
        on_job_status(job_id, "cancelled")
    except Exception as exc:
        print(f"[history] on_job_status failed for {job_id}: {exc}")
    return True


def get_job_payload(job_id: str, user_id: int) -> dict | None:
    with SessionLocal() as db:
        job = db.query(AnalysisJob).filter_by(id=job_id, user_id=user_id).first()
        if not job:
            return None
        steps = db.query(AnalysisStep).filter_by(job_id=job_id).order_by(AnalysisStep.id).all()
        return {
            "id": job.id, "kind": job.kind, "status": job.status,
            "final_content": decode_text(job.final_content), "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "steps": [{
                "id": s.step_id, "name": s.step_name, "status": s.status,
                "content": decode_text(s.content), "error": s.error, "attempts": s.attempts,
            } for s in steps],
        }


def load_job(job_id: str, user_id: int, kind: str) -> tuple[AnalysisJob, dict, dict[str, AnalysisStep]] | None:
    with SessionLocal() as db:
        job = db.query(AnalysisJob).filter_by(id=job_id, user_id=user_id, kind=kind).first()
        if not job:
            return None
        db.expunge(job)
        steps = db.query(AnalysisStep).filter_by(job_id=job_id).all()
        for step in steps:
            db.expunge(step)
        job.tender_text = decode_text(job.tender_text)
        job.context_json = decode_text(job.context_json)
        job.final_content = decode_text(job.final_content)
        for step in steps:
            step.content = decode_text(step.content)
        return job, decode_json(job.context_json, {}), {s.step_id: s for s in steps}


async def run_with_timeout_retry(operation: Callable[[], Awaitable[T]], job_id: str,
                                 step_id: str) -> T:
    last_error: Exception | None = None
    for attempt in range(STEP_MAX_ATTEMPTS):
        update_step(job_id, step_id, "running", error=None, increment_attempt=True)
        try:
            return await asyncio.wait_for(operation(), timeout=STEP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            last_error = TimeoutError(
                f"Timed out after {STEP_TIMEOUT_SECONDS} seconds (attempt {attempt + 1}/{STEP_MAX_ATTEMPTS})"
            )
        except Exception as exc:
            last_error = exc
        if attempt + 1 < STEP_MAX_ATTEMPTS:
            await asyncio.sleep(min(2 ** attempt, 5))
    assert last_error is not None
    raise last_error
