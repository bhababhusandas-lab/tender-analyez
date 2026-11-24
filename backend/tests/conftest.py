# backend/tests/conftest.py
"""Shared fixtures. Points the app at a throwaway SQLite DB and upload dir.

The environment must be set before any `app.*` module is imported, because
`app.core.db.session` and the upload modules read these variables at import.
"""
import os
import tempfile
import itertools

_TMP = tempfile.mkdtemp(prefix="taa-tests-")
# Force these unconditionally (not setdefault): if the shell already has
# DATABASE_PATH/UPLOAD_DIR set, setdefault would silently run tests against
# that real database/upload dir instead of the throwaway one.
os.environ["DATABASE_PATH"] = os.path.join(_TMP, "test.db")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")

import pytest  # noqa: E402

from app.core.db import models  # noqa: E402
from app.core.db.session import Base, SessionLocal, engine  # noqa: E402

Base.metadata.create_all(bind=engine)
_emails = itertools.count(1)

# The DB file above is created once and shared across the whole test
# session (no per-test truncation), so tests must scope their queries to
# the users/rows they themselves created rather than assuming a clean table.


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def make_user(db):
    def _make(plan: str = "enterprise", is_admin: bool = False) -> models.User:
        user = models.User(
            email=f"user{next(_emails)}@test.local", password_hash="x",
            plan=plan, is_admin=is_admin, email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    return _make


@pytest.fixture
def client_as():
    """Return a TestClient authenticated as the given user (no startup events)."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.security.auth import get_current_user

    def _client(user: models.User) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _client
    app.dependency_overrides.clear()
