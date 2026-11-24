from app.core.analysis_quality import (
    audit_final_report,
    blocked_report,
    remove_unsupported_requirement_claims,
    sanitize_final_report,
)
from app.core.tender_evidence import Evidence, canonical_fact_record, serialize_canonical_facts


def _facts():
    evidence = [
        Evidence("Tender Title", "Citizen Service Kiosks", "sample.pdf", "1", "Tender Title: Citizen Service Kiosks"),
        Evidence("EMD Amount", "Rs. 96,000", "sample.pdf", "2", "EMD Amount: Rs. 96,000"),
    ]
    return serialize_canonical_facts(evidence)[0]


def test_canonical_fact_record_rejects_conflicting_candidates():
    evidence = [
        Evidence("EMD Amount", "Rs. 10,000", "a.pdf", "1", "EMD: Rs. 10,000"),
        Evidence("EMD Amount", "Rs. 12,000", "b.pdf", "2", "EMD: Rs. 12,000"),
    ]
    facts, conflicts = canonical_fact_record(evidence)
    assert "EMD Amount" not in facts
    assert len(conflicts["EMD Amount"]) == 2


def test_quality_gate_accepts_one_grounded_decision_and_withheld_quote():
    final = """
FINAL RECOMMENDED QUOTE
NOT CALCULABLE FROM SUPPLIED EVIDENCE

GO / NO-GO DECISION: CONDITIONAL GO
Proceed only after the stated evidence is verified.
"""
    assert audit_final_report(final, "Tender Title: Citizen Service Kiosks\nEMD: Rs. 96,000", _facts()) == []


def test_quality_gate_detects_placeholder_and_canonical_emd_omission():
    final = """
FINAL RECOMMENDED QUOTE
NOT CALCULABLE FROM SUPPLIED EVIDENCE
GO / NO-GO DECISION: GO
Owner: [DEPARTMENT]
EMD Amount: Not Specified
"""
    codes = {issue.code for issue in audit_final_report(final, "EMD: Rs. 96,000", _facts())}
    assert "unfinished_placeholder" in codes
    assert "canonical_fact_omitted" in codes


def test_quality_gate_detects_conflicting_decisions():
    final = """
FINAL RECOMMENDED QUOTE
NOT CALCULABLE FROM SUPPLIED EVIDENCE
GO / NO-GO DECISION: GO
FINAL VERDICT: NO-GO
"""
    codes = {issue.code for issue in audit_final_report(final, "Tender body", {})}
    assert "conflicting_final_decisions" in codes


def test_quality_gate_rejects_unsupported_requirement_and_quote():
    final = """
FINAL RECOMMENDED QUOTE
Rs. 14,49,000
ASSESSMENT CONFIDENCE
Medium
GO / NO-GO DECISION: CONDITIONAL GO
ISO 27001 certificate is mandatory and pending.
"""
    codes = {issue.code for issue in audit_final_report(final, "Tender has no certification clause.", {})}
    assert "unsupported_requirement" in codes
    assert "unsafe_quote" in codes


def test_quality_gate_allows_explicitly_unsupported_requirement_mentions():
    final = """
FINAL RECOMMENDED QUOTE
NOT CALCULABLE FROM SUPPLIED EVIDENCE
GO / NO-GO DECISION: CONDITIONAL GO
- Digital signature certificate: not specified in the tender; verify whether it is required.
- Encryption: no supplied tender evidence; do not treat it as mandatory.
- Portal upload sequence: tender is silent; clarify whether a sequence applies.
- CVs: not required by the supplied tender evidence; do not add this requirement.
"""
    issues = audit_final_report(final, "Tender body without these clauses.", {})
    assert not [issue for issue in issues if issue.code == "unsupported_requirement"]


def test_quality_gate_rejects_affirmative_unsupported_requirements():
    final = """
FINAL RECOMMENDED QUOTE
NOT CALCULABLE FROM SUPPLIED EVIDENCE
GO / NO-GO DECISION: CONDITIONAL GO
- Obtain a digital signature certificate before submission.
- Encrypt every portal upload.
- Follow the mandatory upload sequence.
- Submit CVs for all proposed staff.
"""
    issues = audit_final_report(final, "Tender body without these clauses.", {})
    messages = [issue.message for issue in issues if issue.code == "unsupported_requirement"]
    assert len(messages) == 4


def test_unsupported_requirement_cleanup_removes_claims_but_keeps_safe_uncertainty():
    final = """GO / NO-GO DECISION: CONDITIONAL GO
Technical Bid Incomplete: CVs and brochures are missing.
DSC is not specified in the tender; verify whether it is required.
Evidence-backed implementation plan remains valid.
"""
    cleaned = remove_unsupported_requirement_claims(final, "Tender body without those requirements.")
    assert "CVs and brochures are missing" not in cleaned
    assert "DSC is not specified" in cleaned
    assert "implementation plan remains valid" in cleaned


def test_final_sanitizer_removes_template_placeholder_line_without_guessing():
    final = """GO / NO-GO DECISION: CONDITIONAL GO
Responsible department: [Department to be confirmed]
Evidence-backed conclusion remains valid.
"""
    cleaned = sanitize_final_report(final, "Tender body")
    assert "[Department" not in cleaned
    assert "Evidence-backed conclusion remains valid" in cleaned
    assert audit_final_report(cleaned, "Tender body", {}) == []


def test_quality_gate_detects_canonical_money_conflict():
    final = """
FINAL RECOMMENDED QUOTE
NOT CALCULABLE FROM SUPPLIED EVIDENCE
GO / NO-GO DECISION: CONDITIONAL GO
EMD Amount: Rs. 48,00,000
"""
    codes = {issue.code for issue in audit_final_report(final, "EMD: Rs. 96,000", _facts())}
    assert "canonical_amount_conflict" in codes


def test_quality_gate_rejects_estimated_value_of_phrase_without_evidence():
    final = """
FINAL RECOMMENDED QUOTE
NOT CALCULABLE FROM SUPPLIED EVIDENCE
GO / NO-GO DECISION: NO-GO
CONDITIONS (if Conditional Go): None
The tender has an estimated value of ₹1.2 crore.
"""
    codes = {issue.code for issue in audit_final_report(final, "No contract value stated.", {})}
    assert "unsupported_contract_value" in codes


def test_failed_quality_gate_releases_only_safe_blocked_report():
    issues = audit_final_report(
        "FINAL RECOMMENDED QUOTE\nRs. 14,49,000\nGO / NO-GO DECISION: GO",
        "No verified costs were supplied.",
        {},
    )
    safe = blocked_report(issues)
    assert "REPORT BLOCKED" in safe
    assert "14,49,000" not in safe
    assert "No GO/NO-GO decision" in safe


def test_invented_contract_value_is_removed_not_blocked():
    from app.core.analysis_quality import audit_final_report, sanitize_final_report
    final = ("GO / NO-GO DECISION: CONDITIONAL GO\n"
             "- Estimated contract value: Rs 12,50,00,000\n"
             "The project is valued at Rs 4,00,000 crore.")
    cleaned = sanitize_final_report(final, "tender text without any value", {})
    assert "12,50,00,000" not in cleaned and "4,00,000" not in cleaned
    assert "Not stated in the tender" in cleaned
    assert not [i for i in audit_final_report(cleaned, "tender text", {}) if i.code == "unsupported_contract_value"]


def test_real_contract_value_is_kept():
    from app.core.analysis_quality import sanitize_final_report
    final = "Estimated contract value: Rs 12,50,000"
    facts = {"Estimated Contract Value": {"value": "Rs 12,50,000"}}
    assert sanitize_final_report(final, "Estimated contract value: Rs 12,50,000", facts) == final


# ── Missing-decision fallback ───────────────────────────────────────────────
def test_decision_written_only_in_body_is_inserted_near_top():
    final = """# Final Decision Briefing

EXECUTIVE SUMMARY
This tender fits our road portfolio. Overall stance: CONDITIONAL GO ⚠️ subject to the solvency certificate.

FINAL RECOMMENDED QUOTE
NOT CALCULABLE FROM SUPPLIED EVIDENCE
"""
    cleaned = sanitize_final_report(final, "Tender body", {})
    lines = cleaned.splitlines()
    assert lines[0] == "# Final Decision Briefing"
    assert "GO / NO-GO DECISION: CONDITIONAL GO (inferred from the final report text)" in lines[:3]
    assert "missing_final_decision" not in {i.code for i in audit_final_report(cleaned, "Tender body", {})}


def test_bold_label_decision_is_recognised_without_inference():
    final = "**GO / NO-GO DECISION**: GO ✅\nFINAL RECOMMENDED QUOTE\nNOT CALCULABLE FROM SUPPLIED EVIDENCE\n"
    assert sanitize_final_report(final, "Tender body", {}).strip() == final.strip()
    assert audit_final_report(final, "Tender body", {}) == []


def test_bid_manager_recommendation_is_the_fallback():
    final = "EXECUTIVE SUMMARY\nThe tender is for a highway package.\n\nFINAL RECOMMENDED QUOTE\nNOT CALCULABLE FROM SUPPLIED EVIDENCE\n"
    bid_manager = (
        "**TENDER SNAPSHOT**\n**BID READINESS: MEDIUM EVIDENCE COVERAGE**\n"
        "**RECOMMENDATION: NO-BID**\nThe firm lacks the similar-work value."
    )
    cleaned = sanitize_final_report(final, "Tender body", {}, bid_manager_report=bid_manager)
    assert cleaned.startswith("GO / NO-GO DECISION: NO-GO (inferred from the Bid Manager recommendation)\n")
    assert "missing_final_decision" not in {i.code for i in audit_final_report(cleaned, "Tender body", {})}


def test_conflicting_decisions_are_not_inserted():
    final = "EXECUTIVE SUMMARY\nTechnically this is a GO, but financially a NO-GO.\n"
    assert sanitize_final_report(final, "Tender body", {}, bid_manager_report="RECOMMENDATION: BID").strip() == final.strip()
    codes = {i.code for i in audit_final_report(final, "Tender body", {})}
    assert "missing_final_decision" in codes


def test_ambiguous_bid_manager_and_template_echo_stay_blocked():
    final = "EXECUTIVE SUMMARY\nNo verdict was reached.\n"
    echoed = "RECOMMENDATION: [BID / CONDITIONAL BID / NO-BID]"
    assert sanitize_final_report(final, "Tender body", {}, bid_manager_report=echoed).strip() == final.strip()
    template = "GO / NO-GO DECISION: [GO ✅ / NO-GO ❌ / CONDITIONAL GO ⚠️]\n"
    assert sanitize_final_report(template, "Tender body", {}).strip() == template.strip()


def test_caps_headings_are_not_read_as_decisions():
    final = "BID READINESS: LOW\nTECHNICAL BID evaluation pending.\n"
    assert sanitize_final_report(final, "Tender body", {}).strip() == final.strip()
