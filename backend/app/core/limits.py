"""Authoritative subscription limits for analyses and the Document Vault."""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.db.models import UsageEvent, User


# None means unlimited. ``trial`` remains as a compatibility alias for accounts
# created before the permanent Free plan replaced the old seven-day trial.
PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "free":         {"pipeline_monthly": 5,  "roadmap_monthly": 0,    "vault_documents": 25},
    "trial":        {"pipeline_monthly": 5,  "roadmap_monthly": 0,    "vault_documents": 25},
    "starter":      {"pipeline_monthly": 10, "roadmap_monthly": 1,    "vault_documents": 50},
    "growth":       {"pipeline_monthly": 25, "roadmap_monthly": 3,    "vault_documents": 70},
    "professional": {"pipeline_monthly": None, "roadmap_monthly": None, "vault_documents": None},
    "enterprise":   {"pipeline_monthly": None, "roadmap_monthly": None, "vault_documents": None},
}


def plan_limits(plan: str | None) -> dict[str, int | None]:
    return PLAN_LIMITS.get(plan or "free", PLAN_LIMITS["free"])


def _count(db: Session, user_id: int, since: datetime | None, kind: str | None = None) -> int:
    query = db.query(UsageEvent).filter(UsageEvent.user_id == user_id)
    if since is not None:
        query = query.filter(UsageEvent.created_at >= since)
    if kind is not None:
        query = query.filter(UsageEvent.kind == kind)
    return query.count()


def check_usage(user: User, db: Session, kind: str = "pipeline") -> tuple[bool, dict]:
    """Return whether a pipeline or roadmap run is allowed for the rolling 30-day window."""
    if user.is_admin:
        return True, {}

    plan = "free" if (user.plan or "free") == "trial" else (user.plan or "free")
    limits = plan_limits(plan)
    limit_key = "roadmap_monthly" if kind == "roadmap" else "pipeline_monthly"
    limit = limits[limit_key]
    if limit is None:
        return True, {}

    now = datetime.utcnow()
    used = _count(db, user.id, now - timedelta(days=30), kind)
    if used >= limit:
        product = "7-Phase Analysis" if kind == "roadmap" else "Bid Pipeline"
        return False, {
            "code": "USAGE_LIMIT_EXCEEDED",
            "limit_type": "monthly",
            "kind": kind,
            "plan": plan,
            "used": used,
            "limit": limit,
            "message": f"Your {plan.title()} plan includes {limit} {product} run{'s' if limit != 1 else ''} per month.",
        }
    return True, {}


def record_usage(db: Session, user_id: int, kind: str = "pipeline") -> None:
    db.add(UsageEvent(user_id=user_id, kind=kind))
    db.commit()


def usage_snapshot(user: User, db: Session) -> dict:
    """Return plan-specific pipeline, roadmap, and vault limits plus current usage."""
    plan = "free" if (user.plan or "free") == "trial" else (user.plan or "free")
    limits = plan_limits(plan)
    now = datetime.utcnow()
    since_30d = now - timedelta(days=30)
    pipeline_30d = _count(db, user.id, since_30d, "pipeline")
    roadmap_30d = _count(db, user.id, since_30d, "roadmap")
    return {
        "plan": plan,
        "limits": {**limits, "total": None, "daily": None, "monthly": limits["pipeline_monthly"]},
        "used_total": _count(db, user.id, None),
        "used_24h": _count(db, user.id, now - timedelta(hours=24)),
        "used_30d": pipeline_30d,
        "pipeline_used_30d": pipeline_30d,
        "roadmap_used_30d": roadmap_30d,
    }
