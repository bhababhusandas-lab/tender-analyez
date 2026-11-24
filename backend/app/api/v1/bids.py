import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import Bid, Tender, User
from app.core.security.auth import get_current_user

router = APIRouter()

STATUSES = ["draft", "submitted", "won", "lost", "withdrawn"]


class BidIn(BaseModel):
    tender_name: str
    reference_no: str = ""
    portal: str = ""
    department: str = ""
    estimated_value: str = ""
    emd_amount: str = ""
    submission_deadline: str = ""
    recommended_quote: str = ""
    bid_confidence: str = ""
    status: str = "draft"
    pipeline_result: str = "{}"
    tender_text: str = ""
    notes: str = ""
    tender_id: int | None = None


class StatusUpdate(BaseModel):
    status: str
    notes: str = ""


def _to_dict(b: Bid) -> dict:
    return {c.name: getattr(b, c.name) for c in b.__table__.columns}


@router.get("/bids")
def list_bids(status: str = "", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Bid).filter(Bid.user_id == user.id)
    if status:
        q = q.filter(Bid.status == status)
    bids = q.order_by(Bid.created_at.desc()).all()
    return [_to_dict(b) for b in bids]


@router.post("/bids")
def create_bid(body: BidIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = body.model_dump()
    tender_id = data.pop("tender_id", None)
    bid = Bid(**data, user_id=user.id)
    db.add(bid)
    db.commit()
    db.refresh(bid)
    if tender_id is not None:
        tender = db.query(Tender).filter(Tender.id == tender_id, Tender.user_id == user.id).first()
        if tender is not None:
            existing = db.query(Bid).filter(Bid.id == tender.bid_id).first() if tender.bid_id is not None else None
            if existing is None:
                tender.bid_id = bid.id
                db.commit()
    return _to_dict(bid)


@router.get("/bids/{bid_id}")
def get_bid(bid_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bid = db.query(Bid).filter(Bid.id == bid_id, Bid.user_id == user.id).first()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    return _to_dict(bid)


@router.patch("/bids/{bid_id}/status")
def update_status(bid_id: int, body: StatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bid = db.query(Bid).filter(Bid.id == bid_id, Bid.user_id == user.id).first()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    if body.status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use: {STATUSES}")
    bid.status = body.status
    if body.notes:
        bid.notes = body.notes
    db.commit()
    return _to_dict(bid)


@router.delete("/bids/{bid_id}")
def delete_bid(bid_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bid = db.query(Bid).filter(Bid.id == bid_id, Bid.user_id == user.id).first()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    db.delete(bid)
    db.commit()
    return {"deleted": bid_id}


@router.get("/bids/stats/summary")
def bid_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    all_bids = db.query(Bid).filter(Bid.user_id == user.id).all()
    return {
        "total": len(all_bids),
        "draft": sum(1 for b in all_bids if b.status == "draft"),
        "submitted": sum(1 for b in all_bids if b.status == "submitted"),
        "won": sum(1 for b in all_bids if b.status == "won"),
        "lost": sum(1 for b in all_bids if b.status == "lost"),
        "withdrawn": sum(1 for b in all_bids if b.status == "withdrawn"),
    }
