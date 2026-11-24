"""Deadline alert stages for a user's tenders (all dates are Asia/Kolkata)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.db.models import Bid, NotificationRead, Tender
from app.core.tender_evidence import _parse_date, _parse_time

IST = timezone(timedelta(hours=5, minutes=30), "IST")
CLOSED_BID_STATUSES = {"submitted", "won", "lost", "withdrawn"}
_ORDER = {"overdue": 0, "today": 1, "1": 2, "3": 3, "5": 4, "7": 5}


def now_ist() -> datetime:
    """Current time in IST. Tests patch this for determinism."""
    return datetime.now(IST)


def parse_deadline(text: str) -> datetime | None:
    """Parse a free-form deadline into an aware IST datetime (end of day if no time)."""
    if not text or not text.strip():
        return None
    iso = _parse_date(text)
    if not iso:
        return None
    try:
        day = date.fromisoformat(iso)
        clock = _parse_time(text)
        t = time.fromisoformat(clock) if clock else time(23, 59, 59)
    except ValueError:
        return None
    return datetime.combine(day, t, tzinfo=IST)


def stage_for(days_left: int) -> str | None:
    if days_left < -2 or days_left > 7:
        return None
    if days_left < 0:
        return "overdue"
    if days_left == 0:
        return "today"
    if days_left == 1:
        return "1"
    if days_left <= 3:
        return "3"
    if days_left <= 5:
        return "5"
    return "7"


@dataclass
class Alert:
    tender: Tender
    deadline: datetime
    days_left: int
    stage: str


def _message(name: str, days_left: int, stage: str) -> str:
    if stage == "overdue":
        n = -days_left
        return f"Deadline passed {n} day{'s' if n != 1 else ''} ago: {name}"
    if stage == "today":
        return f"Deadline is today: {name}"
    return f"{days_left} day{'s' if days_left != 1 else ''} left: {name}"


def current_alerts(db: Session, user_id: int) -> list[Alert]:
    today = now_ist().date()
    rows = (db.query(Tender, Bid.status).outerjoin(Bid, Bid.id == Tender.bid_id)
            .filter(Tender.user_id == user_id).all())
    alerts: list[Alert] = []
    for tender, bid_status in rows:
        if (bid_status or "").lower() in CLOSED_BID_STATUSES:
            continue
        deadline = parse_deadline(tender.latest_deadline or "")
        if deadline is None:
            continue
        days_left = (deadline.date() - today).days
        stage = stage_for(days_left)
        if stage:
            alerts.append(Alert(tender, deadline, days_left, stage))
    alerts.sort(key=lambda a: (_ORDER[a.stage], a.deadline, a.tender.id))
    return alerts


def read_keys(db: Session, user_id: int) -> set[tuple[int, str]]:
    return {(r.tender_id, r.stage) for r in db.query(NotificationRead).filter_by(user_id=user_id)}


def mark_read(db: Session, user_id: int, alerts: list[Alert]) -> None:
    seen = read_keys(db, user_id)
    for a in alerts:
        if (a.tender.id, a.stage) not in seen:
            db.add(NotificationRead(user_id=user_id, tender_id=a.tender.id, stage=a.stage))
    db.commit()


def alert_message(alert: Alert) -> str:
    return _message(alert.tender.name, alert.days_left, alert.stage)
