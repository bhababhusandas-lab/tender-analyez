import asyncio
import json
import io
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import User
from app.core.security.auth import get_current_user
from app.core.limits import check_usage, record_usage
from app.core.llm.claude_client import chat_async, user_facing_error
from app.api.v1.company import get_profile_context
from app.api.v1.past_bids import get_past_bids_context
from app.api.v1.tender_analysis import get_vault_context, sse
from app.core.tender_condense import condense_for_final
from app.core.tender_inputs import read_uploads, source_block
from app.core import tender_history
from app.core.tender_condense import build_model_input
from app.core.tender_evidence import extract_tender_evidence, format_evidence_block, serialize_canonical_facts
from app.core.grounding import (
    GROUNDING_RULES,
    MIN_PROFILE_PERCENT,
    profile_completeness,
    thin_profile_warning,
)
from app.core.analysis_jobs import (
    create_job, finish_job, get_job_payload, load_job, run_with_timeout_retry, update_step,
)

router = APIRouter()
_ROADMAP_TASKS: dict[str, asyncio.Task] = {}


PHASES = [
    {
        "id": "phase-1-hunt",
        "name": "Phase 1 — Hunt",
        "subtitle": "Find the right tender / sector fit",
        "team": ["Market Intelligence", "Bid Manager", "Govt Liaison"],
        "prompt": """Acting as the Hunt Cell (Market Intelligence + Bid Manager + Govt Liaison Officer), assess whether this tender is worth pursuing. Complete every section in full.

**TENDER SNAPSHOT**
- Title:
- Department / Authority:
- Tender Reference / NIT No:
- Estimated Contract Value (₹):
- EMD (₹):
- Bid Submission Deadline:
- Contract Duration:
- Portal:
- Category / Sector:

**SECTOR & DEPARTMENT INTELLIGENCE**
- Department's annual procurement budget (only if supported by supplied evidence):
- Department's procurement priorities this year:
- Policy tailwind (e.g., PM Gati Shakti, Digital India, Jal Jeevan):
- Typical L1 pricing pattern in this department:

For this section, do not infer facts from general knowledge. If the tender/profile evidence does not support a claim, write "Not verified in supplied documents" and state what source must be checked.

**COMPETITOR LANDSCAPE — Likely Bidders**
| # | Competitor Company | Past Wins | Typical L1 Pattern | Strength | Weakness |
Name a company only when it appears in the supplied tender, company profile, or past-bid evidence. Never invent likely bidders, wins, pricing, strengths, or weaknesses. If no verified competitor evidence exists, provide one clearly labelled "Research required" row and list the sources to check.

**HISTORICAL L1 PRICES — Comparable Tenders**
| # | Past Tender | Year | Winner | L1 Price | Department |
Include only records found in the supplied evidence. If none are present, say "No verified historical L1 records in supplied documents"; do not fabricate rows.

**GOVT RELATIONSHIPS — Key Stakeholders**
| # | Designation | Department | What They Decide | Protocol to Approach |
List only stakeholder roles supported by the tender. Never invent names or contact details.

**OPPORTUNITY ASSESSMENT**
Use High / Medium / Low / Not Assessable for: Sector Fit / Eligibility Match / Budget Size / Competition Level / Strategic Value. Do not present a numeric score or win probability unless the supplied evidence contains a documented scoring method.

**HUNT VERDICT**: PURSUE / WATCHLIST / DROP — with 3-line justification.""",
    },
    {
        "id": "phase-2-qualify",
        "name": "Phase 2 — Qualify",
        "subtitle": "Bid / No-Bid decision",
        "team": ["Technical Expert", "Finance", "Legal", "MD"],
        "prompt": """Acting as the Qualification Cell (Technical Expert + Finance + Legal + MD perspective), decide BID or NO-BID. Be specific. Fill every table.

**ELIGIBILITY MATRIX** (Technical view)
| # | Eligibility Criterion | Tender Requirement | Our Status | Evidence | Gap / Action |
At least 10 rows. Mark each: ✅ Meet / ⚠️ Verify / ❌ Don't Meet.

**FINANCIAL CAPACITY CHECK** (Finance view)
| Item | Tender Requires | We Have | Gap |
- Min Avg Annual Turnover:
- Net Worth:
- EMD Amount and Capacity:
- PBG Amount and Capacity:
- Working Capital for 90 days:
- Solvency / Banker's Certificate:

**LEGAL RISK SCAN** (Legal view)
- Liquidated Damages Clause: rate, cap, trigger — full text or "Not specified"
- Blacklisting Clause: present? severity?
- Penalty / Termination Clauses: deal-breaker or workable?
- Arbitration Jurisdiction: favourable / neutral / unfavourable
- Indemnity & Force Majeure: balanced?
- Overall Legal Risk: 🟢 Low / 🟡 Medium / 🔴 High

**PRE-BID QUERIES TO RAISE**
Write the actual query text (3–5 queries) we should submit to amend tender conditions in our favour.

**TOP 5 RISKS** specific to this tender (with mitigation for each).

**MD GO / NO-GO DECISION**: GO ✅ / NO-GO ❌ / CONDITIONAL GO ⚠️
Full 4-line justification referencing eligibility, financial capacity, legal risk, and strategic value.""",
    },
    {
        "id": "phase-3-build",
        "name": "Phase 3 — Build",
        "subtitle": "Create the quotation",
        "team": ["Technical Expert", "Finance", "Pricing Analyst", "Tech Writer", "Legal", "Admin/HR", "Doc Controller"],
        "prompt": """Acting as the Build Cell (Technical + Finance + Pricing + Tech Writer + Legal + Admin/HR + Doc Controller), prepare an evidence-based quotation draft. Use "Not verified" for missing tender or company inputs rather than inventing them.

**TECHNICAL COMPLIANCE MATRIX**
| # | Requirement | Spec | Our Status | Evidence | Notes |
At least 10 rows.

**DRAFT METHODOLOGY** — 5 full paragraphs ready for the technical proposal:
1. Understanding of Scope
2. Technical Approach
3. Project Team Structure
4. Quality Assurance Plan
5. Timeline & Milestones

**COMPLETE BOQ (Bill of Quantities)**
| S.No | Item | Unit | Qty | Market Rate (₹) | Our Rate (₹) | Amount (₹) |
Include only quantities and rates supported by the tender, company profile, or past-bid evidence. Put "Rate input required" where commercial evidence is missing.

**COST BUILD-UP**
| Component | Amount (₹) | % |
Direct Labour / Materials / Equipment / Travel / Subcontract / Overhead 15% / Contingency 5% / Total Cost / Margin %.

**WIN-ZONE L1 ANALYSIS (Pricing Analyst)**
- Tender Estimate vs Our Cost Engineering:
- Aggressive L1: ₹
- Recommended Winning L1: ₹  ← THIS IS OUR QUOTE
- Safe Profitable Bid: ₹
- L2 / L3 likely band: ₹ — ₹
- Win probability at recommended L1: __%
- Margin at recommended L1: __%

**PRICE JUSTIFICATION NOTE** — 3 paragraphs ready to submit if department questions our price.

**PROPOSAL DESIGN STRUCTURE** (Tech Writer)
Table of Contents (12+ sections), Executive Summary (200 words), List of Diagrams.

**LEGAL ANNEXURES TO PREPARE**
List of declarations, undertakings, indemnity bonds, integrity pact, stamp duty.

**MANPOWER DEPLOYMENT** (Admin/HR)
| Phase | Duration | Role | Count | Source (Team / Hire / Subcontract) |

**DOCUMENT PACK CHECKLIST** (Doc Controller)
Mandatory eligibility / technical / financial / legal docs — at least 15 items with vault status.""",
    },
    {
        "id": "phase-4-review",
        "name": "Phase 4 — Review",
        "subtitle": "Zero-defect audit",
        "team": ["QA Reviewer", "MD", "Doc Controller"],
        "prompt": """Acting as the Review Cell (QA Reviewer + MD + Doc Controller), run a final audit. Be ruthless.

**ELIGIBILITY VERIFICATION (10 items)** — re-check each criterion vs our credentials, mark ✅⚠️❌.

**DOCUMENT INTEGRITY CHECKLIST (15 items)**
| # | Check Point | Status | Risk if Missed |
Signatures, seals, page numbering, attestation, validity, naming, stamp duty, etc.

**FINANCIAL BID CONSISTENCY (10 items)** — BOQ ↔ Scope tally, GST correct, EMD matched, number-in-words matches numerals, validity stated.

**TECHNICAL BID CONSISTENCY (10 items)** — compliance matrix complete, CVs ↔ deployment plan, brochures attached, deviation statement, undertakings signed.

**PORTAL & FORMAT COMPLIANCE (10 items)** — file size, format, naming, separate covers, DSC, deadline buffer (T-24h).

**TENDER-CLAUSE-TO-BID MAP** — list every numbered tender clause → where addressed → status. At least 15 rows.

**CRITICAL ISSUES FOUND**
| # | Issue | Severity | Location | Fix Required |

**MINOR ISSUES (nice-to-fix)**

**MD FINAL READ — Sign-off Points**
3-line confirmation by MD on: pricing comfort, key commitments, executive summary clarity.

**FINAL VERDICT**: 🟢 GO FOR SUBMISSION / 🟡 FIX MINORS / 🔴 DO NOT SUBMIT — one-line reason.""",
    },
    {
        "id": "phase-5-submit",
        "name": "Phase 5 — Submit",
        "subtitle": "Portal submission plan",
        "team": ["IT Support", "Doc Controller", "Finance", "Bid Manager"],
        "prompt": """Acting as the Submission Cell (IT Support + Doc Controller + Finance + Bid Manager), build the complete submission playbook. T-24 hour rule applies.

**EMD / BID SECURITY TRANSFER PLAN**
- Mode required by tender:
- Amount: ₹
- Beneficiary details (from tender):
- When to transfer: T-48h
- Proof to capture: NEFT UTR / DD No / BG No
- Validity period of EMD instrument:

**DSC & PORTAL READINESS**
- DSC holder name and class:
- DSC validity check date:
- Portal account credentials verified:
- 2FA / OTP method:
- Browser / Java version verified:
- Test login completed at T-48h?

**UPLOAD SEQUENCE PLAN**
| Step | File | Size | Format | Section on Portal | Owner |
At least 10 rows in the exact upload order.

**T-24h to T-0 CHECKLIST**
| Time | Action | Owner | Verified |
At least 12 items from T-24h down to T-0.

**SUBMISSION PROOFS TO CAPTURE**
- Acknowledgement number:
- Submission timestamp:
- Full-page screenshots:
- Bid hash:
- Saved to: (file path / cloud location)

**FALLBACK PLAN IF PORTAL FAILS**
- Helpdesk numbers and emails:
- Manual submission window (if any):
- Internal escalation owner:

**MD SUBMISSION SUMMARY TEMPLATE**
Tender name | Submission time | Acknowledgement no | Next key date | Owner-on-duty.""",
    },
    {
        "id": "phase-6-win",
        "name": "Phase 6 — Win",
        "subtitle": "Evaluation & negotiation",
        "team": ["Bid Manager", "Pricing Analyst", "Legal", "Technical Expert", "Govt Liaison", "MD"],
        "prompt": """Acting as the Win Cell (Bid Manager + Pricing + Legal + Technical + Govt Liaison + MD), plan the post-submission strategy through to contract award.

**BID OPENING MONITORING PLAN**
- Online opening attendance plan:
- Data to capture at opening: L1 price, number of bidders, technical shortlist
- Owner for opening attendance:

**EVALUATION COMMITTEE — Expected Queries**
List 5 likely clarification queries the committee may raise, and our pre-drafted response framework.

**RESPONSE PROTOCOLS**
| Query Type | Response Owner | Response SLA |
Technical / Financial / Legal / Documentary — with response timelines.

**GOVT LIAISON CHECK-INS**
- Schedule of professional check-ins with nodal officer (frequency, mode):
- Topics safe to discuss / NOT to discuss

**NEGOTIATION STRATEGY (if called)**
- Our floor price (Pricing Analyst):
- Concessions we can offer in exchange for higher price:
- Non-negotiable terms (Legal):
- Negotiation lead: MD, supported by Pricing Analyst + Legal

**LoA / WORK ORDER REVIEW CHECKLIST (10 items)**
Items Legal must verify in the Letter of Acceptance before MD signs.

**PBG INITIATION PLAN**
- PBG amount: ₹
- Bank:
- Format:
- Days to issue: __
- Validity period:

**EXPECTED OUTCOME**: Probability-weighted scenarios — Win at recommended L1 / Win after negotiation / Lose to lower L1 / Tender re-floated.""",
    },
    {
        "id": "phase-7-execute",
        "name": "Phase 7 — Execute",
        "subtitle": "Contract delivery plan",
        "team": ["Admin/HR", "Finance", "Legal", "Bid Manager", "Technical", "Govt Liaison"],
        "prompt": """Acting as the Execute Cell (Admin/HR + Finance + Legal + Bid Manager + Technical + Govt Liaison), build the execution playbook ASSUMING we win.

**KICK-OFF PLAN (Day 0 to Day 30)**
| Action | Owner | Deadline | Deliverable |
At least 10 actions for the first 30 days of contract.

**RESOURCE MOBILISATION**
- Project Manager (name or "to hire"):
- Core team headcount and roles:
- Site / service location:
- Equipment / material mobilisation:

**MILESTONE & BILLING SCHEDULE**
| Milestone | Date / Trigger | Deliverable | Invoice Amount (₹) | Expected Payment Date |
At least 5 milestones.

**SLA & LD MONITORING**
| SLA Clause | Trigger | Our Internal Buffer | LD if Missed |
At least 5 critical SLAs.

**LABOUR & STATUTORY COMPLIANCE**
- PF / ESI applicability and registration status:
- Minimum wages compliance plan:
- Monthly compliance reports schedule:
- Audit-readiness pack location:

**RISK REGISTER (Top 5)**
| Risk | Likelihood | Impact | Owner | Mitigation |

**GOVT LIAISON PLAN**
- Reporting cadence to department:
- Monthly review schedule:
- Escalation matrix on issues:

**EXIT / COMPLETION PLAN**
- Completion Certificate process:
- PBG release plan:
- Reference letter request plan:
- Repeat-business pipeline from this department:""",
    },
]


FINAL_QUOTE_PROMPT = """You are the Managing Director of Unique Type. The 7-phase roadmap analysis is complete. Produce the FINAL QUOTE ANALYSIS — a decisive, MD-grade summary that ties everything together.

**TENDER FINAL QUOTE ANALYSIS — CONFIDENTIAL**

**EXECUTIVE SUMMARY (5 sentences)**
What the tender is, why it matters, our position, our recommended quote, our confidence level.

**FINAL RECOMMENDED QUOTE: ₹ [EXACT FIGURE]**
2 lines justifying the figure with reference to the Build phase pricing and the Hunt phase competitor intel.

**BID CONFIDENCE SCORE: [X]%**
Department-wise breakdown:
- Hunt / Opportunity Fit: [X]%
- Eligibility & Qualification: [X]%
- Technical Readiness: [X]%
- Financial Competitiveness: [X]%
- Document Readiness: [X]%
- Legal Risk Posture: [rating]
- Submission Readiness: [X]%
- Execution Capacity: [X]%
- **OVERALL CONFIDENCE: [X]%**

**FINAL DECISION: GO ✅ / NO-GO ❌ / CONDITIONAL GO ⚠️**
4-line justification referencing each of the 7 phases.

**WIN PROBABILITY: [X]%**
Reasoning tied to historical L1 patterns from Hunt phase.

**CRITICAL ACTION ITEMS — Next 72 Hours**
| # | Action | Phase | Owner | Deadline |
At least 10 specific actions across all phases.

**PHASE-WISE READINESS DASHBOARD**
| Phase | Readiness % | Blocker | Owner |
| 1 Hunt | | | |
| 2 Qualify | | | |
| 3 Build | | | |
| 4 Review | | | |
| 5 Submit | | | |
| 6 Win | | | |
| 7 Execute | | | |

**STRATEGIC NOTES — MD'S CALL**
3-4 lines: what we will and won't compromise on, what we expect from each team, and the key signal to watch in the next 7 days.

Every number must be specific. No vague advice. This is what gets shared with the team to mobilise."""


async def run_phase(system_prompt: str, task_prompt: str, tender_text: str, prior_context: str = "", max_tokens: int | None = None, agent_id: str | None = None) -> str:
    user_msg = f"TENDER DOCUMENT:\n\n{tender_text}"
    if prior_context:
        user_msg += (
            "\n\n---\n\nPRIOR TEAM ANALYSIS (from earlier phases of this same bid) — "
            "incorporate these findings into your work, don't repeat them:\n" + prior_context
        )
    closing = (
        " Build on the prior phases above — reference their specific findings, numbers, and decisions where relevant."
        if prior_context else ""
    )
    user_msg += (
        f"\n\n---\n\nIMPORTANT: Complete every section below, but use only the supplied evidence. "
        f"Never invent facts, names, dates, tender numbers, values, prices, credentials, projects, certifications, links, or historical records to fill a section or table. "
        f"When evidence is absent, write 'Not verified in supplied documents' and identify the exact source or action needed to verify it. "
        f"Preserve the source labels required by the grounding rules. Produce a complete, evidence-led report.{closing}\n\n"
        f"TASK BRIEF:\n\n{task_prompt}"
    )
    return await chat_async(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=max_tokens,
        agent_id=agent_id,
    )


async def _run_roadmap_background(job_id: str, user_id: int, retry_phase_id: str | None = None) -> None:
    try:
        loaded = load_job(job_id, user_id, "roadmap")
        if not loaded:
            return
        job, context, saved = loaded
        company_ctx = context.get("company_ctx", "")
        vault_ctx = context.get("vault_ctx", "")
        past_bids_ctx = context.get("past_bids_ctx", "")
        grounding = context.get("grounding", GROUNDING_RULES)

        def system_prompt(phase: dict) -> str:
            extra = past_bids_ctx if phase["id"] in ("phase-1-hunt", "phase-3-build") else ""
            return (
                f"You are leading the {phase['name']} cell at Unique Type. "
                f"The cell consists of: {', '.join(phase['team'])}. "
                "Synthesise every team member's perspective into one evidence-led output."
                + company_ctx + vault_ctx + extra + grounding
            )

        retry_reached = retry_phase_id is None
        for phase in PHASES:
            phase_id = phase["id"]
            current = load_job(job_id, user_id, "roadmap")
            assert current is not None
            _, _, steps = current
            if not retry_reached:
                if phase_id != retry_phase_id:
                    continue
                retry_reached = True
            if phase_id != retry_phase_id and steps.get(phase_id) and steps[phase_id].status == "done":
                continue
            prior = []
            for prior_phase in PHASES:
                if prior_phase["id"] == phase_id:
                    break
                step = steps.get(prior_phase["id"])
                if step and step.status == "done":
                    prior.append(f"=== {prior_phase['name']} ===\n{step.content}")
            try:
                content = await run_with_timeout_retry(
                    lambda p=phase, prior_text="\n\n".join(prior): run_phase(
                        system_prompt(p), p["prompt"], job.tender_text,
                        prior_context=prior_text, agent_id=p["id"],
                    ),
                    job_id, phase_id,
                )
                update_step(job_id, phase_id, "done", content=content, error=None)
            except Exception as exc:
                print(f"[roadmap] {phase_id} failed: {exc}")
                update_step(job_id, phase_id, "error", error=user_facing_error(exc))
                finish_job(job_id, "partial", error=f"{phase['name']} requires retry")
                return
        refreshed = load_job(job_id, user_id, "roadmap")
        assert refreshed is not None
        _, _, steps = refreshed
        phase_ids = {p["id"] for p in PHASES}
        if any(step_id in phase_ids and step.status != "done" for step_id, step in steps.items()):
            finish_job(job_id, "partial", error="Roadmap has unfinished phases")
            return
        final_tender, combined = condense_for_final(job.tender_text, [
            (f"{p['name'].upper()} ({p['subtitle']})", steps[p["id"]].content) for p in PHASES
        ])
        try:
            final = await run_with_timeout_retry(
                lambda: run_phase(
                    "You are an AI decision-support analyst for Indian government tenders." + company_ctx + grounding,
                    FINAL_QUOTE_PROMPT,
                    f"TENDER:\n{final_tender}\n\nROADMAP ANALYSIS:\n{combined}", agent_id="md-final",
                ),
                job_id, "md-final",
            )
            update_step(job_id, "md-final", "done", content=final, error=None)
            finish_job(job_id, "completed", final_content=final, error=None)
        except Exception as exc:
            print(f"[roadmap] md-final failed: {exc}")
            update_step(job_id, "md-final", "error", error=user_facing_error(exc))
            finish_job(job_id, "partial", error=user_facing_error(exc))
    except Exception as exc:
        finish_job(job_id, "partial", error=str(exc))
    finally:
        _ROADMAP_TASKS.pop(job_id, None)


def _ensure_roadmap_running(job_id: str, user_id: int, retry_phase_id: str | None = None) -> None:
    task = _ROADMAP_TASKS.get(job_id)
    if task and not task.done():
        return
    finish_job(job_id, "running", error=None)
    _ROADMAP_TASKS[job_id] = asyncio.create_task(
        _run_roadmap_background(job_id, user_id, retry_phase_id), name=f"roadmap-{job_id}"
    )


async def watch_roadmap_job(job_id: str, user_id: int):
    yield sse({"type": "job_created", "job_id": job_id})
    previous: dict[str, tuple] = {}
    while True:
        payload = get_job_payload(job_id, user_id)
        if not payload:
            yield sse({"type": "error", "message": "Analysis job not found."})
            return
        for step in payload["steps"]:
            signature = (step["status"], step["content"], step["error"], step["attempts"])
            if previous.get(step["id"]) == signature:
                continue
            previous[step["id"]] = signature
            if step["id"] == "md-final":
                if step["status"] == "running":
                    yield sse({"type": "final_start"})
                elif step["status"] == "done":
                    results = {s["id"]: s["content"] for s in payload["steps"] if s["id"] != "md-final"}
                    results["final"] = step["content"]
                    yield sse({"type": "final_done", "content": step["content"], "all_results": results, "job_id": job_id})
                elif step["status"] == "error":
                    yield sse({"type": "final_error", "message": step["error"] or "Final briefing failed"})
            else:
                phase = next((p for p in PHASES if p["id"] == step["id"]), None)
                if step["status"] in {"waiting", "running"}:
                    yield sse({"type": "phase_start", "phase_id": step["id"], "phase_name": step["name"],
                               "subtitle": phase["subtitle"] if phase else "", "team": phase["team"] if phase else []})
                elif step["status"] == "done":
                    yield sse({"type": "phase_done", "phase_id": step["id"], "content": step["content"]})
                elif step["status"] == "error":
                    yield sse({"type": "phase_error", "phase_id": step["id"], "message": step["error"] or "Phase failed"})
        if payload["status"] in {"completed", "partial", "failed"}:
            if payload["status"] != "completed":
                yield sse({"type": "job_paused", "job_id": job_id})
            yield "data: [DONE]\n\n"
            return
        yield ": keepalive\n\n"
        await asyncio.sleep(1)


@router.post("/tender/analyze-roadmap/{job_id}/resume")
async def resume_roadmap(job_id: str, user: User = Depends(get_current_user)):
    if not load_job(job_id, user.id, "roadmap"):
        raise HTTPException(status_code=404, detail="Analysis job not found")
    _ensure_roadmap_running(job_id, user.id)
    return StreamingResponse(watch_roadmap_job(job_id, user.id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/tender/analyze-roadmap/{job_id}/retry/{phase_id}")
async def retry_roadmap_phase(job_id: str, phase_id: str, user: User = Depends(get_current_user)):
    if phase_id not in {p["id"] for p in PHASES}:
        raise HTTPException(status_code=404, detail="Unknown roadmap phase")
    if not load_job(job_id, user.id, "roadmap"):
        raise HTTPException(status_code=404, detail="Analysis job not found")
    update_step(job_id, phase_id, "waiting", error=None)
    _ensure_roadmap_running(job_id, user.id, phase_id)
    return StreamingResponse(watch_roadmap_job(job_id, user.id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def start_roadmap_job(db: Session, user: User, raw_text: str, *, evidence=None) -> str:
    """Build the AI input, create the durable 7-phase job and start it. Returns the job id."""
    evidence = extract_tender_evidence(raw_text) if evidence is None else evidence
    evidence_block = format_evidence_block(evidence)
    canonical_facts, _ = serialize_canonical_facts(evidence)
    # Oversized tenders are condensed to the passages a bid analysis needs
    # instead of letting the model silently drop everything past its context.
    text = build_model_input(raw_text, evidence_block)
    company_ctx = get_profile_context(db, user.id)
    vault_ctx = get_vault_context(db, user.id)
    past_bids_ctx = get_past_bids_context(db, user.id)
    profile_pct, profile_missing = profile_completeness(db, user.id)
    grounding = GROUNDING_RULES
    if profile_pct < MIN_PROFILE_PERCENT:
        grounding += thin_profile_warning(profile_pct, profile_missing)
    job_id = create_job(
        user.id, "roadmap", text,
        {
            "company_ctx": company_ctx, "vault_ctx": vault_ctx, "past_bids_ctx": past_bids_ctx,
            "grounding": grounding, "profile_pct": profile_pct, "profile_missing": profile_missing,
            "canonical_facts": canonical_facts,
        },
        PHASES + [{"id": "md-final", "name": "Final Decision Briefing"}],
    )
    _ensure_roadmap_running(job_id, user.id)
    return job_id


@router.post("/tender/analyze-roadmap")
async def analyze_tender_roadmap(
    tender_text: str = Form(""),
    file: UploadFile | None = File(None),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Plan limit check — block before doing any work
    ok, info = check_usage(user, db, "roadmap")
    if not ok:
        raise HTTPException(status_code=402, detail=info)

    uploads = list(files)
    if file is not None:
        uploads.insert(0, file)  # backwards compatibility
    text_parts = [f"--- PASTED TENDER TEXT ---\n{tender_text.strip()}"] if tender_text.strip() else []
    docs, extraction_errors = await read_uploads(uploads)
    text_parts.extend(source_block(doc) for doc in docs)

    raw_text = "\n\n".join(text_parts).strip()

    if extraction_errors or not raw_text:
        async def err():
            yield sse({
                "type": "error",
                "message": " ".join(extraction_errors) or "No tender content provided.",
            })
        return StreamingResponse(err(), media_type="text/event-stream")

    # Record this run against the user's quota
    record_usage(db, user.id, "roadmap")

    evidence = extract_tender_evidence(raw_text)
    job_id = start_roadmap_job(db, user, raw_text, evidence=evidence)
    stream = watch_roadmap_job(job_id, user.id)
    try:
        tender, _ = await asyncio.to_thread(
            tender_history.start_run, db, user.id,
            tender=None, kind="roadmap", job_id=job_id, docs=docs, pasted_text=tender_text,
            note="", name_hint=tender_history.tender_name(evidence, docs),
        )
        tender_id = tender.id  # read now: the request's DB session may be closed while streaming

        async def announce(inner):
            yield sse({"type": "tender", "tender_id": tender_id})
            async for chunk in inner:
                yield chunk

        stream = announce(stream)
    except Exception as exc:  # history is a convenience; it must never block the analysis
        db.rollback()
        print(f"[history] could not record tender for job {job_id}: {exc}")

    return StreamingResponse(stream, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
