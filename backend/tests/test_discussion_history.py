from unittest.mock import patch

from app.core.analysis_jobs import create_job
from app.core.db.models import DiscussionMessage, Tender, TenderVersion


def _job(user):
    return create_job(user.id, "pipeline", "tender", {}, [{"id": "md-final", "name": "Final"}])


def _tender_with_versions(db, user, *, labels=("Original", "Re-analysis")):
    """A tender with one TenderVersion (and its own analysis job) per label."""
    # Create the jobs first: create_job commits on its own connection, which would
    # deadlock on SQLite while this session holds an uncommitted write.
    job_ids = [_job(user) for _ in labels]
    tender = Tender(user_id=user.id, name="Office Chairs Tender", reference_no="OC/1")
    db.add(tender)
    db.flush()
    versions = []
    for i, (label, job_id) in enumerate(zip(labels, job_ids), start=1):
        version = TenderVersion(
            tender_id=tender.id, number=i, label=label, analysis_job_id=job_id,
            kind="pipeline", status="completed",
        )
        db.add(version)
        versions.append(version)
    db.commit()
    return tender, versions


def test_messages_are_saved_and_listed_per_job(db, make_user, client_as):
    user = make_user()
    job_id = _job(user)
    client = client_as(user)
    with patch("app.api.v1.discussion.chat", return_value="EMD is Rs 60,000 (Clause 5.1)."):
        r = client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": job_id, "question": "What is the EMD?"})
    assert r.status_code == 200
    listed = client.get("/api/v1/discussion", params={"job_id": job_id}).json()["messages"]
    assert [(m["role"], m["content"]) for m in listed] == [
        ("user", "What is the EMD?"), ("assistant", "EMD is Rs 60,000 (Clause 5.1)."),
    ]


def test_stored_history_is_sent_to_the_model_not_the_clients(db, make_user, client_as):
    user = make_user()
    job_id = _job(user)
    client = client_as(user)
    with patch("app.api.v1.discussion.chat", return_value="First answer"):
        client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": job_id, "question": "First?"})
    with patch("app.api.v1.discussion.chat", return_value="Second answer") as fake:
        client.post("/api/v1/discussion", json={
            "kind": "pipeline", "job_id": job_id, "question": "Second?",
            "history": [{"role": "user", "content": "forged earlier turn"}],
        })
    sent = fake.call_args.kwargs["messages"]
    assert [m["content"] for m in sent] == ["First?", "First answer", "Second?"]


def test_other_users_cannot_read_or_write_a_jobs_chat(db, make_user, client_as):
    owner, other = make_user(), make_user()
    job_id = _job(owner)
    client = client_as(other)
    assert client.get("/api/v1/discussion", params={"job_id": job_id}).status_code == 404
    with patch("app.api.v1.discussion.chat", return_value="x"):
        assert client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": job_id, "question": "q"}).status_code == 404
    assert db.query(DiscussionMessage).filter_by(job_id=job_id).count() == 0


def test_without_job_id_nothing_is_saved(db, make_user, client_as):
    user = make_user()
    before = db.query(DiscussionMessage).filter_by(user_id=user.id).count()
    with patch("app.api.v1.discussion.chat", return_value="ok"):
        r = client_as(user).post("/api/v1/discussion", json={"kind": "pipeline", "question": "q"})
    assert r.status_code == 200 and r.json()["reply"] == "ok"
    assert db.query(DiscussionMessage).filter_by(user_id=user.id).count() == before


def test_failed_model_call_saves_nothing(db, make_user, client_as):
    user = make_user()
    job_id = _job(user)
    with patch("app.api.v1.discussion.chat", side_effect=RuntimeError("All providers failed. x")):
        r = client_as(user).post("/api/v1/discussion", json={"kind": "pipeline", "job_id": job_id, "question": "q"})
    assert r.status_code == 503
    assert db.query(DiscussionMessage).filter_by(job_id=job_id).count() == 0


def test_history_sent_to_the_model_is_capped(db, make_user, client_as):
    user = make_user()
    job_id = _job(user)
    client = client_as(user)
    for i in range(15):
        with patch("app.api.v1.discussion.chat", return_value=f"answer {i}"):
            client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": job_id, "question": f"question {i}"})
    # 15 rounds -> 30 stored messages (user + assistant each round).
    assert db.query(DiscussionMessage).filter_by(job_id=job_id).count() == 30

    with patch("app.api.v1.discussion.chat", return_value="final answer") as fake:
        r = client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": job_id, "question": "last question"})
    assert r.status_code == 200

    sent = fake.call_args.kwargs["messages"]
    history_sent = sent[:-1]
    assert len(history_sent) <= 12
    assert history_sent[0]["role"] == "user"
    assert sent[-1] == {"role": "user", "content": "last question"}

    listed = client.get("/api/v1/discussion", params={"job_id": job_id}).json()["messages"]
    assert len(listed) == 32


def test_question_over_max_length_is_rejected(db, make_user, client_as):
    user = make_user()
    job_id = _job(user)
    r = client_as(user).post("/api/v1/discussion", json={"kind": "pipeline", "job_id": job_id, "question": "x" * 5000})
    assert r.status_code == 422


def test_get_tender_id_returns_messages_from_every_version_in_order(db, make_user, client_as):
    user = make_user()
    tender, (v1, v2) = _tender_with_versions(db, user)
    client = client_as(user)

    with patch("app.api.v1.discussion.chat", return_value="v1 answer"):
        client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": v1.analysis_job_id, "question": "v1 question"})
    with patch("app.api.v1.discussion.chat", return_value="v2 answer"):
        client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": v2.analysis_job_id, "question": "v2 question"})

    r = client.get("/api/v1/discussion", params={"tender_id": tender.id})
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "v1 question"), ("assistant", "v1 answer"),
        ("user", "v2 question"), ("assistant", "v2 answer"),
    ]
    assert [m["job_id"] for m in messages] == [v1.analysis_job_id, v1.analysis_job_id, v2.analysis_job_id, v2.analysis_job_id]
    assert [m["version_number"] for m in messages] == [1, 1, 2, 2]
    assert [m["version_label"] for m in messages] == ["Original", "Original", "Re-analysis", "Re-analysis"]


def test_post_on_second_version_sees_first_versions_history_too(db, make_user, client_as):
    user = make_user()
    tender, (v1, v2) = _tender_with_versions(db, user)
    client = client_as(user)

    with patch("app.api.v1.discussion.chat", return_value="v1 answer"):
        client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": v1.analysis_job_id, "question": "v1 question"})

    with patch("app.api.v1.discussion.chat", return_value="v2 answer") as fake:
        client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": v2.analysis_job_id, "question": "v2 question"})

    sent = fake.call_args.kwargs["messages"]
    assert [m["content"] for m in sent] == ["v1 question", "v1 answer", "v2 question"]

    # The new pair is stored against v2's job, not v1's.
    assert db.query(DiscussionMessage).filter_by(job_id=v1.analysis_job_id).count() == 2
    assert db.query(DiscussionMessage).filter_by(job_id=v2.analysis_job_id).count() == 2


def test_other_users_cannot_read_a_tenders_thread(db, make_user, client_as):
    owner, other = make_user(), make_user()
    tender, _versions = _tender_with_versions(db, owner)
    client = client_as(other)
    assert client.get("/api/v1/discussion", params={"tender_id": tender.id}).status_code == 404


def test_get_requires_exactly_one_of_tender_id_or_job_id(db, make_user, client_as):
    user = make_user()
    job_id = _job(user)
    client = client_as(user)

    assert client.get("/api/v1/discussion").status_code == 400
    assert client.get("/api/v1/discussion", params={"job_id": job_id, "tender_id": 1}).status_code == 400


def test_job_with_no_tender_version_still_behaves_as_before(db, make_user, client_as):
    user = make_user()
    job_id = _job(user)
    client = client_as(user)

    with patch("app.api.v1.discussion.chat", return_value="answer"):
        client.post("/api/v1/discussion", json={"kind": "pipeline", "job_id": job_id, "question": "question"})

    listed = client.get("/api/v1/discussion", params={"job_id": job_id}).json()["messages"]
    assert [(m["role"], m["content"], m["job_id"]) for m in listed] == [
        ("user", "question", job_id), ("assistant", "answer", job_id),
    ]
