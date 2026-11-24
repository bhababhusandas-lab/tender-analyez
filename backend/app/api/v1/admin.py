"""Admin endpoints — list/manage users + platform stats. Admin-only."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.db.session import get_db
from app.core.db.models import User, Bid, Document, PastBid, CompanyProfile, UsageEvent
from app.core.security.auth import get_current_user

router = APIRouter()


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


class AdminUserRow(BaseModel):
    id: int
    email: str
    full_name: str
    company_name: str
    phone: str
    plan: str
    trial_ends_at: datetime | None
    is_admin: bool
    is_active: bool
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None
    bids_count: int
    documents_count: int
    usage_total: int
    usage_24h: int
    usage_30d: int


@router.get("/admin/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from datetime import timedelta
    users = db.query(User).order_by(User.created_at.desc()).all()
    bid_counts = dict(db.query(Bid.user_id, func.count(Bid.id)).group_by(Bid.user_id).all())
    doc_counts = dict(db.query(Document.user_id, func.count(Document.id)).group_by(Document.user_id).all())

    # Usage totals (lifetime / 24h / 30d) for each user
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)
    since_30d = now - timedelta(days=30)
    usage_total = dict(db.query(UsageEvent.user_id, func.count(UsageEvent.id)).group_by(UsageEvent.user_id).all())
    usage_24h   = dict(db.query(UsageEvent.user_id, func.count(UsageEvent.id)).filter(UsageEvent.created_at >= since_24h).group_by(UsageEvent.user_id).all())
    usage_30d   = dict(db.query(UsageEvent.user_id, func.count(UsageEvent.id)).filter(UsageEvent.created_at >= since_30d).group_by(UsageEvent.user_id).all())

    return [
        AdminUserRow(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            company_name=u.company_name,
            phone=u.phone,
            plan=u.plan,
            trial_ends_at=u.trial_ends_at,
            is_admin=u.is_admin,
            is_active=u.is_active,
            email_verified=u.email_verified,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
            bids_count=bid_counts.get(u.id, 0),
            documents_count=doc_counts.get(u.id, 0),
            usage_total=usage_total.get(u.id, 0),
            usage_24h=usage_24h.get(u.id, 0),
            usage_30d=usage_30d.get(u.id, 0),
        ).model_dump()
        for u in users
    ]


@router.get("/admin/stats")
def platform_stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    # Keep the response key for older admin clients while counting both legacy
    # trial rows and accounts on the current permanent Free plan.
    trial_users = db.query(User).filter(User.plan.in_(("trial", "free"))).count()
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_this_week = db.query(User).filter(User.created_at >= week_ago).count()
    active_this_week = db.query(User).filter(User.last_login_at >= week_ago).count()
    plan_breakdown = dict(db.query(User.plan, func.count(User.id)).group_by(User.plan).all())

    return {
        "total_users": total_users,
        "active_users": active_users,
        "trial_users": trial_users,
        "new_this_week": new_this_week,
        "active_this_week": active_this_week,
        "plan_breakdown": plan_breakdown,
        "total_bids": db.query(Bid).count(),
        "total_documents": db.query(Document).count(),
        "total_past_bids": db.query(PastBid).count(),
    }


class PlanUpdate(BaseModel):
    plan: str  # free / starter / growth / professional / enterprise


@router.patch("/admin/users/{user_id}/plan")
def update_user_plan(user_id: int, body: PlanUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if body.plan not in ("free", "starter", "growth", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="Invalid plan")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.plan = body.plan
    db.commit()
    return {"ok": True, "user_id": user_id, "plan": body.plan}


@router.patch("/admin/users/{user_id}/toggle-active")
def toggle_active(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.is_active = not u.is_active
    db.commit()
    return {"ok": True, "user_id": user_id, "is_active": u.is_active}


@router.post("/admin/users/{user_id}/force-verify")
def force_verify(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Admin shortcut to manually verify a user — useful while SMTP isn't configured."""
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.email_verified = True
    u.verification_code = None
    u.verification_code_sent_at = None
    db.commit()
    return {"ok": True, "user_id": user_id, "email_verified": True}


@router.get("/admin/users/{user_id}/verification-code")
def peek_verification_code(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Admin shortcut to view a pending verification code (for users who claim they didn't receive the email)."""
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": user_id,
        "email": u.email,
        "email_verified": u.email_verified,
        "verification_code": u.verification_code,
        "verification_code_sent_at": u.verification_code_sent_at,
    }
