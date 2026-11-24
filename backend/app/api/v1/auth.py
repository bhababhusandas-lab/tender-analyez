"""Auth endpoints: signup, login, verify email, current user."""
import os
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import User, CompanyProfile
from app.core.security.auth import (
    hash_password, verify_password, make_token, get_current_user
)
from app.core.email_sender import send_email
from app.core.ratelimit import limiter
from app.templates.emails import welcome_email, admin_new_signup_email, verification_code_email

router = APIRouter()

ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "admin@example.com").split(",")
    if e.strip()
}

VERIFICATION_CODE_TTL_MINUTES = 60

# Allow resend at most every 30 seconds to prevent abuse
RESEND_COOLDOWN_SECONDS = 30


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _code_expired(sent_at: datetime | None) -> bool:
    if not sent_at:
        return True
    return datetime.utcnow() - sent_at > timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES)


# === Schemas ===
class SignupIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    company_name: str = ""
    phone: str = ""

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class VerifyIn(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def code_format(cls, v: str) -> str:
        v = v.strip().replace(" ", "").replace("-", "")
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Code must be 6 digits")
        return v


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    company_name: str
    phone: str
    plan: str
    trial_ends_at: datetime | None
    is_admin: bool
    email_verified: bool
    created_at: datetime


class AuthOut(BaseModel):
    token: str
    user: UserOut


# === Endpoints ===
@router.post("/auth/signup", response_model=AuthOut)
@limiter.limit("5/minute;20/hour")
def signup(request: Request, payload: SignupIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists. Try logging in.")

    is_admin_user = email in ADMIN_EMAILS
    code = _new_code()

    # Admins/founders get the highest plan + auto-verified + no expiring trial
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        company_name=payload.company_name.strip(),
        phone=payload.phone.strip(),
        plan="enterprise" if is_admin_user else "free",
        trial_ends_at=None,
        is_admin=is_admin_user,
        is_active=True,
        email_verified=True if is_admin_user else False,
        verification_code=None if is_admin_user else code,
        verification_code_sent_at=None if is_admin_user else datetime.utcnow(),
        last_login_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Auto-create their empty company profile
    profile = CompanyProfile(user_id=user.id, company_name=payload.company_name.strip())
    db.add(profile)
    db.commit()

    # Fire-and-forget emails: verification code to user (skip for admin who is pre-verified)
    # + admin notification to founder addresses
    try:
        if not is_admin_user:
            vsubj, vhtml = verification_code_email(payload.full_name, code)
            send_email(to=email, subject=vsubj, html=vhtml)
        for admin_email in ADMIN_EMAILS:
            asubj, ahtml = admin_new_signup_email(payload.full_name, email, payload.company_name, payload.phone)
            send_email(to=admin_email, subject=asubj, html=ahtml)
    except Exception as e:
        print(f"[signup] email dispatch failed (non-fatal): {e}")

    # Token is issued so the frontend can call /auth/verify and /auth/verify/resend
    return AuthOut(token=make_token(user.id, user.email), user=UserOut.model_validate(user, from_attributes=True))


@router.post("/auth/login", response_model=AuthOut)
@limiter.limit("10/minute;100/hour")
def login(request: Request, payload: LoginIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Self-healing admin promotion: if the email is in the founder/admin list, make sure
    # they always have full access — admin flag, enterprise plan, verified email — even if
    # an earlier signup happened before this rule was added.
    if email in ADMIN_EMAILS:
        user.is_admin = True
        user.email_verified = True
        if user.plan != "enterprise":
            user.plan = "enterprise"
        user.verification_code = None
        user.verification_code_sent_at = None
        user.trial_ends_at = None
    elif user.plan == "trial":
        # Migrate accounts created under the former trial model.
        user.plan = "free"
        user.trial_ends_at = None

    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return AuthOut(token=make_token(user.id, user.email), user=UserOut.model_validate(user, from_attributes=True))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/auth/verify", response_model=UserOut)
@limiter.limit("10/minute;50/hour")
def verify_email(request: Request, payload: VerifyIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.email_verified:
        return UserOut.model_validate(user, from_attributes=True)

    if not user.verification_code or _code_expired(user.verification_code_sent_at):
        raise HTTPException(status_code=400, detail="Code has expired. Request a new one.")

    if payload.code != user.verification_code:
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    # Success
    user.email_verified = True
    user.verification_code = None
    user.verification_code_sent_at = None
    db.commit()
    db.refresh(user)

    # Welcome email after successful verification
    try:
        wsubj, whtml = welcome_email(user.full_name, user.company_name)
        send_email(to=user.email, subject=wsubj, html=whtml)
    except Exception as e:
        print(f"[verify] welcome email failed (non-fatal): {e}")

    return UserOut.model_validate(user, from_attributes=True)


@router.post("/auth/verify/resend")
@limiter.limit("3/minute;15/hour")
def resend_verification(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.email_verified:
        return {"ok": True, "message": "Already verified."}

    # Cooldown check
    if user.verification_code_sent_at:
        elapsed = (datetime.utcnow() - user.verification_code_sent_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {int(RESEND_COOLDOWN_SECONDS - elapsed)}s before requesting another code.",
            )

    code = _new_code()
    user.verification_code = code
    user.verification_code_sent_at = datetime.utcnow()
    db.commit()

    try:
        subj, html = verification_code_email(user.full_name, code)
        send_email(to=user.email, subject=subj, html=html)
    except Exception as e:
        print(f"[resend] email dispatch failed (non-fatal): {e}")

    return {"ok": True, "message": "A fresh verification code has been sent to your email."}
