"""Deadline notifications, scoped to the signed-in user."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.tenders import _list_item
from app.core import deadline_alerts as da
from app.core.db.models import User
from app.core.db.session import get_db
from app.core.security.auth import get_current_user

router = APIRouter()


class ReadIn(BaseModel):
    tender_id: int | None = None


@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    alerts = da.current_alerts(db, user.id)
    seen = da.read_keys(db, user.id)
    items = []
    for a in alerts:
        info = _list_item(db, a.tender)
        items.append({
            "tender_id": a.tender.id, "name": a.tender.name,
            "deadline_iso": a.deadline.isoformat(), "deadline_text": a.tender.latest_deadline,
            "days_left": a.days_left, "stage": a.stage, "message": da.alert_message(a),
            "unread": (a.tender.id, a.stage) not in seen,
            "latest_kind": info["latest_kind"], "latest_job_id": info["latest_job_id"],
        })
    return {"unread_count": sum(1 for i in items if i["unread"]), "items": items}


@router.post("/notifications/read")
def mark_notifications_read(body: ReadIn | None = None, db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    alerts = da.current_alerts(db, user.id)
    tender_id = body.tender_id if body else None
    if tender_id is not None:
        alerts = [a for a in alerts if a.tender.id == tender_id]
    da.mark_read(db, user.id, alerts)
    return {"ok": True, "marked": len(alerts)}
