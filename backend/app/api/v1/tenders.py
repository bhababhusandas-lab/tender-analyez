"""Tender history API (mounted under /tender-history). Every query is scoped
to the signed-in user."""
import asyncio
import json
import re
from types import SimpleNamespace

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import tender_history as th
from app.core.analysis_jobs import get_job_payload
from app.core.db.models import Tender, TenderHistoryDocument, TenderVersion, User
from app.core.db.session import get_db
from app.core.limits import check_usage, record_usage
from app.core.security.auth import get_current_user
from app.core.tender_evidence import prefer_newest_evidence
from app.core.tender_inputs import read_uploads

router = APIRouter()
_COMPARED = ("decision", "quote", "deadline")


def _owned(db: Session, tender_id: int, user: User) -> Tender:
    tender = db.query(Tender).filter(Tender.id == tender_id, Tender.user_id == user.id).first()
    if tender is None:
        raise HTTPException(status_code=404, detail="Tender not found")
    return tender


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _list_item(db: Session, tender: Tender) -> dict:
    running = db.query(TenderVersion).filter_by(tender_id=tender.id, status="running").first()
    active = running is not None and th.is_active_run(db, running)
    latest = (db.query(TenderVersion).filter(TenderVersion.tender_id == tender.id, TenderVersion.number.isnot(None))
              .order_by(TenderVersion.number.desc()).first())
    finished_since_view = latest is not None and latest.completed_at is not None and (
        tender.last_viewed_at is None or latest.completed_at > tender.last_viewed_at)
    return {
        "id": tender.id, "name": tender.name, "reference_no": tender.reference_no,
        "latest_decision": tender.latest_decision, "latest_deadline": tender.latest_deadline,
        "version_count": tender.version_count, "last_activity_at": _iso(tender.last_activity_at),
        "unread": bool(finished_since_view), "running": active,
        "latest_kind": latest.kind if latest else (running.kind if running else "pipeline"),
        "latest_job_id": latest.analysis_job_id if latest else (running.analysis_job_id if running else None),
        "bid_id": tender.bid_id,
    }


@router.get("/tender-history")
def list_tenders(q: str = "", limit: int = 20, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Tender).filter(Tender.user_id == user.id)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter((Tender.name.ilike(like)) | (Tender.reference_no.ilike(like)))
    tenders = query.order_by(Tender.last_activity_at.desc(), Tender.id.desc()).limit(max(1, min(limit, 200))).all()
    return {"items": [_list_item(db, t) for t in tenders]}


@router.get("/tender-history/{tender_id}")
def tender_detail(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tender = _owned(db, tender_id, user)
    versions = db.query(TenderVersion).filter_by(tender_id=tender.id).order_by(TenderVersion.id.desc()).all()
    numbered = sorted((v for v in versions if v.number), key=lambda v: v.number)
    previous = {v.number: numbered[i - 1] for i, v in enumerate(numbered) if i > 0}
    out_versions = []
    for v in versions:
        before = previous.get(v.number) if v.number else None
        changes = [
            {"field": f, "before": getattr(before, f), "after": getattr(v, f)}
            for f in _COMPARED if before is not None and getattr(before, f) and getattr(v, f) and getattr(before, f) != getattr(v, f)
        ]
        out_versions.append({
            "id": v.id, "number": v.number, "label": v.label, "kind": v.kind, "status": v.status, "note": v.note,
            "decision": v.decision, "quote": v.quote, "deadline": v.deadline, "job_id": v.analysis_job_id,
            "created_at": _iso(v.created_at), "completed_at": _iso(v.completed_at), "changes": changes,
        })
    version_numbers = {v.id: v.number for v in versions}
    documents = [{
        "id": d.id, "filename": d.original_filename, "size": d.file_size, "mime_type": d.mime_type,
        "version_id": d.version_id, "version_number": version_numbers.get(d.version_id),
        "uploaded_at": _iso(d.uploaded_at),
    } for d in th.documents_for(db, tender.id)]
    return {**_list_item(db, tender), "versions": out_versions, "documents": documents}


@router.post("/tender-history/{tender_id}/viewed")
def mark_viewed(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from datetime import datetime
    tender = _owned(db, tender_id, user)
    tender.last_viewed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)


@router.patch("/tender-history/{tender_id}")
def rename(tender_id: int, body: RenameIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tender = _owned(db, tender_id, user)
    tender.name = body.name.strip()
    db.commit()
    return _list_item(db, tender)


@router.delete("/tender-history/{tender_id}")
def delete_tender(tender_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tender = _owned(db, tender_id, user)
    th.delete_tender(db, tender)
    return {"ok": True}


@router.get("/tender-history/{tender_id}/documents/{doc_id}")
def download_document(tender_id: int, doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tender = _owned(db, tender_id, user)
    doc = db.query(TenderHistoryDocument).filter_by(id=doc_id, tender_id=tender.id).first()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=th.read_document_bytes(doc), media_type=doc.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{re.sub(r"[^A-Za-z0-9._ -]", "_", doc.original_filename)}"'},
    )


@router.get("/tender-history/{tender_id}/versions/{number}/export")
def export_version(tender_id: int, number: int, full: bool = False,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.api.v1.export import build_pdf

    tender = _owned(db, tender_id, user)
    version = db.query(TenderVersion).filter_by(tender_id=tender.id, number=number).first()
    if version is None or not version.analysis_job_id:
        raise HTTPException(status_code=404, detail="Version not found")
    payload = get_job_payload(version.analysis_job_id, user.id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Version not found")
    results = {s["id"]: s["content"] for s in payload["steps"] if s["id"] != "md-final" and s["content"]}
    results["final"] = payload["final_content"]
    report = SimpleNamespace(
        tender_name=tender.name, department="", portal="", reference_no=tender.reference_no,
        submission_deadline=version.deadline,
        recommended_quote="" if version.quote in ("", "Not calculable") else version.quote,
        bid_confidence="", pipeline_result=json.dumps(results),
    )
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", tender.name)[:50]
    return FileResponse(build_pdf(report, full=full), media_type="application/pdf",
                        filename=f"{safe}_v{number}{'_Full' if full else ''}.pdf")


@router.post("/tender-history/{tender_id}/reanalyze")
async def reanalyze(tender_id: int, kind: str = Form("pipeline"), note: str = Form(""),
                    files: list[UploadFile] = File(default=[]),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tender = _owned(db, tender_id, user)
    if kind not in ("pipeline", "roadmap"):
        raise HTTPException(status_code=400, detail="Choose Bid Pipeline or 7-Phase Analysis.")
    if not files and not note.strip():
        raise HTTPException(status_code=400, detail="Add a file or a note to re-analyse.")
    running = db.query(TenderVersion).filter_by(tender_id=tender.id, status="running").first()
    if running is not None:
        if th.is_active_run(db, running):
            raise HTTPException(status_code=409, detail="An analysis of this tender is already running.")
        # Stale: left behind by a crashed/restarted process. Don't let it
        # block a new re-analysis forever.
        running.status = "failed"
        db.commit()
    # Reserve the running version right after the 409 check, with nothing
    # awaited in between, so two concurrent requests can't both pass the
    # check and both start a job.
    reserved = th.reserve_run(db, tender, kind, note)

    def _release_reservation() -> None:
        db.delete(reserved)
        db.commit()

    try:
        ok, info = check_usage(user, db, kind)
        if not ok:
            raise HTTPException(status_code=402, detail=info)
        docs, errors = await read_uploads(files)
        if errors:
            raise HTTPException(status_code=400, detail=" ".join(errors))

        raw_text, layers = th.build_reanalysis_input(db, tender, new_docs=docs, note=note, exclude_version_id=reserved.id)
        evidence = prefer_newest_evidence(layers)
        record_usage(db, user.id, kind)
        if kind == "pipeline":
            from app.api.v1 import tender_analysis
            job_id = tender_analysis.start_pipeline_job(db, user, raw_text, evidence=evidence)
        else:
            from app.api.v1 import tender_roadmap
            job_id = tender_roadmap.start_roadmap_job(db, user, raw_text, evidence=evidence)
    except Exception:
        db.rollback()
        _release_reservation()
        raise

    try:
        _, version = await asyncio.to_thread(
            th.start_run, db, user.id, tender=tender, kind=kind, job_id=job_id,
            docs=docs, pasted_text="", note=note, name_hint=tender.name, version=reserved,
        )
    except Exception as exc:  # the job is already running; the reserved version must not be lost
        db.rollback()
        print(f"[history] could not record re-analysis run for job {job_id}: {exc}")
        try:
            reserved.analysis_job_id = job_id
            db.commit()
        except Exception as exc2:
            db.rollback()
            print(f"[history] could not save job id on reserved version {reserved.id}: {exc2}")
        version = reserved
    return {"tender_id": tender.id, "job_id": job_id, "kind": kind, "version_id": version.id}
