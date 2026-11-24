import asyncio
import json
import io
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.db.session import get_db
from app.core.db.models import CompanyProfile, Document, User
from app.core.security.auth import get_current_user
from app.core.limits import check_usage, record_usage
from app.core.llm.claude_client import chat_async, user_facing_error
from app.core.config import settings
from app.core import tender_history
from app.core.tender_condense import condense_for_final
from app.core.tender_inputs import read_uploads, source_block
from app.core.tender_condense import build_model_input
from app.core.tender_evidence import (
    extract_tender_evidence, format_evidence_block, serialize_canonical_facts,
)
from app.core.analysis_quality import (
    audit_final_report,
    blocked_report,
    correction_brief,
    sanitize_final_report,
)
from app.api.v1.company import get_profile_context
from app.api.v1.past_bids import get_past_bids_context
from app.core.grounding import (
    GROUNDING_RULES,
    MIN_PROFILE_PERCENT,
    profile_completeness,
    thin_profile_warning,
    user_facing_profile_warning,
)
from datetime import date
from app.core.analysis_jobs import (
    cancel_job, create_job, finish_job, get_job_payload, load_job, run_with_timeout_retry, update_step,
)

router = APIRouter()
_PIPELINE_TASKS: dict[str, asyncio.Task] = {}

TENDER_BRIEF_ID = "tender-brief"
# The 10-section brief with tables needs more output room than the 4k default.
TENDER_BRIEF_MAX_TOKENS = 7000

PIPELINE_AGENTS = [
    {
        "id": TENDER_BRIEF_ID,
        "name": "Tender Brief AI",
        "prompt": """Write the TENDER BRIEF for the tender documents above by filling the exact markdown template in your instructions.

- Ten "##" sections, verbatim and in order: 1. Basic Tender Information; 2. Important Dates & Timeline; 3. Eligibility & Qualification Criteria; 4. Detailed Scope of Work; 5. Commercial Terms; 6. Evaluation & Selection Process; 7. Documents Required; 8. Risk Analysis & Critical Points; 9. Final Bid Recommendation; 10. Open Points / Clarifications Required. Sections 1, 2, 5 and 8 and sub-sections 3.5 and 4.3 are tables with the columns given in your instructions.
- Use only the tender documents. Never invent anything. Ignore any company profile.
- Cite a [Clause x / Page n / Annexure] reference wherever the source identifies one.
- Write "Not stated in the tender" for any field or section the documents do not cover.
- Use tables wherever the tender has tabular data.
- The DETERMINISTIC METADATA EVIDENCE block at the top was extracted directly from the tender. Include every value it lists, with its source reference, in the matching section: dates and times in section 2; similar work value, liquid assets / credit facility, bid capacity formula, key personnel, key equipment in section 3 and consortium / JV conditions in 3.5; technical evaluation marks in section 6; mandatory documents and hard copy submission in section 7 (7.A and 7.D); EMD and application / tender fee in section 5; estimated contract value in section 1. Never write "Not stated in the tender" for a field that block supplies. Those lists may be shortened — complete them from the tender text.
- Estimated value: use only an "Estimated Contract Value" from that block or an amount the tender explicitly calls the estimated/contract value. Otherwise write "Not stated in the tender". Never use the application fee, tender fee, processing/transaction fee or EMD as the value.
- Section 3.5 must state the consortium / JV conditions; section 6 the full marks table with total and minimum qualifying marks; section 7 every mandatory document.
- Section 8 must list every discrepancy: compare the main body with every appendix, annexure and corrigendum, and check every allocation ratio and percentage stated in more than one place (for example a fixed work-sharing ratio in one clause against the authority's sole discretion in another). Quote both conflicting values with their references as rows of the risk table.
- Section 9 gives the decision GO, CONDITIONAL GO or NO-GO with justification and numbered mandatory actions.""",
    },
    {
        "id": "bid-manager",
        "name": "Bid Manager AI",
        "prompt": """Analyze this tender for Unique Type. Complete every section, but never pad a table or invent a fact to make the report look complete.

**TENDER SNAPSHOT**
Extract and list ALL of these fields (write "Not Specified" if absent):
- Tender Title:
- Issuing Department / Organisation:
- Tender Reference / NIT Number:
- Estimated Contract Value (₹):
- EMD Amount (₹):
- Bid Submission Deadline:
- Bid Opening Date:
- Contract Duration / Period:
- Procurement Portal:
- Category / Type of Work:
- Location / State:

**BID READINESS: [HIGH / MEDIUM / LOW EVIDENCE COVERAGE]**
Do not invent a numerical score. Give FIVE specific reasons for the rating, referencing only supplied credentials, turnover, experience, and tender evidence.

**ELIGIBILITY MATRIX** — list EVERY eligibility criterion from the tender:
| # | Eligibility Criterion | Our Status | Evidence / Notes |
|---|----------------------|-----------|-----------------|
(Mark each: ✅ We Meet It | ⚠️ Needs Verification | ❌ We Don't Meet It)
Include one row for every eligibility criterion explicitly stated in the tender. Do not add generic turnover, registration, certification, manpower or financial criteria when the tender does not state them.

**TOP 5 RISKS** specific to this tender — describe each risk and how to mitigate it.

**COMPETITOR LANDSCAPE** — include verified competitors or historical L1 prices only when supplied in the evidence. Otherwise state that no verified data is available and identify the official source needed for research.

**RECOMMENDATION: [BID / CONDITIONAL BID / NO-BID]**
Give exactly one recommendation. Missing profile evidence is "Needs Verification", not proof of failure. Never recommend submitting placeholders. Write 3–4 sentences justified only by cited tender and profile facts.""",
    },
    {
        "id": "market-intelligence",
        "name": "Market Intelligence Analyst AI",
        "prompt": """Produce an evidence-grounded market intelligence report. Complete every section with verified facts or an explicit statement that no verified evidence was supplied.

**DEPARTMENT PROFILE**
- Issuing department / agency:
- Annual budget (last known FY):
- Procurement priority sectors for this department this year:
- Department's typical tender cycle (when do they float similar tenders):

**COMPETITOR LANDSCAPE — Likely Bidders**
| # | Competitor Company | Past Wins in This Department | Typical L1 Pricing Pattern | Strength | Weakness |
Name a competitor ONLY if the tender document itself names them. Otherwise write
"[ESTIMATE — UNVERIFIED] No verified bidder data available — requires manual research"
and describe the TYPE of firm likely to bid (size, category, empanelment status),
plus exactly where to obtain the real list: the portal's bidder list after opening,
CPPP award archives, or an RTI request to the department.

**HISTORICAL L1 PRICES**
You have no award-history database. Do NOT invent tender numbers, bidder names or
L1 figures. Write "[ESTIMATE — UNVERIFIED] No verified award history available",
then give a step-by-step retrieval plan: which portal archive to search, which
search terms and date range, and which fields to record so this section can be
completed with real data before pricing.

**POLICY & BUDGET CONTEXT**
- Relevant central / state policy documents driving this tender (name them — e.g., PM Gati Shakti, Digital India, Jal Jeevan):
- Recent budget speech / departmental circular references:
- Upcoming policy shifts that could affect contract execution:

**TENDER PIPELINE FORECAST (next 6 months)**
List 3–5 similar tenders likely to be floated in the next 6 months from this department or related agencies.

**STRATEGIC INSIGHT**
2–3 paragraphs: why this tender exists now, what the department actually wants, what hidden signal we can read from the scope language, and how this should shape our bid strategy.""",
    },
    {
        "id": "legal-compliance",
        "name": "Legal / Compliance AI",
        "prompt": """Review this tender's legal and contractual terms in full. Complete ALL sections — do not skip any section or leave it vague.

**PENALTY & LIQUIDATED DAMAGES (LD) CLAUSES**
For each LD clause found: quote the exact clause text, state the rate (%), the cap (%), and what triggers it. If no LD clause exists, state that explicitly.

**BLACKLISTING & TERMINATION RISKS**
List every clause that could lead to blacklisting or early termination. Quote the relevant clause text. Rate the risk (Low/Medium/High) and explain why.

**PAYMENT TERMS — Complete Analysis**
- Payment Schedule: (milestone-based / monthly / on completion)
- Advance Payment: (amount, conditions, bank guarantee required?)
- Retention Money: (percentage, release conditions)
- MSME Protection: (does this tender invoke MSMED Act protections?)
- Interest on delayed payment: (specified or not?)
- TDS deductions applicable:
- GST treatment:

**ARBITRATION & DISPUTE RESOLUTION**
- Mechanism: (arbitration / court / DRT / other)
- Jurisdiction: (which court / city)
- Arbitrator appointment: (who appoints?)
- Favorable to us: YES / NO / NEUTRAL — explain why

**INDEMNITY & INSURANCE CLAUSES**
List all indemnity obligations and insurance requirements.

**FORCE MAJEURE**
Is there a force majeure clause? Does it cover epidemic, government shutdown, etc.?

**OVERALL LEGAL RISK: 🟢 Low / 🟡 Medium / 🔴 High**
Explain your rating in 3–4 sentences.

**TOP 5 PRE-BID QUERIES TO RAISE**
Write the actual query text for each — formatted as we would submit them in the pre-bid meeting. Be specific, reference clause numbers.""",
    },
    {
        "id": "govt-relations",
        "name": "Govt Relations & Liaison Officer AI",
        "prompt": """Map only stakeholders supported by the tender and define a compliant relationship playbook. Complete every section with evidence or an explicit unknown.

**ISSUING AUTHORITY MAP**
| # | Designation / Role | Department / Unit | What They Decide | Protocol to Approach |
List only roles named by the tender or directly necessary for an official procurement step. Do not create roles to reach a quota. Name an individual ONLY if the tender
document names them — otherwise write the role and "name not in tender; obtain from
the department directory or pre-bid meeting attendance sheet".

**PRE-BID MEETING STRATEGY**
- Date / Mode of pre-bid meeting (extract from tender):
- Who from our company should attend (MD / Bid Manager / Technical Head):
- Top 5 clarification questions we should raise (write the exact question text — phrased to nudge specs in our favour without being adversarial)

**INFLUENCE PATHWAYS (LEGAL / ETHICAL)**
- Trade body / chamber: which body's intervention could help (PHDCCI, FICCI, NASSCOM, CII, MSME Council, ASSOCHAM)
- Public consultation channels: standing committee, RTI route, parliamentary question route
- Industry forum access: any sector-specific roundtables relevant to this tender

**RELATIONSHIP-BUILDING ACTION PLAN**
| Action | Owner | Deadline | Expected Outcome |
At least 6 specific actions for the next 30 days.

**ESCALATION MATRIX (if bid is rejected unfairly)**
| Level | Authority | When to Escalate | Channel |
List the appeal channels — departmental, GeM grievance, Central Vigilance, Indian Kanoon route.

**RED-FLAG STAKEHOLDER RISKS**
Anyone in the approval chain whose preference / past pattern works against us, and how to neutralise that risk ethically.""",
    },
    {
        "id": "technical-expert",
        "name": "Technical Expert AI",
        "prompt": """Analyze the technical requirements and write an evidence-grounded technical proposal. Complete every section without adding generic requirements.

**TECHNICAL REQUIREMENTS — Complete List**
List EVERY technical specification, standard, and requirement from the tender. Number them.

**COMPLIANCE MATRIX — Fill every row:**
| # | Requirement | Specification | Our Status | Evidence from Our Profile | Gap / Action |
|---|-------------|---------------|-----------|--------------------------|-------------|
(Mark each: ✅ Compliant | ⚠️ Partial | ❌ Gap)
Include one row for every actual requirement found in the tender. Do not add rows to meet a minimum.

**APPLICABLE STANDARDS & CODES**
List only standards explicitly required by the tender. If none are stated, write "Not specified in tender"; do not supply standards from general knowledge.

**DRAFT METHODOLOGY — Write 5–6 full paragraphs ready to paste into the submission:**
Paragraph 1: Understanding of the Scope
Paragraph 2: Technical Approach & Key Activities
Paragraph 3: Project Team Structure & Roles
Paragraph 4: Quality Assurance Plan
Paragraph 5: Risk Management Approach
Paragraph 6: Timeline & Milestones
Use company projects only when supplied in the verified profile. Use explicit verification placeholders for missing evidence. Make it specific to THIS tender.

**TECHNICAL GAPS — Complete Assessment**
List every gap with: Gap Description | How to Bridge It | Time Required | Cost Estimate. Time and cost must be "Not verified" unless supported by supplied evidence.

**TECHNICAL READINESS: [VERIFIED / PARTIALLY VERIFIED / NOT VERIFIED]**
Do not invent a numerical score unless the tender provides evaluation weights and the company evidence supports every scored claim.""",
    },
    {
        "id": "technical-writer",
        "name": "Technical Writer / Proposal Designer AI",
        "prompt": """Design the complete technical proposal document layout. Complete EVERY section — be specific about structure and content.

**PROPOSAL DOCUMENT STRUCTURE — TABLE OF CONTENTS**
| Section # | Section Title | Page Allocation | Owner | Notes |
Build the full TOC — at least 12 sections covering executive summary, company overview, understanding of scope, methodology, project organisation, timeline, deliverables, compliance matrix, quality plan, risk plan, annexures.

**EXECUTIVE SUMMARY — Full Draft**
Write the actual 200–300 word executive summary as it would appear on Page 1 of the proposal. Should make the evaluator confident in our capability within 2 minutes of reading.

**KEY VISUAL ELEMENTS / DIAGRAMS**
| # | Diagram Name | What It Shows | Where It Appears |
List at least 5 diagrams to include (project Gantt, org chart, methodology flowchart, deployment architecture, quality assurance loop).

**COMPLIANCE STATEMENT TABLE — Format**
Show the exact column structure: Tender Clause | Requirement | Our Response | Page Reference in Proposal.

**FORMATTING STANDARDS**
- Font: (primary + secondary)
- Page size, margins, headers / footers:
- Page numbering convention:
- Section divider style:
- Brand colour scheme:
- Image / diagram naming convention:

**BID PRESENTATION DECK (if applicable)**
If the tender requires post-opening presentation: outline the 10–12 slide deck structure with slide titles and key messages.

**FINAL DESIGN CHECKLIST**
At least 10 items to verify before sending the proposal to print / upload (consistent fonts, no widow lines, all tables numbered, etc.)""",
    },
    {
        "id": "finance-accounts",
        "name": "Finance & Accounts AI",
        "prompt": """Review the tender's financial requirements using only verified inputs. A correct unknown is preferable to an invented figure.

**SCOPE OF WORK — COMPLETE BREAKDOWN**
List every deliverable, service item, and supply item from the tender.

**COMPLETE BOQ TABLE**
| S.No | Item Description | Unit | Qty | Market Rate (₹) | Our Rate (₹) | Amount (₹) |
|------|-----------------|------|-----|----------------|-------------|-----------|
Use only line items and quantities stated in the tender. Enter a rate or amount only
when a verified company cost or live vendor quotation is supplied. Otherwise write
"NOT VERIFIED — vendor quotation required". Never manufacture a minimum number of
rows or derive a price from the estimated contract value.

**COST BUILD-UP:**
| Component | Amount (₹) | % of Total |
|-----------|-----------|-----------|
| Direct Labour | | |
| Materials / Supplies | | |
| Equipment / Tools | | |
| Travel & Logistics | | |
| Subcontracting (if any) | | |
| **Subtotal Direct Cost** | | |
| Overheads (verified approved rate only) | | |
| Contingency (verified approved rate only) | | |
| **Total Cost** | | |
| Our Margin (%) | | |
| **Our Quote (₹)** | | |

**RECOMMENDED QUOTE**
Give an exact figure only when verified costs, tax treatment, overhead, contingency and approved margin are supplied. Otherwise write "NOT CALCULABLE FROM SUPPLIED EVIDENCE" and list the inputs required. Never describe an unsupported quote as L1.

**GST ANALYSIS:**
- Applicable GST rate (only if supplied or verified by an authorised tax source):
- HSN/SAC Code (only if supplied or verified):
- Quote inclusive/exclusive of GST:
- Input Tax Credit available:

**EMD REQUIREMENT:**
- EMD Amount: ₹
- Prescribed Mode: copy only the mode stated in the tender; otherwise "Not specified in tender"
- Our Capacity: (check company profile)
- Bank Guarantee Cost: verified bank quotation only; otherwise "Not verified"
- Recommendation:

**WORKING CAPITAL & CASH FLOW:**
Show milestone percentages exactly as stated and verify that they sum to 100%. Produce month-by-month cash flow only when timing and verified costs are supplied; otherwise list the missing inputs.

**FINANCIAL QUALIFICATION DOCUMENTS REQUIRED:**
List only the financial documents explicitly required by this tender.""",
    },
    {
        "id": "bid-pricing",
        "name": "Bid Pricing Analyst AI",
        "prompt": """Produce an evidence-grounded pricing-readiness analysis. Never invent numbers to complete a section.

**TENDER ESTIMATE REALITY CHECK**
- Tender's stated estimated value:
- Our independent cost engineering estimate:
- Gap (positive / negative):
- Verdict: Is the tender estimate realistic, generous, or unviable?

**HISTORICAL L1 PRICING — Comparable Tenders**
| # | Tender | Year | Department | Winning Bidder | L1 Price | Our Note |
You have no award-history database. Do NOT fabricate tenders, bidders or L1 prices.
Write "[ESTIMATE — UNVERIFIED] No verified L1 history available" and state which
portal archive the user must pull it from before this quote can be trusted.

**WIN-ZONE PRICE BAND**
Provide bands only when verified company costs and verified award/competitor evidence are supplied. Otherwise state "NOT CALCULABLE FROM SUPPLIED EVIDENCE":
- Aggressive / Risky L1: ₹
- Recommended Winning L1: ₹
- Safe Profitable Bid: ₹
- L2 / L3 likely band: ₹ to ₹
Justify each figure with calculation logic.

**PRICE JUSTIFICATION NOTE — Draft status**
Draft only from verified cost evidence. If unavailable, provide a checklist of evidence needed rather than fictional market-rate prose.

**CAPITAL REQUIREMENT BREAKDOWN**
- EMD: ₹ (mode required — DD / BG / online)
- Performance Bank Guarantee (PBG): ₹ (rate %, validity period)
- Mobilisation Advance: ₹ (if any, with BG cost)
- Working Capital lock-up for first 90 days: ₹
- Total Capital at Risk: ₹

**SENSITIVITY ANALYSIS**
| Scenario | Margin Impact | Recommended Action |
Use scenarios only when their bases are supplied or label them clearly as user-selectable hypothetical inputs; do not present them as tender facts.

**WIN PROBABILITY AT RECOMMENDED L1**
- Win probability: do NOT state a percentage — you have no historical win/loss data
  to compute one from. Instead describe qualitatively (Strong / Moderate / Weak)
  and list exactly which facts would be needed to quantify it.
- Justification using historical win-loss patterns

**PRICING RED FLAGS**
List any aspects of the tender that make pricing risky or unpredictable (vague scope, missing quantity, ambiguous penalty).""",
    },
    {
        "id": "doc-controller",
        "name": "Document Controller AI",
        "prompt": """Create the complete master submission checklist. Every table must be fully filled. Check every document against our vault status.

**SECTION A — MANDATORY ELIGIBILITY DOCUMENTS**
| # | Document Name | Format Required | Validity | Vault Status | Action Required | Responsible Person | Deadline |
|---|--------------|----------------|---------|-------------|----------------|-------------------|---------|
(Status: ✅ Ready | ⚠️ Expired/Expiring | ❌ Missing | 📋 Create Fresh)
Cover: Registration certificates, GST, PAN, turnover certificate, ITRs, audited accounts, experience certificates, etc.

**SECTION B — TECHNICAL DOCUMENTS**
| # | Document Name | Format Required | Validity | Vault Status | Action Required |
Cover: Work orders, completion certificates, ISO/quality certifications, key personnel CVs, organization chart, technical brochure, etc.

**SECTION C — FINANCIAL BID DOCUMENTS**
| # | Document Name | Format Required | Notes | Status |
Cover: BOQ, price schedule, EMD instrument, declaration forms, etc.

**SECTION D — LEGAL & COMPLIANCE DOCUMENTS**
| # | Document Name | Format Required | Notes | Status |
Cover: Power of Attorney, MoU/JV agreement (if applicable), integrity pact, blacklisting declaration, etc.

**PORTAL SUBMISSION REQUIREMENTS — [Portal Name]**
- File size limits:
- Allowed formats:
- Folder/package structure:
- Separate technical & financial cover requirement:
- DSC requirement:
- Upload sequence:

**INTERNAL DEADLINE CALENDAR**
| Milestone | Date | Tasks | Owner |
|-----------|------|-------|-------|
| D-10 | | | |
| D-7 | | | |
| D-5 | | | |
| D-3 | | | |
| D-1 | | | |
| D-Day | | | |

Calculate every D-N date from the tender deadline and verify that it occurs before submission. If the deadline is absent, write "Not calculable". Never place an internal milestone after the portal deadline.

**TOP 10 DISQUALIFICATION RISKS**
List the 10 most common reasons bids get disqualified on tenders like this, and how to prevent each one.""",
    },
    {
        "id": "admin-hr",
        "name": "Admin / HR AI",
        "prompt": """Assess HR, manpower, and compliance requirements. Complete ALL sections — every table must have real rows.

**KEY PERSONNEL REQUIREMENTS FROM TENDER**
| # | Role / Position | Min Qualification | Min Experience | Certifications Required | Do We Have This Person? |
|---|----------------|-----------------|---------------|----------------------|------------------------|
Match EACH requirement against our actual team from the company profile.

**MANPOWER DEPLOYMENT PLAN**
| Phase | Duration | Personnel Required | Count | Source (Our Team / Hire / Subcontract) |
|-------|---------|------------------|-------|--------------------------------------|

**CVs TO PREPARE**
List every CV we need to include. For each person: name (or "TBD"), role, key qualifications to highlight, projects to mention, format required.

**LABOUR COMPLIANCE CHECKLIST**
List only labour, staffing, safety, PF/ESI or wage requirements explicitly stated in the tender. For statutory applicability not stated in the tender, write "Requires current authorised HR/legal verification" and do not insert thresholds from memory.

**STATUTORY COMPLIANCES DURING EXECUTION**
List all compliances government auditors will verify:
| Compliance | Frequency | Documents to Maintain | Risk if Non-Compliant |

**AUDIT-READINESS ASSESSMENT**
Assess only tender-stated records against supplied HR evidence. Do not manufacture generic audit requirements or claim missing records prove non-compliance.

**INTERNAL HR ACTIONS REQUIRED**
| Action | Deadline | Owner | Priority |
List everything HR needs to do before bid submission and during execution.""",
    },
    {
        "id": "qa-reviewer",
        "name": "Quality Assurance (QA) Reviewer AI",
        "prompt": """Run the final zero-defect QA review on the entire bid package. This is the LAST firewall before submission — be ruthless and exhaustive.

**ELIGIBILITY VERIFICATION (10 items)**
Re-verify each eligibility criterion against our actual credentials. Mark ✅ ⚠️ ❌ for each. Flag ANY item that could risk technical disqualification.

**DOCUMENT INTEGRITY CHECKLIST (15 items)**
| # | Check Point | Status | Risk if Missed |
Check an item only when the tender requires it. Generic checks absent from the tender must be marked "Not specified in tender", not failed.

**FINANCIAL BID CONSISTENCY (10 items)**
- BOQ quantities match scope: ✅/❌
- Unit rates × Quantity = Line total: ✅/❌
- Line totals → Subtotal → Grand Total tally: ✅/❌
- GST treatment correct (inclusive/exclusive as required): ✅/❌
- EMD amount and mode match tender: ✅/❌
- Currency stated correctly: ✅/❌
- Number-in-words matches numerical figure: ✅/❌
- Validity of bid (180 days etc) confirmed: ✅/❌
- Price justification note attached: ✅/❌
- Discount / rebate clause clearly stated: ✅/❌

**TECHNICAL BID CONSISTENCY (10 items)**
Cover: compliance matrix completed for every requirement, methodology covers full scope, CVs match deployment plan, past project references included, technical brochures attached, OEM authorisations where required, standards quoted (IS / BIS / ISO codes), make/model specifications match, deviation statement (NIL or listed), undertaking letters signed.

**FORMAT & PORTAL COMPLIANCE (10 items)**
Check only portal rules explicitly supplied by the tender. Never invent file sizes, formats, DSC, encryption, naming, upload sequence, hash, browser or deadline-buffer requirements.

**TENDER-CLAUSE-TO-BID MAP**
List every numbered clause in the tender → where it is addressed in our bid → status (Compliant / Partial / Non-compliant). At least 15 rows.

**CRITICAL ISSUES FOUND**
| # | Issue | Severity | Location in Bid | Fix Required Before Submission |

**MINOR ISSUES (nice-to-fix)**
Cosmetic / non-blocking improvements.

**FINAL VERDICT: 🟢 GO FOR SUBMISSION / 🟡 FIX MINOR ISSUES FIRST / 🔴 DO NOT SUBMIT**
With one-line justification.""",
    },
]

FINAL_PROMPT = """You are preparing an AI-generated decision-support report for a human Managing Director. You have reviewed the analysis from the AI team. Write a careful, evidence-grounded briefing. Do not impersonate the Managing Director or claim that the MD Office prepared, approved, or signed this report.

**AI-GENERATED TENDER ANALYSIS — DRAFT FOR HUMAN REVIEW**
Generated: {current_date} | Prepared by: Unique Type Team

**EVIDENCE AUDIT — REQUIRED BEFORE THE SUMMARY**
- Treat the tender text, company profiles, document-vault metadata and supplied past-bid records as the only factual evidence.
- Discard any claim in a specialist report that cannot be traced to that supplied evidence.
- Never copy an invented certification number, turnover, project, employee, competitor, price, deadline, compliance status, approval or document status into this briefing.
- When evidence is absent or conflicting, write "NOT VERIFIED — human review required" and identify the missing source.
- Test profiles whose names begin with "TEST —" contain demonstration data only. Label all conclusions about them "TEST DATA — NOT FOR SUBMISSION".
- The deterministic metadata block is authoritative for title, reference, value, EMD and dates when its cited excerpt is unambiguous. Never confuse EMD with contract value.
- Reject specialist prices, standards, credentials, portal rules and legal conclusions that do not appear in the tender/profile evidence, even when they are labelled estimates.
- Recompute every arithmetic result and date offset. Payment milestones must total 100%, and every internal deadline must precede the portal deadline.
- Do not output template tokens such as [DEPARTMENT], [X]/100, TBD, or TO BE FILLED. Use "NOT VERIFIED — human review required" and identify the missing evidence instead.

**EXECUTIVE SUMMARY**
Write 4–5 sentences covering: what this tender is, which department, what value, why it matters to us, and your overall stance.

**FINAL RECOMMENDED QUOTE**
Give an exact figure only when the tender quantities and verified company cost inputs support it. Otherwise write "NOT CALCULABLE FROM SUPPLIED EVIDENCE" and list the cost inputs required. Never turn an agent estimate into a verified quote.

**ASSESSMENT CONFIDENCE**
Use High / Medium / Low and explain the evidence coverage. Do not invent numerical probabilities.
Break this down:
- Technical Eligibility: [Verified / Partially verified / Not verified]
- Financial Competitiveness: [Verified / Partially verified / Not verified]
- Document Readiness: [Verified / Partially verified / Not verified]
- Legal Risk Level: [rating]
- Overall Evidence Confidence: [High / Medium / Low]

**GO / NO-GO DECISION: [GO ✅ / NO-GO ❌ / CONDITIONAL GO ⚠️]**
Write 4–5 sentences justifying your decision. Reference specific findings from the team analysis — eligibility gaps, risks, our strengths, competition. Be decisive.
Give exactly one reconciled decision for the entire report. Missing company evidence is unverified, not proof that a criterion is failed. If specialist verdicts conflict, resolve the conflict from primary evidence and explicitly discard unsupported verdicts.

**CONDITIONS (if Conditional Go):**
List each condition that must be met before submission.

**KEY STRENGTHS WE SHOULD HIGHLIGHT**
List 5 specific strengths from our company profile that give us an advantage in this tender.

**CRITICAL RISKS TO MANAGE**
| Risk | Severity | Mitigation |
List top 5 risks with severity (High/Medium/Low) and specific mitigation steps.

**CRITICAL ACTION ITEMS — Next 72 Hours**
| # | Action Item | Department / Owner | Deadline | Status |
|---|------------|------------------|---------|--------|
List only specific actions required by verified gaps. Do not create filler actions for departments that have no evidenced task.
Use a calendar date only when it can be calculated from the tender deadline; otherwise use "Before submission — owner to schedule". Never invent a 72-hour date.

**SUBMISSION READINESS DASHBOARD:**
| Department | Evidence Status | What's Pending |
|-----------|----------|---------------|
| Bid Management | Verified / Partial / Not verified | |
| Legal / Compliance | Verified / Partial / Not verified | |
| Technical Proposal | Verified / Partial / Not verified | |
| Financial Bid | Verified / Partial / Not verified | |
| Document Vault | Verified / Partial / Not verified | |
| HR / Manpower | Verified / Partial / Not verified | |
| **OVERALL** | **High / Medium / Low evidence coverage** | |

**RECOMMENDED HUMAN REVIEW**
List the decisions and claims that a responsible person must verify before submission.

Never invent a value to make a section look complete. An explicit unknown is a correct and complete result."""


def get_vault_context(db: Session, user_id: int | None = None) -> str:
    if user_id is None:
        return ""
    docs = db.query(Document).filter(Document.user_id == user_id).all()
    if not docs:
        return ""
    today = date.today()
    lines = ["\n\n=== DOCUMENT VAULT STATUS ==="]
    for d in docs:
        if d.expiry_date:
            delta = (d.expiry_date - today).days
            if delta < 0:
                status = f"❌ EXPIRED {abs(delta)}d ago"
            elif delta <= 30:
                status = f"⚠️ EXPIRING in {delta}d"
            else:
                status = f"✅ Valid ({delta}d left)"
        else:
            status = "✅ No expiry"
        lines.append(f"- {d.name} [{d.category}] — {status}")
    lines.append("=== END VAULT ===")
    return "\n".join(lines)


async def run_agent_async(system_prompt: str, task_prompt: str, tender_text: str, max_tokens: int | None = None, agent_id: str | None = None) -> str:
    user_msg = (
        f"TENDER DOCUMENT:\n\n{tender_text}\n\n---\n\n"
        f"IMPORTANT: Complete every section, but use only supplied evidence. "
        f"Never invent a value to fill a table. Use NOT VERIFIED when evidence is absent.\n\n"
        f"TASK BRIEF:\n\n{task_prompt}"
    )
    return await chat_async(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=max_tokens,
        agent_id=agent_id,
    )


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def stream_pipeline_job(job_id: str, user_id: int, only_ids: set[str] | None = None):
    """Run unfinished/failed specialists for an existing durable job."""
    loaded = load_job(job_id, user_id, "pipeline")
    if not loaded:
        yield sse({"type": "error", "message": "Analysis job not found."})
        return
    job, context, saved_steps = loaded
    text = job.tender_text
    company_ctx = context.get("company_ctx", "")
    vault_ctx = context.get("vault_ctx", "")
    past_bids_ctx = context.get("past_bids_ctx", "")
    grounding = context.get("grounding", GROUNDING_RULES)
    profile_pct = context.get("profile_pct", 100)
    profile_missing = context.get("profile_missing", [])
    canonical_facts = context.get("canonical_facts", {})
    from app.agents.registry import AGENT_SYSTEM_PROMPTS

    def system_prompt_for(agent: dict) -> str:
        if agent["id"] == TENDER_BRIEF_ID:
            # The brief describes the tender only; company data would invite
            # the model to mix our credentials into the tender's facts.
            return AGENT_SYSTEM_PROMPTS[TENDER_BRIEF_ID] + grounding
        enriched = AGENT_SYSTEM_PROMPTS.get(agent["id"], "") + company_ctx + vault_ctx
        if agent["id"] == "technical-expert" and past_bids_ctx:
            enriched += past_bids_ctx
        return enriched + grounding

    selected = []
    for agent in PIPELINE_AGENTS:
        step = saved_steps.get(agent["id"])
        if only_ids is not None:
            if agent["id"] in only_ids:
                selected.append(agent)
        elif not step or step.status != "done":
            selected.append(agent)

    yield sse({"type": "job_created", "job_id": job_id, "resumed": bool(saved_steps)})
    if profile_pct < MIN_PROFILE_PERCENT:
        yield sse({
            "type": "warning", "code": "incomplete_profile", "profile_percent": profile_pct,
            "missing": profile_missing,
            "message": user_facing_profile_warning(profile_pct, profile_missing),
        })

    provider_slots = asyncio.Semaphore(settings.pipeline_concurrency)

    async def run_one(agent: dict) -> str:
        async with provider_slots:
            brief_tokens = TENDER_BRIEF_MAX_TOKENS if agent["id"] == TENDER_BRIEF_ID else None
            return await run_with_timeout_retry(
                lambda: run_agent_async(
                    system_prompt=system_prompt_for(agent), task_prompt=agent["prompt"],
                    tender_text=text, agent_id=agent["id"], max_tokens=brief_tokens,
                ),
                job_id, agent["id"],
            )

    tasks = {asyncio.create_task(run_one(agent)): agent for agent in selected}
    for agent in selected:
        yield sse({"type": "agent_start", "agent_id": agent["id"], "agent_name": agent["name"]})

    pending = set(tasks)
    try:
        while pending:
            done, pending = await asyncio.wait(pending, timeout=10, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                yield ": keepalive\n\n"
                continue
            for task in done:
                agent = tasks[task]
                try:
                    content = task.result() or ""
                    update_step(job_id, agent["id"], "done", content=content, error=None)
                    yield sse({"type": "agent_done", "agent_id": agent["id"], "content": content})
                except Exception as exc:
                    print(f"[pipeline] {agent['id']} failed: {exc}")
                    message = user_facing_error(exc)
                    update_step(job_id, agent["id"], "error", error=message)
                    yield sse({"type": "agent_error", "agent_id": agent["id"], "message": message})
    finally:
        unfinished_tasks = [task for task in tasks if not task.done()]
        for task in unfinished_tasks:
            task.cancel()
        if unfinished_tasks:
            await asyncio.gather(*unfinished_tasks, return_exceptions=True)

    refreshed = load_job(job_id, user_id, "pipeline")
    assert refreshed is not None
    _, _, steps = refreshed
    pipeline_ids = {agent["id"] for agent in PIPELINE_AGENTS}
    failures = [s for step_id, s in steps.items() if step_id in pipeline_ids and s.status != "done"]
    if failures:
        finish_job(job_id, "partial", error=f"{len(failures)} specialist(s) require retry")
        yield sse({"type": "job_paused", "job_id": job_id, "failed_agent_ids": [s.step_id for s in failures]})
        yield "data: [DONE]\n\n"
        return

    results = {step_id: step.content for step_id, step in steps.items()}
    yield sse({"type": "final_start"})
    final_tender, combined = condense_for_final(text, [
        (a["name"].upper(), results.get(a["id"], "N/A")) for a in PIPELINE_AGENTS
        # The brief restates the tender itself, which md-final already receives.
        if a["id"] != TENDER_BRIEF_ID
    ])
    try:
        final = await run_with_timeout_retry(
            lambda: run_agent_async(
                system_prompt=(
                    "You are an AI decision-support analyst for Indian government tenders. "
                    "You are not the Managing Director and may not imply human approval."
                    + company_ctx + vault_ctx + GROUNDING_RULES
                ),
                task_prompt=FINAL_PROMPT.format(current_date=date.today().isoformat()),
                tender_text=f"TENDER:\n{final_tender}\n\nTEAM ANALYSIS:\n{combined}", agent_id="md-final",
            ),
            job_id, "md-final",
        )
        final = sanitize_final_report(
            final or "", text, canonical_facts, bid_manager_report=results.get("bid-manager"),
        )
        quality_issues = audit_final_report(final, text, canonical_facts)
        if quality_issues:
            # Give the reasoning model one bounded opportunity to repair the
            # deterministic failures before the report is released.
            repair_prompt = FINAL_PROMPT.format(current_date=date.today().isoformat()) + f"""

**QUALITY-GATE REWRITE REQUIRED**
The first draft failed deterministic review for these reasons:
{correction_brief(quality_issues)}

Rewrite the entire final report. Correct every issue above using primary tender/profile evidence only. Do not discuss the failed draft or the rewrite process.
"""
            try:
                repaired = await run_with_timeout_retry(
                    lambda: run_agent_async(
                        system_prompt=(
                            "You are an AI decision-support analyst for Indian government tenders. "
                            "You are not the Managing Director and may not imply human approval."
                            + company_ctx + vault_ctx + GROUNDING_RULES
                        ),
                        task_prompt=repair_prompt,
                        tender_text=f"TENDER:\n{final_tender}\n\nTEAM ANALYSIS:\n{combined}",
                        agent_id="md-final",
                    ),
                    job_id, "md-final",
                )
                if repaired:
                    final = sanitize_final_report(
                        repaired, text, canonical_facts, bid_manager_report=results.get("bid-manager"),
                    )
                    quality_issues = audit_final_report(final, text, canonical_facts)
            except Exception:
                # Keep the first draft as a blocked human-review artifact if
                # the correction provider is unavailable or times out.
                pass

        update_step(job_id, "md-final", "done", content=final)
        issue_payload = [issue.to_dict() for issue in quality_issues]
        if quality_issues:
            final = blocked_report(quality_issues)
            update_step(job_id, "md-final", "done", content=final)
            finish_job(job_id, "review_required", final_content=final, error=json.dumps(issue_payload))
        else:
            finish_job(job_id, "completed", final_content=final, error=None)
        results["final"] = final
        yield sse({"type": "quality_gate", "passed": not quality_issues, "issues": issue_payload, "job_id": job_id})
        yield sse({"type": "final_done", "content": final, "all_results": results, "job_id": job_id})
    except Exception as exc:
        print(f"[pipeline] md-final failed: {exc}")
        message = user_facing_error(exc)
        update_step(job_id, "md-final", "error", error=message)
        finish_job(job_id, "partial", error=message)
        yield sse({"type": "final_error", "message": message, "job_id": job_id})
    yield "data: [DONE]\n\n"


async def _run_pipeline_background(job_id: str, user_id: int, only_ids: set[str] | None = None) -> None:
    """Consume the worker independently of the requesting browser connection."""
    try:
        async for _ in stream_pipeline_job(job_id, user_id, only_ids):
            pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        finish_job(job_id, "partial", error=str(exc))
    finally:
        _PIPELINE_TASKS.pop(job_id, None)


def _ensure_pipeline_running(job_id: str, user_id: int, only_ids: set[str] | None = None) -> None:
    task = _PIPELINE_TASKS.get(job_id)
    if task and not task.done():
        return
    finish_job(job_id, "running", error=None)
    _PIPELINE_TASKS[job_id] = asyncio.create_task(
        _run_pipeline_background(job_id, user_id, only_ids),
        name=f"pipeline-{job_id}",
    )


async def watch_pipeline_job(job_id: str, user_id: int):
    """Translate persisted state into SSE; safe to disconnect and reconnect."""
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
                    if payload["status"] == "review_required":
                        try:
                            issues = json.loads(payload.get("error") or "[]")
                        except json.JSONDecodeError:
                            issues = [{"severity": "critical", "message": "The report requires human review."}]
                        yield sse({"type": "quality_gate", "passed": False, "issues": issues, "job_id": job_id})
                    elif payload["status"] == "completed":
                        yield sse({"type": "quality_gate", "passed": True, "issues": [], "job_id": job_id})
                    yield sse({"type": "final_done", "content": step["content"], "all_results": results, "job_id": job_id})
                elif step["status"] == "error":
                    yield sse({"type": "final_error", "message": step["error"] or "Final briefing failed", "job_id": job_id})
            elif step["status"] in {"waiting", "running"}:
                yield sse({"type": "agent_start", "agent_id": step["id"], "agent_name": step["name"]})
            elif step["status"] == "done":
                yield sse({"type": "agent_done", "agent_id": step["id"], "content": step["content"]})
            elif step["status"] == "error":
                yield sse({"type": "agent_error", "agent_id": step["id"], "message": step["error"] or "Agent failed"})
        if payload["status"] in {"completed", "review_required", "partial", "failed", "cancelled"}:
            if payload["status"] == "cancelled":
                yield sse({"type": "job_cancelled", "job_id": job_id})
                yield "data: [DONE]\n\n"
                return
            if payload["status"] not in {"completed", "review_required"}:
                failed = [s["id"] for s in payload["steps"] if s["status"] == "error"]
                yield sse({"type": "job_paused", "job_id": job_id, "failed_agent_ids": failed})
            yield "data: [DONE]\n\n"
            return
        yield ": keepalive\n\n"
        await asyncio.sleep(1)


@router.post("/tender/analyze/{job_id}/cancel")
async def cancel_tender_analysis(job_id: str, user: User = Depends(get_current_user)):
    if not cancel_job(job_id, user.id, "pipeline"):
        raise HTTPException(status_code=404, detail="Analysis job not found")
    task = _PIPELINE_TASKS.get(job_id)
    if task and not task.done():
        task.cancel()
    return {"status": "cancelled", "job_id": job_id}


@router.post("/tender/analyze/{job_id}/resume")
async def resume_tender_analysis(job_id: str, user: User = Depends(get_current_user)):
    if not load_job(job_id, user.id, "pipeline"):
        raise HTTPException(status_code=404, detail="Analysis job not found")
    _ensure_pipeline_running(job_id, user.id)
    return StreamingResponse(watch_pipeline_job(job_id, user.id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/tender/analyze/{job_id}/retry/{agent_id}")
async def retry_tender_agent(job_id: str, agent_id: str, user: User = Depends(get_current_user)):
    valid_ids = {a["id"] for a in PIPELINE_AGENTS} | {"md-final"}
    if agent_id not in valid_ids:
        raise HTTPException(status_code=404, detail="Unknown specialist")
    loaded = load_job(job_id, user.id, "pipeline")
    if not loaded:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    update_step(job_id, agent_id, "waiting", error=None)
    _ensure_pipeline_running(job_id, user.id, {agent_id})
    return StreamingResponse(watch_pipeline_job(job_id, user.id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def start_pipeline_job(db: Session, user: User, raw_text: str, *, evidence=None,
                       company_profile_id: int | None = None, compare_all_companies: bool = False) -> str:
    """Build the AI input, create the durable job and start it. Returns the job id."""
    evidence = extract_tender_evidence(raw_text) if evidence is None else evidence
    evidence_block = format_evidence_block(evidence)
    canonical_facts, evidence_conflicts = serialize_canonical_facts(evidence)
    # Put high-value cited facts first. Local-model context limits generally
    # preserve the prompt prefix even when a very long annexure is truncated.
    # Oversized tenders are condensed to the passages a bid analysis needs
    # instead of letting the model silently drop everything past its context.
    text = build_model_input(raw_text, evidence_block)
    company_ctx = get_profile_context(db, user.id, company_profile_id, compare_all_companies)
    vault_ctx = get_vault_context(db, user.id)
    past_bids_ctx = get_past_bids_context(db, user.id)
    # These agents are shipped to customers bidding real money — never let them
    # invent market data or assert credentials the customer has not supplied.
    profile_pct, profile_missing = profile_completeness(db, user.id, company_profile_id)
    grounding = GROUNDING_RULES
    if profile_pct < MIN_PROFILE_PERCENT:
        grounding += thin_profile_warning(profile_pct, profile_missing)
    job_id = create_job(
        user.id, "pipeline", text,
        {
            "company_ctx": company_ctx, "vault_ctx": vault_ctx, "past_bids_ctx": past_bids_ctx,
            "grounding": grounding, "profile_pct": profile_pct, "profile_missing": profile_missing,
            "canonical_facts": canonical_facts, "evidence_conflicts": evidence_conflicts,
        },
        PIPELINE_AGENTS + [{"id": "md-final", "name": "Final Decision Briefing"}],
    )
    _ensure_pipeline_running(job_id, user.id)
    return job_id


async def _announce_tender(tender_id: int, stream):
    """Tell the browser which history entry this run belongs to, then relay the job stream."""
    yield sse({"type": "tender", "tender_id": tender_id})
    async for chunk in stream:
        yield chunk


@router.post("/tender/analyze")
async def analyze_tender(
    tender_text: str = Form(""),
    company_profile_id: int | None = Form(None),
    compare_all_companies: bool = Form(False),
    file: UploadFile | None = File(None),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Plan limit check — block before doing any work
    ok, info = check_usage(user, db, "pipeline")
    if not ok:
        raise HTTPException(status_code=402, detail=info)

    uploads = list(files)
    if file is not None:
        uploads.insert(0, file)  # backwards compatibility with older clients
    text_parts = [f"--- PASTED TENDER TEXT ---\n{tender_text.strip()}"] if tender_text.strip() else []
    docs, extraction_errors = await read_uploads(uploads)
    text_parts.extend(source_block(doc) for doc in docs)
    raw_text = "\n\n".join(text_parts).strip()
    extract_error = " ".join(extraction_errors) if extraction_errors else None

    if extraction_errors or not raw_text:
        message = extract_error or "No tender content provided."

        async def err():
            yield sse({"type": "error", "message": message})
        return StreamingResponse(err(), media_type="text/event-stream")

    # Record this run against the user's quota
    record_usage(db, user.id, "pipeline")

    if company_profile_id is not None:
        owned = db.query(CompanyProfile).filter(
            CompanyProfile.id == company_profile_id, CompanyProfile.user_id == user.id
        ).first()
        if not owned:
            async def company_err():
                yield sse({"type": "error", "message": "Selected company profile was not found."})
            return StreamingResponse(company_err(), media_type="text/event-stream")

    evidence = extract_tender_evidence(raw_text)
    job_id = start_pipeline_job(db, user, raw_text, evidence=evidence, company_profile_id=company_profile_id,
                                compare_all_companies=compare_all_companies)
    stream = watch_pipeline_job(job_id, user.id)
    try:
        tender, _ = await asyncio.to_thread(
            tender_history.start_run, db, user.id,
            tender=None, kind="pipeline", job_id=job_id, docs=docs, pasted_text=tender_text,
            note="", name_hint=tender_history.tender_name(evidence, docs),
        )
        stream = _announce_tender(tender.id, stream)
    except Exception as exc:  # history is a convenience; it must never block the analysis
        db.rollback()
        print(f"[history] could not record tender for job {job_id}: {exc}")
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
