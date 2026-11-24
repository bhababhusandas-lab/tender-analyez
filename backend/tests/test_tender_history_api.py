# backend/tests/test_tender_history_api.py
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.core.db.models import AnalysisJob, AnalysisStep, Tender, TenderHistoryDocument, TenderVersion
from app.core import tender_history as th
from app.core.analysis_jobs import create_job, finish_job
from app.core.tender_inputs import UploadedDoc


async def _one_event(*_args, **_kwargs):
    yield 'data: {"type": "job_created"}\n\n'


def test_new_pipeline_analysis_creates_tender_and_announces_it(db, make_user, client_as):
    user = make_user()
    with (
        patch("app.api.v1.tender_analysis._ensure_pipeline_running"),
        patch("app.api.v1.tender_analysis.watch_pipeline_job", _one_event),
    ):
        response = client_as(user).post(
            "/api/v1/tender/analyze",
            data={"tender_text": "Tender Title: Supply of 500 office chairs\nEMD: Rs 20,000"},
            files=[("files", ("NIT.txt", b"Bid Submission Deadline: 15.10.2026", "text/plain"))],
        )
    assert response.status_code == 200
    tender = db.query(Tender).filter_by(user_id=user.id).one()
    assert tender.name == "Supply of 500 office chairs"
    assert f'"tender_id": {tender.id}' in response.text
    version = db.query(TenderVersion).filter_by(tender_id=tender.id).one()
    assert (version.kind, version.status, version.label) == ("pipeline", "running", "Original")
    assert version.analysis_job_id
    names = [d.original_filename for d in db.query(TenderHistoryDocument).filter_by(tender_id=tender.id)]
    assert names == ["Pasted tender text.txt", "NIT.txt"]


def test_new_roadmap_analysis_creates_tender(db, make_user, client_as):
    user = make_user()
    with (
        patch("app.api.v1.tender_roadmap._ensure_roadmap_running"),
        patch("app.api.v1.tender_roadmap.watch_roadmap_job", _one_event),
    ):
        response = client_as(user).post("/api/v1/tender/analyze-roadmap",
                                        data={"tender_text": "Tender Title: Road works PWD"})
    assert response.status_code == 200
    tender = db.query(Tender).filter_by(user_id=user.id).one()
    assert f'"tender_id": {tender.id}' in response.text
    assert db.query(TenderVersion).filter_by(tender_id=tender.id).one().kind == "roadmap"


def test_pipeline_analysis_still_streams_when_history_fails(db, make_user, client_as):
    user = make_user()
    with (
        patch("app.api.v1.tender_analysis._ensure_pipeline_running"),
        patch("app.api.v1.tender_analysis.watch_pipeline_job", _one_event),
        patch("app.core.tender_history.start_run", side_effect=OSError("disk full")),
    ):
        response = client_as(user).post("/api/v1/tender/analyze",
                                        data={"tender_text": "Tender Title: Supply of desks"})
    assert response.status_code == 200
    assert '"type": "job_created"' in response.text
    assert "tender_id" not in response.text
    assert db.query(Tender).filter_by(user_id=user.id).count() == 0


def test_roadmap_analysis_still_streams_when_history_fails(db, make_user, client_as):
    user = make_user()
    with (
        patch("app.api.v1.tender_roadmap._ensure_roadmap_running"),
        patch("app.api.v1.tender_roadmap.watch_roadmap_job", _one_event),
        patch("app.core.tender_history.start_run", side_effect=OSError("disk full")),
    ):
        response = client_as(user).post("/api/v1/tender/analyze-roadmap",
                                        data={"tender_text": "Tender Title: Road works PWD"})
    assert response.status_code == 200
    assert '"type": "job_created"' in response.text
    assert "tender_id" not in response.text
    assert db.query(Tender).filter_by(user_id=user.id).count() == 0


FINAL_V1 = "### **GO / NO-GO DECISION: CONDITIONAL GO**\n### **FINAL RECOMMENDED QUOTE**\n**NOT CALCULABLE FROM SUPPLIED EVIDENCE**"
FINAL_V2 = "### **GO / NO-GO DECISION: GO**\n### **FINAL RECOMMENDED QUOTE**\n**Rs 38,40,000**"


def _finished_tender(db, user, name="SRDS Health"):
    def run(tender, final, deadline):
        job = create_job(user.id, "pipeline", "t", {"canonical_facts": {"Bid Submission Deadline": {"value": deadline}}},
                         [{"id": "md-final", "name": "Final"}])
        tender, _ = th.start_run(db, user.id, tender=tender, kind="pipeline", job_id=job,
                                 docs=[UploadedDoc("Tender.pdf", "application/pdf", b"%PDF tender", "tender text")],
                                 pasted_text="", note="" if tender is None else "EMD waived", name_hint=name)
        finish_job(job, "completed", final_content=final)
        db.expire_all()
        return db.get(Tender, tender.id)
    tender = run(None, FINAL_V1, "30.09.2026")
    return run(tender, FINAL_V2, "07.10.2026")


def test_list_is_per_user_and_newest_first(db, make_user, client_as):
    alice, bob = make_user(), make_user()
    older = _finished_tender(db, alice, "Older tender")
    newer = _finished_tender(db, alice, "Newer tender")
    _finished_tender(db, bob, "Bob's tender")
    items = client_as(alice).get("/api/v1/tender-history").json()["items"]
    assert [i["name"] for i in items][:2] == ["Newer tender", "Older tender"]
    assert all(i["name"] != "Bob's tender" for i in items)
    assert items[0]["unread"] is True
    assert client_as(alice).get("/api/v1/tender-history", params={"q": "older"}).json()["items"][0]["id"] == older.id
    assert newer.id != older.id


def test_detail_shows_versions_changes_and_documents(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    body = client_as(user).get(f"/api/v1/tender-history/{tender.id}").json()
    assert [v["number"] for v in body["versions"]] == [2, 1]
    changes = {c["field"]: (c["before"], c["after"]) for c in body["versions"][0]["changes"]}
    assert changes["decision"] == ("CONDITIONAL GO", "GO")
    assert changes["deadline"] == ("30.09.2026", "07.10.2026")
    assert changes["quote"] == ("Not calculable", "Rs 38,40,000")
    assert body["versions"][0]["job_id"]
    assert [d["filename"] for d in body["documents"]] == ["Tender.pdf", "Tender.pdf"]


def test_viewed_clears_unread(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    client = client_as(user)
    assert client.post(f"/api/v1/tender-history/{tender.id}/viewed").status_code == 200
    item = next(i for i in client.get("/api/v1/tender-history").json()["items"] if i["id"] == tender.id)
    assert item["unread"] is False


def test_rename_download_export_and_delete(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    client = client_as(user)
    assert client.patch(f"/api/v1/tender-history/{tender.id}", json={"name": "Renamed"}).json()["name"] == "Renamed"
    doc_id = client.get(f"/api/v1/tender-history/{tender.id}").json()["documents"][0]["id"]
    download = client.get(f"/api/v1/tender-history/{tender.id}/documents/{doc_id}")
    assert download.status_code == 200 and download.content == b"%PDF tender"
    export = client.get(f"/api/v1/tender-history/{tender.id}/versions/2/export")
    assert export.status_code == 200 and export.headers["content-type"] == "application/pdf"
    assert client.delete(f"/api/v1/tender-history/{tender.id}").status_code == 200
    assert client.get(f"/api/v1/tender-history/{tender.id}").status_code == 404


def test_other_users_cannot_touch_a_tender(db, make_user, client_as):
    owner, other = make_user(), make_user()
    tender = _finished_tender(db, owner)
    client = client_as(other)
    assert client.get(f"/api/v1/tender-history/{tender.id}").status_code == 404
    assert client.patch(f"/api/v1/tender-history/{tender.id}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/v1/tender-history/{tender.id}").status_code == 404
    assert client.get(f"/api/v1/tender-history/{tender.id}/versions/1/export").status_code == 404
    assert client.get(f"/api/v1/tender-history/{tender.id}/documents/1").status_code == 404
    assert client.post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"}).status_code == 404


def test_delete_does_not_remove_blob_still_used_by_another_tender(db, make_user, client_as):
    """Two tenders whose documents hash to the same stored blob: deleting one
    must not take down the file the other still references."""
    user = make_user()
    tender_a = _finished_tender(db, user, "Tender A")
    tender_b = _finished_tender(db, user, "Tender B")
    client = client_as(user)
    doc_b_id = client.get(f"/api/v1/tender-history/{tender_b.id}").json()["documents"][0]["id"]

    assert client.delete(f"/api/v1/tender-history/{tender_a.id}").status_code == 200

    download = client.get(f"/api/v1/tender-history/{tender_b.id}/documents/{doc_b_id}")
    assert download.status_code == 200 and download.content == b"%PDF tender"


def test_deleted_blob_is_recreated_when_content_is_reused(db, make_user, client_as):
    """Once the last referencing tender is deleted the blob file is unlinked;
    a later run storing byte-identical content must recreate it, not skip the
    write because a stale row briefly made the file look shared."""
    user = make_user()
    tender_a = _finished_tender(db, user, "Tender A")
    client = client_as(user)
    assert client.delete(f"/api/v1/tender-history/{tender_a.id}").status_code == 200

    tender_c = _finished_tender(db, user, "Tender C")
    doc_c_id = client.get(f"/api/v1/tender-history/{tender_c.id}").json()["documents"][0]["id"]

    download = client.get(f"/api/v1/tender-history/{tender_c.id}/documents/{doc_c_id}")
    assert download.status_code == 200 and download.content == b"%PDF tender"


def test_reanalyse_starts_a_run_with_updates_first(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    captured = {}

    def fake_start(db_, user_, raw_text, *, evidence=None, **_kw):
        captured["text"], captured["evidence"] = raw_text, evidence
        return create_job(user_.id, "pipeline", raw_text, {}, [{"id": "md-final", "name": "Final"}])

    with patch("app.api.v1.tender_analysis.start_pipeline_job", fake_start):
        response = client_as(user).post(
            f"/api/v1/tender-history/{tender.id}/reanalyze",
            data={"kind": "pipeline", "note": "Pre-bid: EMD waived for MSEs"},
            files=[("files", ("Corrigendum-1.txt", b"Bid Submission Deadline: 14.10.2026", "text/plain"))],
        )
    assert response.status_code == 200, response.text
    assert response.json()["tender_id"] == tender.id
    assert captured["text"].index("=== UPDATE 2") < captured["text"].index("=== ORIGINAL TENDER DOCUMENTS ===")
    deadlines = [e.value for e in captured["evidence"] if e.field == "Bid Submission Deadline"]
    assert deadlines and all(v.startswith("14.10.2026") for v in deadlines)
    running = db.query(TenderVersion).filter_by(tender_id=tender.id, status="running").one()
    assert running.label == "Corrigendum-1.txt + note"


def test_reanalyse_rejects_empty_update_and_parallel_runs(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    client = client_as(user)
    assert client.post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": " "}).status_code == 400
    db.add(TenderVersion(tender_id=tender.id, kind="pipeline", status="running", label="x"))
    db.commit()
    assert client.post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"}).status_code == 409


def test_reanalyse_respects_plan_limit(db, make_user, client_as):
    user = make_user(plan="free")
    tender = _finished_tender(db, user)
    with patch("app.api.v1.tenders.check_usage", return_value=(False, {"message": "limit"})):
        response = client_as(user).post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert response.status_code == 402


def test_reanalyse_releases_reservation_on_plan_limit_rejection(db, make_user, client_as):
    user = make_user(plan="free")
    tender = _finished_tender(db, user)
    client = client_as(user)
    with patch("app.api.v1.tenders.check_usage", return_value=(False, {"message": "limit"})):
        rejected = client.post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert rejected.status_code == 402
    assert db.query(TenderVersion).filter_by(tender_id=tender.id, status="running").first() is None

    with (
        patch("app.api.v1.tender_analysis._ensure_pipeline_running"),
    ):
        allowed = client.post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert allowed.status_code == 200, allowed.text


def test_reanalyse_rejects_concurrent_request_without_recording_usage(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    db.add(TenderVersion(tender_id=tender.id, kind="pipeline", status="running", label="x"))
    db.commit()
    with patch("app.api.v1.tenders.record_usage") as mock_record_usage:
        response = client_as(user).post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert response.status_code == 409
    mock_record_usage.assert_not_called()


def test_reanalyse_keeps_the_reserved_version_when_start_run_fails_after_job_starts(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)

    def fake_start(*_args, **_kwargs):
        return create_job(user.id, "pipeline", "t", {}, [{"id": "md-final", "name": "Final"}])

    with (
        patch("app.api.v1.tender_analysis.start_pipeline_job", fake_start),
        patch("app.core.tender_history.start_run", side_effect=OSError("disk full")),
    ):
        response = client_as(user).post(
            f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    version = db.query(TenderVersion).filter_by(id=body["version_id"]).one()
    assert version.status == "running"
    assert version.analysis_job_id == body["job_id"]


def test_reanalyse_releases_reservation_when_pre_job_step_raises(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    client = client_as(user)
    with patch("app.api.v1.tenders.th.build_reanalysis_input", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            client.post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert db.query(TenderVersion).filter_by(tender_id=tender.id, status="running").first() is None

    with patch("app.api.v1.tender_analysis._ensure_pipeline_running"):
        response = client.post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert response.status_code == 200, response.text


def test_reanalyse_treats_a_stale_reservation_as_inactive(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    stale = TenderVersion(tender_id=tender.id, kind="pipeline", status="running", label="Preparing…",
                          created_at=datetime.utcnow() - timedelta(minutes=11))
    db.add(stale)
    db.commit()
    db.refresh(stale)

    with patch("app.api.v1.tender_analysis._ensure_pipeline_running"):
        response = client_as(user).post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert response.status_code == 200, response.text
    db.refresh(stale)
    assert stale.status == "failed"


def test_reanalyse_treats_a_stale_job_as_inactive(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    job_id = create_job(user.id, "pipeline", "t", {}, [{"id": "md-final", "name": "Final"}])
    db.add(TenderVersion(tender_id=tender.id, kind="pipeline", status="running", label="x", analysis_job_id=job_id))
    db.commit()
    job = db.query(AnalysisJob).filter_by(id=job_id).one()
    job.updated_at = datetime.utcnow() - timedelta(minutes=31)
    for step in db.query(AnalysisStep).filter_by(job_id=job_id):
        step.updated_at = datetime.utcnow() - timedelta(minutes=31)
    db.commit()

    with patch("app.api.v1.tender_analysis._ensure_pipeline_running"):
        response = client_as(user).post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert response.status_code == 200, response.text


def test_reanalyse_stays_blocked_when_a_step_updated_recently(db, make_user, client_as):
    """The job row's own updated_at doesn't advance while a job runs — only
    step rows change (via update_step) — so activity must be judged by the
    newest step update, not the job row alone."""
    user = make_user()
    tender = _finished_tender(db, user)
    job_id = create_job(user.id, "pipeline", "t", {}, [{"id": "md-final", "name": "Final"}])
    db.add(TenderVersion(tender_id=tender.id, kind="pipeline", status="running", label="x", analysis_job_id=job_id))
    db.commit()
    job = db.query(AnalysisJob).filter_by(id=job_id).one()
    job.updated_at = datetime.utcnow() - timedelta(minutes=40)
    steps = list(db.query(AnalysisStep).filter_by(job_id=job_id))
    steps[0].updated_at = datetime.utcnow() - timedelta(minutes=2)
    db.commit()

    response = client_as(user).post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert response.status_code == 409

    items = client_as(user).get("/api/v1/tender-history").json()["items"]
    item = next(i for i in items if i["id"] == tender.id)
    assert item["running"] is True


def test_reanalyse_still_blocks_on_a_fresh_active_run(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    job_id = create_job(user.id, "pipeline", "t", {}, [{"id": "md-final", "name": "Final"}])
    db.add(TenderVersion(tender_id=tender.id, kind="pipeline", status="running", label="x", analysis_job_id=job_id))
    db.commit()

    response = client_as(user).post(f"/api/v1/tender-history/{tender.id}/reanalyze", data={"kind": "pipeline", "note": "n"})
    assert response.status_code == 409


def test_list_item_running_is_false_for_a_stale_version(db, make_user, client_as):
    user = make_user()
    tender = _finished_tender(db, user)
    stale = TenderVersion(tender_id=tender.id, kind="pipeline", status="running", label="x",
                          created_at=datetime.utcnow() - timedelta(minutes=11))
    db.add(stale)
    db.commit()

    items = client_as(user).get("/api/v1/tender-history").json()["items"]
    item = next(i for i in items if i["id"] == tender.id)
    assert item["running"] is False
