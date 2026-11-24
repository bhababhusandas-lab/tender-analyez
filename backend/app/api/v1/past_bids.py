import io
import shutil
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import PastBid, User
from app.core.security.auth import get_current_user
from app.core.compression import decode_text, encode_text

router = APIRouter()


def extract_text(data: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            return ""
    return data.decode("utf-8", errors="ignore")


def _to_dict(p: PastBid) -> dict:
    d = {c.name: getattr(p, c.name) for c in p.__table__.columns}
    d.pop("text_content", None)
    d["text_length"] = len(decode_text(p.text_content))
    return d


@router.post("/past-bids/upload")
async def upload_past_bid(
    title: str = Form(...),
    department: str = Form(""),
    contract_value: str = Form(""),
    year_won: str = Form(""),
    outcome: str = Form("won"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = await file.read()
    text = extract_text(raw, file.filename or "")
    if not text.strip():
        text = raw.decode("utf-8", errors="ignore")

    pb = PastBid(
        user_id=user.id,
        title=title,
        department=department,
        contract_value=contract_value,
        year_won=year_won,
        outcome=outcome,
        original_filename=file.filename or "",
        text_content=encode_text(text),
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return _to_dict(pb)


@router.get("/past-bids")
def list_past_bids(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_to_dict(p) for p in db.query(PastBid).filter(PastBid.user_id == user.id).order_by(PastBid.uploaded_at.desc()).all()]


@router.delete("/past-bids/{pid}")
def delete_past_bid(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(PastBid).filter(PastBid.id == pid, PastBid.user_id == user.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(p)
    db.commit()
    return {"deleted": pid}


def get_past_bids_context(db: Session, user_id: int | None = None, max_bids: int = 3) -> str:
    """Returns text of recent past winning bids to inject into Technical Expert prompt."""
    if user_id is None:
        return ""
    bids = db.query(PastBid).filter(PastBid.user_id == user_id, PastBid.outcome == "won").order_by(PastBid.uploaded_at.desc()).limit(max_bids).all()
    if not bids:
        return ""
    parts = ["\n\n=== PAST WINNING PROPOSALS (Reference) ==="]
    for b in bids:
        parts.append(f"\n--- {b.title} | {b.department} | ₹{b.contract_value} | {b.year_won} ---")
        parts.append(decode_text(b.text_content)[:3000])
    parts.append("=== END PAST PROPOSALS ===")
    return "\n".join(parts)
