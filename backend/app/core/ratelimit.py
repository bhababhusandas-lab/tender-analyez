"""Per-IP API rate limiting via slowapi.

Limits chosen to be generous for normal users, strict for abuse vectors:
- Auth endpoints (login/signup/verify) are the strictest — they're the brute-force surface
- All other endpoints share a generous default
"""
from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_id(request) -> str:
    """Identify client by real IP — X-Forwarded-For (set by nginx) trumps peer IP."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=_client_id,
    default_limits=["120/minute"],
    # headers_enabled=False — slowapi tries to inject X-RateLimit-* headers, which conflicts
    # with FastAPI endpoints that use response_model (returns Pydantic, not Response). Limit
    # still enforced; clients just don't see the remaining-quota header.
    headers_enabled=False,
)
