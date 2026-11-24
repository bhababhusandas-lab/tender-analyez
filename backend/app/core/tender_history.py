"""Tender history: tenders, their versions (analysis runs) and documents.

A version wraps one analysis job. Documents keep the original bytes (compressed,
stored once per content hash) and their extracted text, so a later re-analysis
can re-read everything without the user uploading it again.
"""
import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.compression import decode_bytes, decode_json, decode_text, encode_bytes, encode_text, sha256_bytes
from app.core.db.models import AnalysisJob, AnalysisStep, Bid, DiscussionMessage, Tender, TenderHistoryDocument, TenderVersion
from app.core.db.session import SessionLocal
from app.core.tender_evidence import Evidence, extract_tender_evidence
from app.core.tender_inputs import UploadedDoc, source_block

UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent.parent.parent / "uploads")))
PASTED_NAME = "Pasted tender text.txt"

# Serialises blob reuse and deletion; sufficient for the single-process
# deployment. A multi-process deployment would need a file lock.
_BLOB_LOCK = threading.Lock()


# ── Names and labels ───────────────────────────────────────────────────────
def run_label(filenames: list[str], note: str) -> str:
    if not filenames:
        return "Note"
    label = filenames[0] if len(filenames) == 1 else f"{filenames[0]} + {len(filenames) - 1} more"
    return f"{label} + note" if note.strip() else label


def tender_name(evidence: list[Evidence], docs: list[UploadedDoc], fallback: str = "Untitled tender") -> str:
    for field in ("Tender Title", "Tender Reference / NIT Number"):
        value = next((item.value for item in evidence if item.field == field), "")
        if value:
            return value[:300]
    if docs:
        return docs[0].filename[:300]
    return fallback


# ── Files ──────────────────────────────────────────────────────────────────
def _store(tender_id: int, version_id: int, filename: str, mime: str, raw: bytes, text: str) -> TenderHistoryDocument:
    checksum = sha256_bytes(raw)
    encoded = encode_bytes(raw, content_type=mime, filename=filename)
    # The encoding is part of the stored name: whether a given upload gets
    # compressed depends on its mime/filename, so a blob written earlier for
    # the same bytes under a different mime/filename could carry the other
    # encoding. Keying by (checksum, encoding) keeps every row's `compression`
    # column matching the file it actually points to.
    stored = f"tenders/{checksum}.{encoded.encoding}.blob"
    path = UPLOAD_ROOT / stored
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(encoded.data)
        temporary.replace(path)
    return TenderHistoryDocument(
        tender_id=tender_id, version_id=version_id, original_filename=filename, mime_type=mime,
        file_size=len(raw), stored_filename=stored, sha256=checksum,
        compression=encoded.encoding, extracted_text=encode_text(text),
    )


def read_document_bytes(doc: TenderHistoryDocument) -> bytes:
    return decode_bytes((UPLOAD_ROOT / doc.stored_filename).read_bytes(), doc.compression)


def documents_for(db: Session, tender_id: int) -> list[TenderHistoryDocument]:
    return db.query(TenderHistoryDocument).filter_by(tender_id=tender_id).order_by(TenderHistoryDocument.id).all()


# ── Runs ───────────────────────────────────────────────────────────────────
# Background analyses don't survive a server restart, so a "running" version
# left behind by a crashed/restarted process must not block new work forever.
RESERVATION_ACTIVE_WINDOW = timedelta(minutes=10)  # reservation in progress, no job id yet
JOB_ACTIVE_WINDOW = timedelta(minutes=30)  # job assigned; still counts as active if updated this recently


def is_active_run(db: Session, version: TenderVersion) -> bool:
    """Whether a status="running" version represents work actually in flight.

    True only if either: it's a very fresh reservation with no job id yet
    (`reserve_run` was just called and `start_run`/the job start is still in
    progress), or its AnalysisJob is still "running"/"pending" and has had
    activity within the active window. Anything else — a job that finished
    without the finish hook running, or one abandoned by a server restart —
    is stale and must not block a new re-analysis.

    Activity is the newer of the job row's own `updated_at` and the newest
    `AnalysisStep.updated_at` for that job: `job.updated_at` does not advance
    while the job runs (only `update_step` touches step rows), so using the
    job row alone would misjudge a healthy long-running analysis as stale.
    """
    now = datetime.utcnow()
    if version.analysis_job_id is None:
        return version.created_at is not None and (now - version.created_at) <= RESERVATION_ACTIVE_WINDOW
    job = db.get(AnalysisJob, version.analysis_job_id)
    if job is None:
        return False
    if job.status not in ("running", "pending"):
        return False
    latest_step = db.query(func.max(AnalysisStep.updated_at)).filter(AnalysisStep.job_id == job.id).scalar()
    last_activity = max(job.updated_at, latest_step) if latest_step is not None else job.updated_at
    return (now - last_activity) <= JOB_ACTIVE_WINDOW


def reserve_run(db: Session, tender: Tender, kind: str, note: str) -> TenderVersion:
    """Create and commit a placeholder "running" version before any slow work.

    Used by re-analysis so the 409 "already running" check is enforced the
    instant the request is accepted, with nothing awaited in between — two
    concurrent re-analyse requests can't both pass the check and both start a
    job. Pass the returned version to `start_run` to fill it in once the job
    id and documents are known; delete it (and commit) if a later validation
    step rejects the request, so a retry isn't blocked by its own 409.
    """
    version = TenderVersion(tender_id=tender.id, kind=kind, status="running",
                            label="Preparing…", note=note.strip())
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def start_run(db: Session, user_id: int, *, tender: Tender | None, kind: str, job_id: str | None,
              docs: list[UploadedDoc], pasted_text: str, note: str, name_hint: str,
              version: TenderVersion | None = None) -> tuple[Tender, TenderVersion]:
    """Create (or reuse) a tender, add (or fill in) a running version and store its documents.

    Pass `version` (from `reserve_run`) to fill in an already-reserved version
    instead of creating a new one.
    """
    if tender is None:
        tender = Tender(user_id=user_id, name=(name_hint or "Untitled tender")[:300])
        db.add(tender)
        db.flush()
        label = "Original"
    else:
        label = run_label([d.filename for d in docs], note)
    if version is None:
        version = TenderVersion(tender_id=tender.id, kind=kind, status="running", label=label,
                                note=note.strip(), analysis_job_id=job_id)
        db.add(version)
    else:
        version.analysis_job_id = job_id
        version.label = label
        version.note = note.strip()
    db.flush()
    with _BLOB_LOCK:
        if pasted_text.strip():
            raw = pasted_text.strip().encode()
            db.add(_store(tender.id, version.id, PASTED_NAME, "text/plain", raw, pasted_text.strip()))
        for doc in docs:
            db.add(_store(tender.id, version.id, doc.filename, doc.mime_type, doc.raw, doc.text))
        tender.last_activity_at = datetime.utcnow()
        db.commit()
    db.refresh(tender)
    db.refresh(version)
    return tender, version


# ── Re-analysis input ──────────────────────────────────────────────────────
CHAT_CHAR_LIMIT = 4000


def _earlier_user_chat(db: Session, tender: Tender, *, exclude_version_id: int | None = None) -> str:
    """The user's own chat messages across this tender's earlier runs, oldest
    first, capped at CHAT_CHAR_LIMIT keeping the most recent text.

    Only role == "user" messages are included: MD/assistant answers are AI
    output and could carry mistakes forward as facts if re-fed as input. This
    text is not run through evidence extraction — chat can contain
    hypotheticals ("what if the deadline were 10.10?") that aren't facts.
    """
    job_ids = [v.analysis_job_id for v in
               db.query(TenderVersion).filter(TenderVersion.tender_id == tender.id, TenderVersion.id != exclude_version_id)
               if v.analysis_job_id]
    if not job_ids:
        return ""
    rows = (db.query(DiscussionMessage)
            .filter(DiscussionMessage.job_id.in_(job_ids), DiscussionMessage.role == "user")
            .order_by(DiscussionMessage.id).all())
    # One line per message, so chat text can never forge a "=== …" section or
    # "--- SOURCE DOCUMENT" marker inside the AI input.
    lines = []
    for r in rows:
        flat = " ".join(decode_text(r.content).split())
        if flat:
            lines.append(f"- {flat}")
    text = "\n".join(lines)
    return text[-CHAT_CHAR_LIMIT:] if len(text) > CHAT_CHAR_LIMIT else text


def _doc_block(doc: TenderHistoryDocument) -> str:
    return f"--- SOURCE DOCUMENT: {doc.original_filename} ---\n{decode_text(doc.extracted_text)}"


def build_reanalysis_input(db: Session, tender: Tender, *, new_docs: list[UploadedDoc], note: str,
                           today: datetime | None = None,
                           exclude_version_id: int | None = None) -> tuple[str, list[list[Evidence]]]:
    """Return (AI input text, evidence layers newest-first).

    Order: this update → the user's note → earlier updates (newest first) →
    original documents. Updates come first so they survive if the input is
    longer than the model's context window: the job builders pass this text
    through `tender_condense.build_model_input`, which always keeps the
    UPDATE / user-statement sections and condenses the documents after them.

    Every earlier version is included regardless of status: if the original
    run (v1) failed or was stopped before it could be numbered, its documents
    must still make it into the re-analysis input rather than silently
    disappearing.

    `exclude_version_id` leaves out a placeholder version reserved (via
    `reserve_run`) for the run currently being built, so it doesn't count
    itself as an earlier update or bump the update number.
    """
    today = today or datetime.utcnow()
    all_versions = (db.query(TenderVersion)
                    .filter(TenderVersion.tender_id == tender.id, TenderVersion.id != exclude_version_id)
                    .order_by(TenderVersion.id.desc()).all())
    docs_by_version: dict[int, list[TenderHistoryDocument]] = {}
    for doc in documents_for(db, tender.id):
        docs_by_version.setdefault(doc.version_id, []).append(doc)

    update_no = len(all_versions)  # count of existing versions, so a failed v1 still gives UPDATE 1
    sections: list[str] = []
    layers: list[list[Evidence]] = []

    new_text = "\n\n".join(source_block(d) for d in new_docs)
    note_text = f"--- SOURCE DOCUMENT: Update note from the user ---\n{note.strip()}" if note.strip() else ""
    if new_text:
        sections.append(f"=== UPDATE {update_no} (added {today:%d %b %Y}): "
                        f"{', '.join(d.filename for d in new_docs)} — overrides earlier documents where they conflict ===\n{new_text}")
    if note_text:
        sections.append(f"=== UPDATE FROM THE USER (not from the tender) ===\n{note_text}")
    layers.append(extract_tender_evidence("\n\n".join(filter(None, [new_text, note_text]))))

    chat = _earlier_user_chat(db, tender, exclude_version_id=exclude_version_id)
    if chat:
        sections.append("=== EARLIER DISCUSSION — STATEMENTS FROM THE USER (not from the tender) ===\n" + chat)

    earliest_id = min((version.id for version in all_versions), default=None)
    for version in all_versions:
        body = "\n\n".join(_doc_block(d) for d in docs_by_version.get(version.id, []))
        if version.id == earliest_id:
            header = "=== ORIGINAL TENDER DOCUMENTS ==="
        else:
            if version.number is not None:
                header = f"=== EARLIER UPDATE (version {version.number}, {version.created_at:%d %b %Y}) ==="
            else:
                header = f"=== EARLIER UPDATE ({version.created_at:%d %b %Y}) ==="
            if version.note:
                body = "\n\n".join(filter(None, [body, f"--- SOURCE DOCUMENT: Earlier note from the user ---\n{version.note}"]))
        if body:
            sections.append(f"{header}\n{body}")
            layers.append(extract_tender_evidence(body))
    return "\n\n".join(sections), layers


# ── Finish hook ────────────────────────────────────────────────────────────
_FINISHED = {"completed", "review_required"}
_DECISION_RE = re.compile(r"\b(NO[- ]BID|NO[- ]GO|CONDITIONAL (?:GO|BID)|GO|BID)\b", re.I)


def summarize_result(final: str, canonical_facts: dict) -> dict:
    """Decision, quote and deadline for the history list and "what changed"."""
    from app.api.v1.export import find_section  # local import: export imports fpdf lazily

    decision = ""
    section = find_section(final, r"GO\s*/\s*NO.?GO|DECISION")
    # The heading itself contains "GO / NO-GO", so read the value after its colon first.
    heading_value = section[0].split(":", 1)[1] if section and ":" in section[0] else ""
    for candidate in [heading_value, section[1] if section else "", final]:
        match = _DECISION_RE.search(candidate or "")
        if match:
            decision = match.group(1).upper()
            if decision.startswith("NO"):
                decision = decision.replace(" ", "-")  # "NO BID" -> "NO-BID"
            break
    quote = ""
    quote_section = find_section(final, r"RECOMMENDED QUOTE")
    if quote_section:
        first = next((line.strip() for line in quote_section[1].split("\n") if line.strip()), "")
        quote = "Not calculable" if "NOT CALCULABLE" in first.upper() else first.replace("*", "").strip()[:120]
    deadline = str((canonical_facts.get("Bid Submission Deadline") or {}).get("value", ""))[:160]
    return {"decision": decision, "quote": quote, "deadline": deadline}


def _job_results(db: Session, job_id: str) -> dict[str, str]:
    steps = db.query(AnalysisStep).filter_by(job_id=job_id).all()
    return {s.step_id: decode_text(s.content) for s in steps if s.step_id != "md-final" and s.content}


def _assign_version_number(db: Session, version: TenderVersion, tender: Tender) -> tuple[TenderVersion, Tender]:
    """Assign the next version number for this tender.

    Uses max(existing numbers) + 1 rather than tender.version_count + 1, since
    version_count can go stale (e.g. a numbered version created outside this
    path). Retries past a concurrent numbering race (two runs finishing for
    the same tender at once) via the UniqueConstraint on (tender_id, number).
    """
    for _attempt in range(3):
        next_number = (db.query(func.max(TenderVersion.number))
                       .filter(TenderVersion.tender_id == tender.id).scalar() or 0) + 1
        version.number = next_number
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            version = db.get(TenderVersion, version.id)
            tender = db.get(Tender, tender.id)
            continue
        tender.version_count = next_number
        return version, tender
    raise RuntimeError(f"could not assign a version number for tender {tender.id} after 3 attempts")


def on_job_status(job_id: str, status: str) -> None:
    """Called by finish_job/cancel_job. Safe to call for jobs with no tender."""
    with SessionLocal() as db:
        version = db.query(TenderVersion).filter_by(analysis_job_id=job_id).first()
        if version is None or status in {"running", "pending"}:
            return
        tender = db.get(Tender, version.tender_id)
        if version.number is not None and status not in _FINISHED:
            # A later "cancelled"/"partial"/other non-finished status (e.g. a
            # failed md-final retry) must never downgrade an already-numbered,
            # already-finished version.
            return
        if status == "cancelled":
            version.status = "stopped"
        elif status not in _FINISHED:
            version.status = "failed"
        else:
            job = db.get(AnalysisJob, job_id)
            final = decode_text(job.final_content) if job else ""
            context = decode_json(job.context_json, {}) if job else {}
            summary = summarize_result(final, context.get("canonical_facts", {}))
            if version.number is None:
                version, tender = _assign_version_number(db, version, tender)
            version.status = status
            version.completed_at = datetime.utcnow()
            version.decision, version.quote, version.deadline = summary["decision"], summary["quote"], summary["deadline"]
            if summary["decision"]:
                tender.latest_decision = summary["decision"]
            if summary["quote"]:
                tender.latest_quote = summary["quote"]
            if summary["deadline"]:
                tender.latest_deadline = summary["deadline"]
            if tender.bid_id:
                bid = db.get(Bid, tender.bid_id)
                if bid is not None:
                    results = _job_results(db, job_id)
                    results["final"] = final
                    bid.pipeline_result = json.dumps(results)
                    if summary["quote"] and summary["quote"] != "Not calculable":
                        bid.recommended_quote = summary["quote"]
                    if summary["deadline"]:
                        bid.submission_deadline = summary["deadline"]
        tender.last_activity_at = datetime.utcnow()
        db.commit()


def _discard_orphan_job(job_id: str | None) -> None:
    """Best-effort cleanup of an AnalysisJob (and its steps) left behind by a
    backfill attempt that failed before the tender/version were created."""
    if job_id is None:
        return
    try:
        with SessionLocal() as db:
            db.query(AnalysisStep).filter_by(job_id=job_id).delete()
            db.query(AnalysisJob).filter_by(id=job_id).delete()
            db.commit()
    except Exception as exc:
        print(f"[history] failed to discard orphan job {job_id}: {exc}")


def backfill_from_bids() -> int:
    """Give every analysed Bid Tracker entry a tender with version 1. Idempotent.

    Never modifies the source Bid: the job is created and finished *before*
    any TenderVersion links to it, so `on_job_status` (called by `finish_job`)
    finds no version to act on and is a no-op — the tender/version/document
    are created afterwards, in a single commit, with quote/deadline copied
    verbatim from the bid rather than re-derived. One bad bid can never stop
    the others; a bid whose `pipeline_result` fails to parse into a non-empty
    dict is skipped, and any other failure is logged and leaves no orphan
    AnalysisJob behind.
    """
    from app.core.analysis_jobs import create_job, finish_job, update_step

    created = 0
    with SessionLocal() as db:
        linked = {row[0] for row in db.query(Tender.bid_id).filter(Tender.bid_id.isnot(None))}
        bids = db.query(Bid).filter(Bid.pipeline_result.notin_(["", "{}"])).all()
        pending = [b for b in bids if b.id not in linked and b.user_id is not None]
    for bid in pending:
        job_id = None
        try:
            try:
                results = json.loads(bid.pipeline_result or "{}")
            except ValueError:
                continue
            if not isinstance(results, dict) or not results:
                continue
            results = {str(key): str(value) for key, value in results.items()}
            final = results.pop("final", "")
            steps = ([{"id": key, "name": key} for key in results]
                    + [{"id": "md-final", "name": "Final Decision Briefing"}])
            job_id = create_job(bid.user_id, "pipeline", bid.tender_text or "", {}, steps)
            for key, content in results.items():
                update_step(job_id, key, "done", content=content)
            update_step(job_id, "md-final", "done", content=final)
            finish_job(job_id, "completed", final_content=final)  # no TenderVersion yet: on_job_status is a no-op

            decision = summarize_result(final, {})["decision"]
            quote = bid.recommended_quote or ""
            deadline = bid.submission_deadline or ""
            with SessionLocal() as db:
                with _BLOB_LOCK:
                    tender = Tender(user_id=bid.user_id, name=bid.tender_name[:300], reference_no=bid.reference_no or "",
                                    bid_id=bid.id, version_count=1, latest_decision=decision,
                                    latest_quote=quote, latest_deadline=deadline)
                    db.add(tender)
                    db.flush()
                    version = TenderVersion(tender_id=tender.id, number=1, kind="pipeline", status="completed",
                                            completed_at=datetime.utcnow(), label="Original (from Bid Tracker)",
                                            analysis_job_id=job_id, decision=decision, quote=quote, deadline=deadline)
                    db.add(version)
                    db.flush()
                    if bid.tender_text:
                        raw = bid.tender_text.encode()
                        db.add(_store(tender.id, version.id, "Tender text (from Bid Tracker).txt", "text/plain", raw, bid.tender_text))
                    db.commit()
            created += 1
        except Exception as exc:
            print(f"[history] backfill skipped bid {bid.id}: {exc}")
            _discard_orphan_job(job_id)
    return created


def delete_tender(db: Session, tender: Tender) -> None:
    """Delete a tender, its versions and documents; remove files nothing else uses."""
    docs = documents_for(db, tender.id)
    stored = {d.stored_filename for d in docs}
    for doc in docs:
        db.delete(doc)
    db.query(TenderVersion).filter_by(tender_id=tender.id).delete()
    db.delete(tender)
    db.commit()
    with _BLOB_LOCK:
        for name in stored:
            if db.query(TenderHistoryDocument).filter_by(stored_filename=name).first() is None:
                (UPLOAD_ROOT / name).unlink(missing_ok=True)
