"""GET /api/v1/usage — current usage + limits for the logged-in user."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import User
from app.core.security.auth import get_current_user
from app.core.limits import usage_snapshot

router = APIRouter()


@router.get("/usage")
def my_usage(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return usage_snapshot(user, db)
