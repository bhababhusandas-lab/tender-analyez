import json

from app.core import tender_history as th
from app.core.analysis_jobs import get_job_payload
from app.core.db.models import AnalysisJob, Bid, Tender, TenderHistoryDocument, TenderVersion


def test_backfill_creates_one_finished_version_per_bid_once(db, make_user):
    user = make_user()
    results = {"bid-manager": "manager", "final": "### **GO / NO-GO DECISION: NO-BID**"}
    bid = Bid(user_id=user.id, tender_name="Old bid", reference_no="OLD/1", tender_text="old tender text",
              pipeline_result=json.dumps(results), recommended_quote="Rs 1,00,000", submission_deadline="01.08.2026")
    empty = Bid(user_id=user.id, tender_name="Never analysed", pipeline_result="{}")
    db.add_all([bid, empty])
    db.commit()

    th.backfill_from_bids()
    th.backfill_from_bids()  # idempotent

    tenders = db.query(Tender).filter_by(user_id=user.id).all()
    assert [t.name for t in tenders] == ["Old bid"]
    tender = tenders[0]
    assert (tender.bid_id, tender.version_count, tender.latest_decision) == (bid.id, 1, "NO-BID")
    version = db.query(TenderVersion).filter_by(tender_id=tender.id).one()
    assert (version.number, version.status, version.label) == (1, "completed", "Original (from Bid Tracker)")
    payload = get_job_payload(version.analysis_job_id, user.id)
    assert payload["status"] == "completed"
    assert {s["id"]: s["content"] for s in payload["steps"]}["bid-manager"] == "manager"
    assert payload["final_content"].endswith("NO-BID**")
    doc = db.query(TenderHistoryDocument).filter_by(tender_id=tender.id).one()
    assert th.read_document_bytes(doc) == b"old tender text"


def test_backfill_skips_non_dict_pipeline_result_and_continues_to_later_bids(db, make_user):
    user = make_user()
    # A pipeline_result that parses to a list (not a dict) must be skipped,
    # not crash the loop and block bids that come after it.
    bad = Bid(user_id=user.id, tender_name="Bad shape", pipeline_result="[1, 2, 3]")
    good = Bid(user_id=user.id, tender_name="Good bid", pipeline_result=json.dumps({"final": "### GO"}))
    db.add_all([bad, good])
    db.commit()

    created = th.backfill_from_bids()

    assert created == 1
    tenders = db.query(Tender).filter_by(user_id=user.id).all()
    assert [t.name for t in tenders] == ["Good bid"]
    assert db.query(Tender).filter_by(bid_id=bad.id).first() is None


def test_backfill_never_modifies_the_source_bid(db, make_user):
    user = make_user()
    original_pipeline_result = json.dumps({
        "final": "### **FINAL RECOMMENDED QUOTE**\n**Rs 38,40,000**",
    })
    bid = Bid(user_id=user.id, tender_name="Quote bid", pipeline_result=original_pipeline_result,
              recommended_quote="₹38.4 L (approx)", submission_deadline="15.09.2026", status="draft")
    db.add(bid)
    db.commit()
    bid_id = bid.id

    created = th.backfill_from_bids()
    assert created == 1

    db.expire_all()
    refreshed = db.get(Bid, bid_id)
    # The bid itself must come out byte-for-byte unchanged: no re-derived
    # quote/deadline/pipeline_result/status from summarize_result's parse of
    # the final text, which here would find a different-looking quote.
    assert refreshed.recommended_quote == "₹38.4 L (approx)"
    assert refreshed.submission_deadline == "15.09.2026"
    assert refreshed.pipeline_result == original_pipeline_result
    assert refreshed.status == "draft"

    tender = db.query(Tender).filter_by(bid_id=bid_id).one()
    version = db.query(TenderVersion).filter_by(tender_id=tender.id).one()
    # The version/tender carry the bid's quote verbatim, not a re-parsed one.
    assert version.quote == "₹38.4 L (approx)"
    assert tender.latest_quote == "₹38.4 L (approx)"
    assert version.deadline == "15.09.2026"
    assert tender.latest_deadline == "15.09.2026"


def test_backfill_leaves_no_orphan_job_when_tender_creation_fails(db, make_user, monkeypatch):
    user = make_user()
    bid = Bid(user_id=user.id, tender_name="Boom", tender_text="boom text",
              pipeline_result=json.dumps({"final": "### GO"}))
    db.add(bid)
    db.commit()
    bid_id = bid.id

    def boom_store(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(th, "_store", boom_store)

    created = th.backfill_from_bids()

    assert created == 0
    assert db.query(Tender).filter_by(bid_id=bid_id).first() is None
    assert db.query(AnalysisJob).filter_by(user_id=user.id).count() == 0

    monkeypatch.undo()  # restore the real _store

    created = th.backfill_from_bids()

    assert created == 1
    assert db.query(Tender).filter_by(bid_id=bid_id).first() is not None
