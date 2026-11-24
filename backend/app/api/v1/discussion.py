"""Post-analysis discussion endpoint.

After Bid Pipeline or Analysis completes, the user can ask follow-up questions.
The AI MD has access to the full tender + all agent/phase outputs as context.
Discussion messages do NOT count toward usage limits — they're free follow-up.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import AnalysisJob, DiscussionMessage, Tender, TenderVersion, User
from app.core.security.auth import get_current_user
from app.core.compression import decode_text, encode_text
from app.core.llm.claude_client import chat, user_facing_error
from app.api.v1.company import get_profile_context

router = APIRouter()


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class DiscussionIn(BaseModel):
    kind: str = Field(default="pipeline")           # "pipeline" or "roadmap"
    tender_text: str = ""                            # the original tender
    analysis_results: dict[str, str] = {}            # agent_id -> content (pipeline) or phase_id -> content (roadmap)
    final_briefing: str = ""                         # the MD final output
    history: list[Message] = []                      # prior chat messages this discussion thread
    question: str = Field(min_length=1, max_length=4000)  # the new user question
    job_id: str | None = None                         # analysis job to persist/read this thread against


SYSTEM_PROMPT_TEMPLATE = """You are the Managing Director of an AI bid team at Unique Type. The team has just completed a {kind_name} for a government tender. The user is now asking follow-up questions to clarify, debate, or refine the recommendations.

You have full access to:
- The original tender document
- Every team member's output from the {kind_name}
- The final MD briefing (quote, confidence, decision, action items)
- The user's company profile

Answer the user's question concisely, decisively, and grounded in the actual findings of the analysis. If the user pushes back on a number or recommendation, take their input seriously and update your reasoning — show your math. If you don't have enough information from the original analysis, say so honestly. Speak like an experienced MD running a bid review, not like a generic assistant.

When the user asks for a different quote, an alternative strategy, or a re-evaluation, be concrete: give updated numbers, updated reasoning, and updated next steps. Reference specific phases or agent outputs by name when relevant ("Phase 3 Build estimated...", "The Legal review flagged...").

If the question is unrelated to the tender or analysis, gently steer back to the bid at hand.

FACTS: Use only figures, clauses, dates and names that appear in the context below. Never invent an example value ("e.g. ₹12.5 crore"). If a figure is not in the context, write "not stated in the tender" and say which document the bidder should check.

FORMAT — this is a chat reply read by a busy bid manager:
- Open with a one or two sentence direct answer. No preamble, no restating the question.
- Then at most 3 short sections, each introduced by a bold label on its own line (e.g. **What it means**, **What to do now**). Do not use # headings or --- dividers.
- Use "- " bullets; keep each bullet to one line where possible. Do not nest bullets.
- Name the source when you cite a finding: (Legal review), (Clause 4.2), (MD briefing).
- End with the single most important next action, prefixed "**Next step:**".
- Stay under 250 words unless the user asks for more detail."""


# The whole system prompt must fit the model's context window with room for the
# chat history and the reply. Most important material is placed first so any
# overflow drops the least useful text rather than the MD briefing.
CONTEXT_CHAR_BUDGET = 36000
FINAL_BRIEFING_CHARS = 6000
TENDER_CHARS = 8000

# The chat history sent to the model is capped independently of what's stored:
# the DB keeps the full thread (and GET /discussion returns all of it), but the
# model only ever sees the most recent turns, within both a message-count and a
# total-character budget, and always starting on a "user" turn.
HISTORY_MAX_MESSAGES = 12
HISTORY_MAX_CHARS = 12000


def _build_context(payload: DiscussionIn) -> str:
    kind_name = "7-phase Analysis" if payload.kind == "roadmap" else "Bid Pipeline"

    parts: list[str] = []
    if payload.final_briefing:
        parts.append(f"=== MD FINAL BRIEFING ===\n{payload.final_briefing[:FINAL_BRIEFING_CHARS]}")

    if payload.tender_text:
        parts.append(f"=== TENDER DOCUMENT (excerpt) ===\n{payload.tender_text[:TENDER_CHARS]}")

    outputs = [(key, content) for key, content in payload.analysis_results.items() if content]
    if outputs:
        remaining = CONTEXT_CHAR_BUDGET - sum(len(p) for p in parts)
        per_output = max(800, remaining // len(outputs))
        parts.append(f"=== {kind_name.upper()} TEAM OUTPUTS ===")
        for key, content in outputs:
            label = key.replace("phase-", "").replace("-", " ").title()
            parts.append(f"--- {label} ---\n{content[:per_output]}")

    return "\n\n".join(parts)


def _owned_job(db: Session, job_id: str, user: User) -> AnalysisJob:
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id, AnalysisJob.user_id == user.id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return job


def _owned_tender(db: Session, tender_id: int, user: User) -> Tender:
    tender = db.query(Tender).filter(Tender.id == tender_id, Tender.user_id == user.id).first()
    if tender is None:
        raise HTTPException(status_code=404, detail="Tender not found")
    return tender


def _tender_versions(db: Session, tender_id: int) -> list[TenderVersion]:
    """A tender's versions that have a linked analysis job, oldest first."""
    return (
        db.query(TenderVersion)
        .filter(TenderVersion.tender_id == tender_id, TenderVersion.analysis_job_id.isnot(None))
        .order_by(TenderVersion.id)
        .all()
    )


def _tender_for_job(db: Session, job_id: str) -> Tender | None:
    version = db.query(TenderVersion).filter(TenderVersion.analysis_job_id == job_id).first()
    if version is None:
        return None
    return db.query(Tender).filter(Tender.id == version.tender_id).first()


def _stored_messages(db: Session, job_id: str) -> list[dict]:
    rows = db.query(DiscussionMessage).filter_by(job_id=job_id).order_by(DiscussionMessage.id).all()
    return [{"role": r.role, "content": decode_text(r.content)} for r in rows]


def _rows_for_jobs(db: Session, job_ids: list[str]) -> list[DiscussionMessage]:
    if not job_ids:
        return []
    return (
        db.query(DiscussionMessage)
        .filter(DiscussionMessage.job_id.in_(job_ids))
        .order_by(DiscussionMessage.id)
        .all()
    )


def _thread_messages(db: Session, job_ids: list[str]) -> list[dict]:
    """All messages across the given jobs, chronological (role/content only)."""
    return [{"role": r.role, "content": decode_text(r.content)} for r in _rows_for_jobs(db, job_ids)]


def _cap_history(history: list[dict]) -> list[dict]:
    """Keep only the most recent turns, within a message-count and a char budget.

    Drops the oldest messages first, then trims any leading non-"user" message
    so the capped thread never opens on an orphan assistant answer.
    """
    capped: list[dict] = []
    total_chars = 0
    for msg in reversed(history):
        if len(capped) >= HISTORY_MAX_MESSAGES:
            break
        msg_chars = len(msg.get("content") or "")
        if capped and total_chars + msg_chars > HISTORY_MAX_CHARS:
            break
        capped.append(msg)
        total_chars += msg_chars
    capped.reverse()

    while capped and capped[0].get("role") != "user":
        capped.pop(0)

    return capped


@router.get("/discussion")
def list_discussion(
    job_id: str | None = None,
    tender_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if (job_id is None) == (tender_id is None):
        raise HTTPException(status_code=400, detail="Provide exactly one of job_id or tender_id")

    if job_id is not None:
        _owned_job(db, job_id, user)
        rows = db.query(DiscussionMessage).filter_by(job_id=job_id).order_by(DiscussionMessage.id).all()
        return {"messages": [
            {"role": r.role, "content": decode_text(r.content), "job_id": job_id}
            for r in rows
        ]}

    tender = _owned_tender(db, tender_id, user)
    versions = _tender_versions(db, tender.id)
    version_by_job = {v.analysis_job_id: v for v in versions}
    rows = _rows_for_jobs(db, list(version_by_job.keys()))
    messages = []
    for r in rows:
        version = version_by_job.get(r.job_id)
        messages.append({
            "role": r.role,
            "content": decode_text(r.content),
            "job_id": r.job_id,
            "version_number": version.number if version else None,
            "version_label": version.label if version else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return {"messages": messages}


@router.post("/discussion")
def discuss(payload: DiscussionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kind_name = "7-phase Analysis" if payload.kind == "roadmap" else "Bid Pipeline"
    system_prompt = (
        SYSTEM_PROMPT_TEMPLATE.format(kind_name=kind_name)
        + "\n\n"
        + _build_context(payload)
        + get_profile_context(db, user.id)
    )

    if payload.job_id:
        _owned_job(db, payload.job_id, user)
        tender = _tender_for_job(db, payload.job_id)
        if tender is not None:
            job_ids = [v.analysis_job_id for v in _tender_versions(db, tender.id)]
            history = _thread_messages(db, job_ids)
        else:
            history = _stored_messages(db, payload.job_id)
    else:
        history = [{"role": m.role, "content": m.content} for m in payload.history
                   if m.role in ("user", "assistant") and m.content]
    history = _cap_history(history)
    messages = history + [{"role": "user", "content": payload.question}]

    try:
        reply = chat(system_prompt=system_prompt, messages=messages, max_tokens=2500, agent_id="md-final")
    except Exception as exc:
        print(f"[discussion] failed: {exc}")
        raise HTTPException(status_code=503, detail=user_facing_error(exc))

    if payload.job_id:
        db.add_all([
            DiscussionMessage(job_id=payload.job_id, user_id=user.id, role="user", content=encode_text(payload.question)),
            DiscussionMessage(job_id=payload.job_id, user_id=user.id, role="assistant", content=encode_text(reply)),
        ])
        db.commit()
    return {"reply": reply}
