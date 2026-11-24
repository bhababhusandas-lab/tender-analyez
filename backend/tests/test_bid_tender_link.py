"""Tests for linking Bid Tracker entries to tenders (Task 10)."""
from app.core.db.models import Tender


def _make_tender(db, user, name="SRDS"):
    tender = Tender(user_id=user.id, name=name)
    db.add(tender)
    db.commit()
    db.refresh(tender)
    return tender


def test_saving_a_bid_links_it_to_the_tender(db, make_user, client_as):
    user = make_user()
    tender = _make_tender(db, user)
    response = client_as(user).post("/api/v1/bids", json={"tender_name": "SRDS", "tender_id": tender.id})
    assert response.status_code == 200
    db.expire_all()
    assert db.get(Tender, tender.id).bid_id == response.json()["id"]


def test_cannot_link_a_bid_to_someone_elses_tender(db, make_user, client_as):
    owner, other = make_user(), make_user()
    tender = _make_tender(db, owner)
    response = client_as(other).post("/api/v1/bids", json={"tender_name": "x", "tender_id": tender.id})
    assert response.status_code == 200
    db.expire_all()
    assert db.get(Tender, tender.id).bid_id is None


def test_saving_a_bid_without_tender_id_still_works(db, make_user, client_as):
    user = make_user()
    response = client_as(user).post("/api/v1/bids", json={"tender_name": "no link"})
    assert response.status_code == 200
    assert "tender_id" not in response.json()


def test_saving_a_second_bid_does_not_overwrite_existing_link(db, make_user, client_as):
    user = make_user()
    tender = _make_tender(db, user)
    client = client_as(user)
    first = client.post("/api/v1/bids", json={"tender_name": "SRDS", "tender_id": tender.id})
    assert first.status_code == 200
    second = client.post("/api/v1/bids", json={"tender_name": "SRDS again", "tender_id": tender.id})
    assert second.status_code == 200
    db.expire_all()
    assert db.get(Tender, tender.id).bid_id == first.json()["id"]


def test_saving_a_bid_relinks_when_the_existing_bid_was_deleted(db, make_user, client_as):
    user = make_user()
    tender = _make_tender(db, user)
    client = client_as(user)
    first = client.post("/api/v1/bids", json={"tender_name": "SRDS", "tender_id": tender.id})
    assert first.status_code == 200
    del_response = client.delete(f"/api/v1/bids/{first.json()['id']}")
    assert del_response.status_code == 200
    second = client.post("/api/v1/bids", json={"tender_name": "SRDS again", "tender_id": tender.id})
    assert second.status_code == 200
    db.expire_all()
    assert db.get(Tender, tender.id).bid_id == second.json()["id"]


def test_saving_a_bid_with_nonexistent_tender_id_is_ignored(db, make_user, client_as):
    user = make_user()
    response = client_as(user).post("/api/v1/bids", json={"tender_name": "x", "tender_id": 999999})
    assert response.status_code == 200
