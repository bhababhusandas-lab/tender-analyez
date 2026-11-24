import hashlib
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.db.session import get_db
from app.core.db.models import Document, User
from app.core.security.auth import get_current_user
from app.core.limits import plan_limits
from app.core.compression import decode_bytes, encode_bytes

router = APIRouter()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent.parent.parent.parent / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = [
    "Financial",
    "Legal & Registration",
    "Technical Credentials",
    "HR & Compliance",
    "Digital Signature (DSC)",
    "Other",
]


def expiry_status(expiry_date: date | None) -> str:
    if not expiry_date:
        return "no-expiry"
    today = date.today()
    delta = (expiry_date - today).days
    if delta < 0:
        return "expired"
    if delta <= 30:
        return "expiring-soon"
    return "valid"


def doc_to_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "name": doc.name,
        "category": doc.category,
        "original_filename": doc.original_filename,
        "file_size": doc.file_size,
        "stored_size": doc.stored_size or doc.file_size,
        "sha256": doc.sha256 or None,
        "compression": doc.compression or "identity",
        "mime_type": doc.mime_type,
        "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
        "expiry_status": expiry_status(doc.expiry_date),
        "notes": doc.notes,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


@router.post("/documents/upload")
async def upload_document(
    name: str = Form(...),
    category: str = Form(...),
    expiry_date: str = Form(""),
    notes: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing_count = db.query(Document).filter(Document.user_id == user.id).count()
    vault_limit = plan_limits(user.plan).get("vault_documents")
    if not user.is_admin and vault_limit is not None and existing_count >= vault_limit:
        raise HTTPException(status_code=402, detail={
            "code": "DOCUMENT_LIMIT_EXCEEDED",
            "plan": "free" if user.plan == "trial" else (user.plan or "free"),
            "used": existing_count,
            "limit": vault_limit,
            "message": f"Your plan includes up to {vault_limit} documents in the Document Vault.",
        })

    raw = await file.read()
    checksum = hashlib.sha256(raw).hexdigest()
    duplicate = db.query(Document).filter(Document.sha256 == checksum).first()
    stored_filename = f"{checksum}-{uuid.uuid4().hex[:12]}.blob"
    dest = UPLOAD_DIR / stored_filename
    if duplicate and (UPLOAD_DIR / duplicate.stored_filename).is_file():
        duplicate_path = UPLOAD_DIR / duplicate.stored_filename
        try:
            os.link(duplicate_path, dest)
        except OSError:
            dest.write_bytes(duplicate_path.read_bytes())
        stored_size = duplicate.stored_size or duplicate_path.stat().st_size
        compression = duplicate.compression or "identity"
    else:
        encoded = encode_bytes(
            raw,
            content_type=file.content_type or "application/octet-stream",
            filename=file.filename or "file",
        )
        temporary = dest.with_suffix(".tmp")
        temporary.write_bytes(encoded.data)
        temporary.replace(dest)
        stored_size = len(encoded.data)
        compression = encoded.encoding

    parsed_expiry = None
    if expiry_date:
        try:
            parsed_expiry = date.fromisoformat(expiry_date)
        except ValueError:
            pass

    doc = Document(
        user_id=user.id,
        name=name,
        category=category,
        original_filename=file.filename or stored_filename,
        stored_filename=stored_filename,
        file_size=len(raw),
        stored_size=stored_size,
        sha256=checksum,
        compression=compression,
        mime_type=file.content_type or "application/octet-stream",
        expiry_date=parsed_expiry,
        notes=notes or None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc_to_dict(doc)


@router.get("/documents")
def list_documents(category: str = "", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Document).filter(Document.user_id == user.id)
    if category:
        q = q.filter(Document.category == category)
    docs = q.order_by(Document.uploaded_at.desc()).all()
    return [doc_to_dict(d) for d in docs]


@router.get("/documents/stats")
def get_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    all_docs = db.query(Document).filter(Document.user_id == user.id).all()
    total = len(all_docs)
    expired = sum(1 for d in all_docs if expiry_status(d.expiry_date) == "expired")
    expiring_soon = sum(1 for d in all_docs if expiry_status(d.expiry_date) == "expiring-soon")
    categories = {}
    for d in all_docs:
        categories[d.category] = categories.get(d.category, 0) + 1
    return {
        "total": total,
        "expired": expired,
        "expiring_soon": expiring_soon,
        "valid": total - expired - expiring_soon,
        "categories": categories,
    }


@router.get("/documents/{doc_id}/download")
def download_document(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    path = UPLOAD_DIR / doc.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    try:
        content = decode_bytes(path.read_bytes(), doc.compression or "identity")
    except (OSError, ValueError):
        raise HTTPException(status_code=500, detail="Stored file could not be decoded")
    if doc.sha256 and hashlib.sha256(content).hexdigest() != doc.sha256:
        raise HTTPException(status_code=500, detail="Stored file failed its integrity check")
    safe_name = (doc.original_filename or "document").replace('"', "_")
    return Response(
        content=content,
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Document-SHA256": doc.sha256 or hashlib.sha256(content).hexdigest(),
            "X-Storage-Compression": doc.compression or "identity",
        },
    )


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    path = UPLOAD_DIR / doc.stored_filename
    if path.exists():
        path.unlink()
    db.delete(doc)
    db.commit()
    return {"deleted": doc_id}
