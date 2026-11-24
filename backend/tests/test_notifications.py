from datetime import date, datetime, timedelta

import pytest

from app.core import deadline_alerts as da
from app.core.db import models

TODAY = date(2026, 9, 20)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(da, "now_ist", lambda: datetime(2026, 9, 20, 10, 0, tzinfo=da.IST))


def _tender(db, user, days, text=None, name="T", bid_status=None):
    bid_id = None
    if bid_status:
        bid = models.Bid(user_id=user.id, tender_name=name, status=bid_status)
        db.add(bid)
        db.commit()
        bid_id = bid.id
    d = TODAY + timedelta(days=days)
    t = models.Tender(user_id=user.id, name=name, bid_id=bid_id,
                      latest_deadline=text or d.strftime("%d/%m/%Y 05:00 PM"))
    db.add(t)
    db.commit()
    return t.id


@pytest.mark.parametrize("days,stage", [
    (8, None), (7, "7"), (6, "7"), (5, "5"), (4, "5"), (3, "3"), (2, "3"),
    (1, "1"), (0, "today"), (-1, "overdue"), (-2, "overdue"), (-3, None)])
def test_stage_mapping(db, make_user, client_as, days, stage):
    user = make_user()
    tid = _tender(db, user, days)
    items = client_as(user).get("/api/v1/notifications").json()["items"]
    got = [i for i in items if i["tender_id"] == tid]
    if stage is None:
        assert got == []
    else:
        assert got[0]["stage"] == stage and got[0]["days_left"] == days


@pytest.mark.parametrize("text", [
    "30/09/2026 03:00 PM", "30.09.2026 17:00", "30 September 2026", "30.09.2026"])
def test_deadline_formats(text):
    parsed = da.parse_deadline(text)
    assert parsed.date() == date(2026, 9, 30)
    if "PM" in text or "17:00" in text:
        assert (parsed.hour, parsed.minute) == (15 if "PM" in text else 17, 0)
    elif "03" not in text:
        assert (parsed.hour, parsed.minute) == (23, 59)


def test_format_27_10():
    assert da.parse_deadline("27.10.2026 17:00").date() == date(2026, 10, 27)
    assert da.parse_deadline("not a date") is None


def test_unparseable_skipped(db, make_user, client_as):
    user = make_user()
    _tender(db, user, 0, text="TBD")
    assert client_as(user).get("/api/v1/notifications").json()["items"] == []


@pytest.mark.parametrize("status", ["submitted", "won", "lost", "withdrawn"])
def test_closed_bid_skipped(db, make_user, client_as, status):
    user = make_user()
    _tender(db, user, 2, bid_status=status)
    assert client_as(user).get("/api/v1/notifications").json()["items"] == []


def test_draft_bid_kept(db, make_user, client_as):
    user = make_user()
    _tender(db, user, 2, bid_status="draft")
    assert len(client_as(user).get("/api/v1/notifications").json()["items"]) == 1


def test_other_users_hidden(db, make_user, client_as):
    a, b = make_user(), make_user()
    tid = _tender(db, a, 2)
    c = client_as(b)
    assert c.get("/api/v1/notifications").json()["items"] == []
    c.post("/api/v1/notifications/read", json={"tender_id": tid})
    assert client_as(a).get("/api/v1/notifications").json()["unread_count"] == 1


def test_read_then_next_stage_unread(db, make_user, client_as, monkeypatch):
    user = make_user()
    _tender(db, user, 3)
    c = client_as(user)
    assert c.get("/api/v1/notifications").json()["unread_count"] == 1
    tid = c.get("/api/v1/notifications").json()["items"][0]["tender_id"]
    assert c.post("/api/v1/notifications/read", json={"tender_id": tid}).status_code == 200
    c.post("/api/v1/notifications/read", json={"tender_id": tid})  # idempotent
    assert c.get("/api/v1/notifications").json()["unread_count"] == 0
    monkeypatch.setattr(da, "now_ist", lambda: datetime(2026, 9, 22, 10, 0, tzinfo=da.IST))
    body = c.get("/api/v1/notifications").json()
    assert body["items"][0]["stage"] == "1" and body["unread_count"] == 1


def test_mark_all_and_order(db, make_user, client_as):
    user = make_user()
    _tender(db, user, 7, name="seven")
    _tender(db, user, 0, name="today")
    _tender(db, user, -1, name="late")
    c = client_as(user)
    body = c.get("/api/v1/notifications").json()
    assert [i["name"] for i in body["items"]] == ["late", "today", "seven"]
    assert body["unread_count"] == 3
    c.post("/api/v1/notifications/read", json={})
    c.post("/api/v1/notifications/read")
    body = c.get("/api/v1/notifications").json()
    assert body["unread_count"] == 0 and not any(i["unread"] for i in body["items"])
