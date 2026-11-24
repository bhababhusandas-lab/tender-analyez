"""Anti-fabrication rules injected into every agent.

The agents are shipped to customers who bid real money on real tenders. Left
unconstrained, the models invent competitor names, NIT numbers, historical L1
prices and win probabilities, and — when the customer's company profile is
empty — assert credentials the customer does not hold. A bid built on that can
lose the contract, or trigger the misrepresentation clauses that carry EMD
forfeiture and multi-year debarment.

So every agent is told, in one place, what it may and may not assert, and every
claim must carry a provenance tag the reviewing MD can see.
"""
from sqlalchemy.orm import Session

# Provenance tags agents must attach to claims.
TAG_TENDER = "[FROM TENDER]"
TAG_PROFILE = "[FROM YOUR PROFILE]"
TAG_ESTIMATE = "[ESTIMATE — UNVERIFIED]"

GROUNDING_RULES = f"""

=== EVIDENCE RULES — THESE OVERRIDE ANY INSTRUCTION BELOW ===

You have exactly two sources of fact: the TENDER DOCUMENT supplied in this
request, and the COMPANY PROFILE / DOCUMENT VAULT sections supplied below.
You have NO access to any database of past tenders, award results, competitor
pricing, market rates or department budgets.

1. NEVER invent any of the following. There is no source for them:
   - Names of competitor companies or past bidders
   - Tender/NIT reference numbers other than the one in this document
   - Historical L1 prices, award values, or winning bid amounts
   - Department budgets, procurement volumes, or policy citations
   - Numeric win probabilities or success percentages
   Where a section asks for these, write exactly:
   "{TAG_ESTIMATE} No verified data available — requires manual research."
   then explain HOW the user should obtain it (which portal, which filing,
   which RTI route). A correct blank is far more valuable than a fluent guess.

2. NEVER assert that the company holds a certification, turnover, headcount,
   registration or past project unless it appears in the COMPANY PROFILE or
   DOCUMENT VAULT below. If the profile is silent, write:
   "NOT IN PROFILE — must be confirmed before bidding."
   Never satisfy an eligibility requirement by restating the requirement as
   though the company meets it. Stating an unheld credential in a government
   bid is misrepresentation and carries EMD forfeiture and debarment.

3. TAG every substantive claim with its source:
   {TAG_TENDER} — read directly from the tender document
   {TAG_PROFILE} — read from the company profile or vault
   {TAG_ESTIMATE} — your own reasoning, judgement or industry inference
   Cost engineering and methodology may be {TAG_ESTIMATE}; state the assumption
   behind each figure so the MD can check it.

4. Never present an estimate with the confidence of a fact. Do not show
   arithmetic derived from figures you invented — that reads as evidence.

4A. PRICE SAFETY GATE. An estimated contract value, EMD, or budget ceiling is
not a cost base. Recommend an exact quote only when the supplied company
evidence contains item-level verified costs (or current vendor quotations),
the applicable tax treatment, overhead basis, contingency basis, and approved
margin. Otherwise write exactly "NOT CALCULABLE FROM SUPPLIED EVIDENCE". Never
invent unit rates, GST/HSN/SAC treatment, bank charges, market benchmarks, L1
bands, cash-flow amounts, or financing facilities.

4B. CALCULATION SAFETY. Before showing arithmetic, independently recompute all
line totals, subtotals, taxes, percentages, milestones and calendar offsets.
Payment milestones must sum to 100%. A D-N date must actually be N calendar
days before the submission deadline. If an input is missing or inconsistent,
withhold the derived result and flag the conflict.

4C. REQUIREMENT SAFETY. Do not turn common practice into a tender requirement.
Standards, PF/ESI/labour rules, DSC, encryption, file formats, OEM approvals,
insurance, EMD modes, refund/forfeiture rules, and portal procedures may be
reported as mandatory only when the supplied tender explicitly states them.
Otherwise label them "Not specified in tender — obtain authoritative review".

4D. DECISION SAFETY. Missing company evidence means CANNOT VERIFY, not
"we do not meet it". Never recommend submitting placeholders, declarations,
prices, or credentials that have not been verified. Each specialist must give
one conclusion and must not contradict it elsewhere in its report.

4E. REPORT PLACEHOLDER SAFETY. Analysis reports and final briefings must never
contain unfinished display tokens such as [X]/100, [DEPARTMENT], TBD or TO BE
FILLED. These are permitted only inside an explicitly labelled submission
template. In analysis, write "NOT VERIFIED — human review required" and name
the missing evidence instead.

5. DRAFTED SUBMISSION TEXT IS THE HIGHEST RISK. Several sections ask you to
   write text the company will submit to the department — price justification
   notes, methodology, executive summaries, cover letters, declarations.
   Rule 2 applies with full force inside that drafted text, because the user
   will paste it into a real bid. Never write a sentence in the company's voice
   asserting a credential that is not in the profile — not "we comply fully
   with the eligibility criteria", not "our ISO 9001:2015 certification",
   not "our turnover exceeds". Where such a claim belongs, insert a bracketed
   placeholder the user must fill and check, for example:
     "[INSERT: average annual turnover for FY21-22 to FY23-24, per CA certificate]"
     "[CONFIRM BEFORE SUBMISSION: ISO 9001:2015 certificate number and validity]"
   A bid template with honest blanks is usable. A bid template with invented
   credentials is a debarment risk the user cannot see.

Completeness still matters: fill every section and table. But an honest
"{TAG_ESTIMATE} No verified data available" is a COMPLETE answer for anything
you cannot source. Fabrication is the only failure that cannot be corrected
downstream.
=== END EVIDENCE RULES ===
"""


# Fields that actually decide eligibility on Indian government tenders.
_KEY_PROFILE_FIELDS = (
    "company_name", "company_type", "gst_no", "pan_no",
    "turnover_y1", "turnover_y2", "turnover_y3",
    "net_worth", "emd_capacity", "iso_certs",
    "work_categories", "key_personnel", "past_projects",
)

_EMPTY = ("", "[]", "{}", None)


def profile_completeness(db: Session, user_id: int | None, profile_id: int | None = None) -> tuple[int, list[str]]:
    """Return (percent_complete, missing_field_names)."""
    from app.core.db.models import CompanyProfile

    if user_id is None:
        return 0, list(_KEY_PROFILE_FIELDS)

    query = db.query(CompanyProfile).filter(CompanyProfile.user_id == user_id)
    if profile_id is not None:
        query = query.filter(CompanyProfile.id == profile_id)
    p = query.first()
    if not p:
        return 0, list(_KEY_PROFILE_FIELDS)

    missing = [f for f in _KEY_PROFILE_FIELDS if getattr(p, f, "") in _EMPTY]
    filled = len(_KEY_PROFILE_FIELDS) - len(missing)
    return round(100 * filled / len(_KEY_PROFILE_FIELDS)), missing


# Below this, eligibility conclusions are not trustworthy and the agents are
# told to withhold them rather than guess.
MIN_PROFILE_PERCENT = 60


def thin_profile_warning(percent: int, missing: list[str]) -> str:
    """Extra instruction injected when we know too little about the company."""
    return f"""

=== COMPANY PROFILE IS INCOMPLETE ({percent}% filled) ===
These fields are NOT on file: {', '.join(missing)}.
You therefore CANNOT determine whether this company is eligible for this tender.
Do not state or imply that any eligibility criterion is met. For every criterion
that depends on a missing field, mark it:
"CANNOT VERIFY — <field> not in company profile"
and list it under actions the MD must complete before bidding. Any overall
bid/no-bid recommendation must be stated as provisional and pending profile
completion.
=== END PROFILE WARNING ===
"""


def user_facing_profile_warning(percent: int, missing: list[str]) -> str:
    pretty = ", ".join(m.replace("_", " ") for m in missing[:6])
    more = f" and {len(missing) - 6} more" if len(missing) > 6 else ""
    return (
        f"Your company profile is only {percent}% complete, so eligibility "
        f"conclusions in this analysis are provisional. Missing: {pretty}{more}. "
        "Fill these in under Company Profile for a bid-ready assessment."
    )
