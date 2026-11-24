"""Authentication utilities: password hashing, JWT, current-user dependency."""
import os
import hashlib
import hmac
import secrets
import base64
import json
import time
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import User

# JWT secret — from env var, fallback to a random per-instance secret (logs out users on restart, but that's safer than a hardcoded default)
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
JWT_ALGO = "HS256"
JWT_EXPIRY_SECONDS = 7 * 24 * 3600  # 7 days


# === Password hashing (PBKDF2 — stdlib only, no extra deps) ===
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return base64.urlsafe_b64encode(salt + h).decode("ascii")


def verify_password(password: str, stored: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(stored.encode("ascii"))
        salt, h = raw[:16], raw[16:]
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return hmac.compare_digest(h, check)
    except Exception:
        return False


# === JWT (HS256 — minimal hand-rolled, no external lib) ===
def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def make_token(user_id: int, email: str) -> str:
    header = _b64u(json.dumps({"alg": JWT_ALGO, "typ": "JWT"}, separators=(",", ":")).encode())
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    }
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64u(sig)}"


def verify_token(token: str) -> dict | None:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _b64u_decode(sig_b64)):
            return None
        payload = json.loads(_b64u_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


# === FastAPI dependencies ===
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = verify_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == int(payload["sub"]), User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None when not authenticated (no 401)."""
    if not creds or not creds.credentials:
        return None
    payload = verify_token(creds.credentials)
    if not payload:
        return None
    return db.query(User).filter(User.id == int(payload["sub"]), User.is_active == True).first()


def trial_end() -> datetime:
    return datetime.utcnow() + timedelta(days=7)
