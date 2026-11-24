import json

from app.core import tender_history as th
from app.core.analysis_jobs import cancel_job, create_job, finish_job, update_step
from app.core.db.models import Bid, Tender, TenderVersion

FINAL = """### **FINAL RECOMMENDED QUOTE**
**Rs 38,40,000**
### **GO / NO-GO DECISION: CONDITIONAL GO ⚠️**
**Decision**: Close two gaps first.
"""


def _run(db, user, tender=None):
    job_id = create_job(user.id, "pipeline", "tender text",
                        {"canonical_facts": {"Bid Submission Deadline": {"value": "07.10.2026 17:00"}}},
                        [{"id": "bid-manager", "name": "Bid Manager"}, {"id": "md-final", "name": "Final"}])
    tender, version = th.start_run(db, user.id, tender=tender, kind="pipeline", job_id=job_id,
                                   docs=[], pasted_text="text", note="", name_hint="SRDS")
    return job_id, tender, version


def test_completed_job_numbers_version_and_updates_tender(db, make_user):
    user = make_user()
    job_id, tender, version = _run(db, user)
    update_step(job_id, "bid-manager", "done", content="## Decision\n**CONDITIONAL BID**")
    finish_job(job_id, "completed", final_content=FINAL)

    db.expire_all()
    version = db.get(TenderVersion, version.id)
    tender = db.get(Tender, tender.id)
    assert (version.number, version.status) == (1, "completed")
    assert version.decision == "CONDITIONAL GO"
    assert version.quote == "Rs 38,40,000"
    assert version.deadline == "07.10.2026 17:00"
    assert (tender.version_count, tender.latest_decision) == (1, "CONDITIONAL GO")


def test_second_run_becomes_version_two(db, make_user):
    user = make_user()
    job1, tender, _ = _run(db, user)
    finish_job(job1, "completed", final_content=FINAL)
    db.expire_all()
    job2, tender, v2 = _run(db, user, tender=db.get(Tender, tender.id))
    finish_job(job2, "review_required", final_content=FINAL)
    db.expire_all()
    assert db.get(TenderVersion, v2.id).number == 2
    assert db.get(Tender, tender.id).version_count == 2


def test_stopped_and_failed_runs_get_no_number(db, make_user):
    user = make_user()
    job1, _, v1 = _run(db, user)
    cancel_job(job1, user.id, "pipeline")
    job2, _, v2 = _run(db, user)
    finish_job(job2, "partial", error="2 specialist(s) require retry")
    db.expire_all()
    assert (db.get(TenderVersion, v1.id).status, db.get(TenderVersion, v1.id).number) == ("stopped", None)
    assert (db.get(TenderVersion, v2.id).status, db.get(TenderVersion, v2.id).number) == ("failed", None)


def test_running_status_does_not_touch_the_version(db, make_user):
    user = make_user()
    job_id, _, version = _run(db, user)
    finish_job(job_id, "running")
    db.expire_all()
    assert db.get(TenderVersion, version.id).status == "running"


def test_linked_bid_gets_new_results_but_keeps_status(db, make_user):
    user = make_user()
    bid = Bid(user_id=user.id, tender_name="SRDS", status="submitted", pipeline_result="{}")
    db.add(bid)
    db.commit()
    job_id, tender, _ = _run(db, user)
    tender.bid_id = bid.id
    db.commit()
    update_step(job_id, "bid-manager", "done", content="manager output")
    finish_job(job_id, "completed", final_content=FINAL)
    db.expire_all()
    bid = db.get(Bid, bid.id)
    assert bid.status == "submitted"
    assert json.loads(bid.pipeline_result)["bid-manager"] == "manager output"
    assert json.loads(bid.pipeline_result)["final"] == FINAL
    assert bid.recommended_quote == "Rs 38,40,000"
    assert bid.submission_deadline == "07.10.2026 17:00"


def test_finished_version_is_not_downgraded_by_later_status(db, make_user):
    user = make_user()
    job_id, tender, version = _run(db, user)
    finish_job(job_id, "completed", final_content=FINAL)
    db.expire_all()
    finish_job(job_id, "partial", error="md-final retry failed")
    db.expire_all()
    v = db.get(TenderVersion, version.id)
    assert (v.number, v.status, v.decision) == (1, "completed", "CONDITIONAL GO")


def test_finish_job_survives_history_hook_failure(db, make_user, monkeypatch):
    user = make_user()
    job_id, tender, version = _run(db, user)

    def boom(job_id, status):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.core.tender_history.on_job_status", boom)
    finish_job(job_id, "completed", final_content=FINAL)

    from app.core.analysis_jobs import get_job_payload
    payload = get_job_payload(job_id, user.id)
    assert payload["status"] == "completed"


def test_cancel_job_survives_history_hook_failure(db, make_user, monkeypatch):
    user = make_user()
    job_id, tender, version = _run(db, user)

    def boom(job_id, status):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.core.tender_history.on_job_status", boom)
    assert cancel_job(job_id, user.id, "pipeline") is True


def test_numbering_uses_max_existing_not_stale_version_count(db, make_user):
    user = make_user()
    job1, tender, v1 = _run(db, user)
    finish_job(job1, "completed", final_content=FINAL)
    db.expire_all()
    tender = db.get(Tender, tender.id)
    tender.version_count = 0  # simulate a stale counter
    db.commit()

    job2, tender, v2 = _run(db, user, tender=db.get(Tender, tender.id))
    finish_job(job2, "completed", final_content=FINAL)
    db.expire_all()
    assert db.get(TenderVersion, v2.id).number == 2
    assert db.get(Tender, tender.id).version_count == 2


def test_latest_decision_and_quote_not_cleared_by_empty_values(db, make_user):
    user = make_user()
    job1, tender, v1 = _run(db, user)
    finish_job(job1, "completed", final_content=FINAL)
    db.expire_all()

    job2, tender, v2 = _run(db, user, tender=db.get(Tender, tender.id))
    finish_job(job2, "completed", final_content="Nothing decisive here.")
    db.expire_all()
    tender = db.get(Tender, tender.id)
    assert tender.latest_decision == "CONDITIONAL GO"
    assert tender.latest_quote == "Rs 38,40,000"
