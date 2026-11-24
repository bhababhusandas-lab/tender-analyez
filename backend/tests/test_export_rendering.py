import json
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from pypdf import PdfReader

from app.api.v1.export import (
    brief_sections, build_pdf, is_discrepancy_section, report_generated_timestamp, strip_markdown,
    summary_sections,
)


class ExportRenderingTests(unittest.TestCase):
    def test_report_timestamp_is_converted_to_india_time_and_labelled(self):
        utc_time = datetime(2026, 9, 28, 10, 9, tzinfo=timezone.utc)
        self.assertEqual(
            report_generated_timestamp(utc_time),
            "28 Sep 2026, 03:39 PM IST",
        )

    def test_markdown_tables_and_rules_are_rendered_not_printed(self):
        content = """## Tender snapshot
| Field | Value |
|---|---|
| Tender title | Citizen Service Kiosks |
---
- Evidence checked
"""
        bid = SimpleNamespace(
            tender_name="Citizen Service Kiosks",
            department="Example authority",
            portal="",
            reference_no="TEST/1",
            submission_deadline="20 Oct 2026",
            recommended_quote="Rs.14,49,000",
            bid_confidence="",
            pipeline_result=json.dumps({
                "bid-manager": content,
                "final": "## Final recommended quote\nNOT CALCULABLE FROM SUPPLIED EVIDENCE",
            }),
        )
        path = build_pdf(bid, full=True)
        try:
            extracted = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        finally:
            os.unlink(path)
        self.assertIn("Citizen Service Kiosks", extracted)
        self.assertIn("QUOTE STATUS: NOT CALCULABLE FROM SUPPLIED EVIDENCE", extracted)
        self.assertNotIn("| Field | Value |", extracted)
        self.assertNotIn("---", extracted)
        self.assertNotIn("Confidence:", extracted)
        self.assertIn("IST", extracted)


MANAGER = """## Decision
**CONDITIONAL BID**
## Eligibility
| # | Eligibility Criterion | Our Status | Evidence / Notes |
|---|---|---|---|
| 1 | IRDAI Licensed Insurance Company | ❌ We Don't Meet It | No IRDA proof |
| 2 | Office in Hyderabad | ✅ Meets | Lease on file |
| 3 | Tender fee Rs.10,000 | ⚠️ Needs Verification | Not in profile |
## Deadlines
- **Bid Submission Deadline**: 30.09.2026 at 5:00 PM
## Risks
1. Missing IRDA registration
## Action plan
1. Verify IRDA registration
"""

FINAL = """### **EXECUTIVE SUMMARY**
The department seeks group health insurance for 3,680 employees. Cover runs from 01.11.2026 to 31.10.2027. Our profile lacks key eligibility evidence.
### **FINAL RECOMMENDED QUOTE**
**NOT CALCULABLE FROM SUPPLIED EVIDENCE**
- **Required Inputs**:
  - CA-certified turnover
### **GO / NO-GO DECISION: CONDITIONAL GO ⚠️**
**Decision**: Proceed only if the following conditions are met:
1. Verify IRDAI registration.
**Rationale**:
- **Eligibility Gaps**: Missing IRDAI registration.
- **Strengths**: Government project experience.
---
### **CRITICAL RISKS TO MANAGE**
| Risk | Severity | Mitigation |
|---|---|---|
| Missing IRDAI | High | Submit licence |
| Invalid PAN | High | Attach PAN |
| Low turnover | High | CA certificate |
| No Hyderabad office | Medium | Utility bill |
### **CRITICAL ACTION ITEMS — Next 72 Hours**
| # | Action Item | Owner |
|---|---|---|
| 1 | Verify IRDAI | Legal |
| 2 | PAN/GST | Compliance |
| 3 | Turnover | Finance |
| 4 | Hyderabad proof | Legal |
| 5 | Authorisation letter | Legal |
| 6 | Sixth item | Legal |
### **QUALITY-GATE REWRITE REQUIRED**
Internal self-check text.
"""


class SummaryExportTests(unittest.TestCase):
    def _bid(self):
        return SimpleNamespace(
            tender_name="Group Health Insurance", department="", portal="", reference_no="",
            submission_deadline="30.09.2026", recommended_quote=None, bid_confidence="",
            pipeline_result=json.dumps({"bid-manager": MANAGER, "legal-compliance": "## Legal\nClause detail",
                                        "final": FINAL}),
        )

    def test_summary_has_six_sections_each_stated_once(self):
        sections = dict(summary_sections(json.loads(self._bid().pipeline_result)))
        self.assertEqual(list(sections), ["Tender at a glance", "Decision", "Deadlines", "Eligibility gaps", "Quote", "Top risks", "Next steps"])
        # What is being bought, stopping before our own readiness (covered below).
        self.assertIn("3,680 employees", sections["Tender at a glance"])
        self.assertIn("31.10.2027", sections["Tender at a glance"])
        self.assertNotIn("lacks", sections["Tender at a glance"])
        self.assertIn("CONDITIONAL GO", sections["Decision"])
        self.assertIn("**Why**", sections["Decision"])
        self.assertIn("Government project experience", sections["Decision"])
        self.assertNotIn("Proceed only if", sections["Decision"])
        self.assertNotIn("Verify IRDAI registration.", sections["Decision"])
        self.assertNotIn("---", sections["Decision"])
        # Only unmet criteria, without the emoji prefix.
        self.assertIn("IRDAI Licensed Insurance Company | We Don't Meet It | No IRDA proof", sections["Eligibility gaps"])
        self.assertIn("Needs Verification", sections["Eligibility gaps"])
        self.assertNotIn("Office in Hyderabad", sections["Eligibility gaps"])
        # The quote value, not its "required inputs" list (repeats the gaps).
        self.assertIn("NOT CALCULABLE", sections["Quote"])
        self.assertNotIn("CA-certified", sections["Quote"])
        self.assertEqual(sections["Top risks"].count("\n") - 1, 3)
        self.assertEqual(sections["Next steps"].count("\n") - 1, 5)

    def _text(self, full):
        path = build_pdf(self._bid(), full=full)
        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages), len(PdfReader(path).pages)
        finally:
            os.unlink(path)

    def test_default_export_is_the_brief_only(self):
        text, _ = self._text(full=False)
        self.assertIn("Bid Summary", text)
        self.assertIn("30.09.2026", text)
        self.assertIn("Tender at a glance", text)
        self.assertNotIn("Clause detail", text)
        self.assertNotIn("QUALITY-GATE", text)
        self.assertNotIn("Sixth item", text)
        # Older analyses have no brief: the short summary is unchanged.
        self.assertNotIn("Tender Brief", text)
        self.assertNotIn("Our Bid Assessment", text)

    def test_full_export_appends_specialist_reports_without_internal_self_check(self):
        text, _ = self._text(full=True)
        self.assertIn("Full Bid Report", text)
        self.assertIn("Appendix: detailed specialist reports", text)
        self.assertIn("Clause detail", text)
        self.assertNotIn("Internal self-check", text)

    def test_unsupported_symbols_are_spelled_out(self):
        self.assertEqual(strip_markdown("Turnover ≥ ₹50 Crore ⚠️"), "Turnover >= Rs.50 Crore Needs review")


BRIEF = """# Tender Brief
## 1. Tender Overview
- **Issuing authority:** Society for Rural Development Services, Hyderabad [Page 1]
- **Estimated value:** Not stated in the tender
## 2. Key Dates & Schedule
| Activity | Date & Time |
|---|---|
| Bid submission | 15.10.2026, 3:00 PM [Clause 4] |
## 3. Eligibility Criteria
1. IRDAI-registered insurer [Clause 5.1]
## 4. Scope of Work / Deliverables
1. Maternity cover Rs.25,000 normal / Rs.50,000 caesarean [Clause 7.3]
## 5. Commercial Terms
- **EMD:** Rs.1,00,000 by DD [Clause 6]
## 6. Evaluation Process
L1 on total premium [Clause 9]
## 7. Documents to be Submitted
- **Technical bid:** IRDAI licence
## 8. Appendices & Annexures
### Annexure A - Benefit table
| Benefit | Limit |
|---|---|
| Maternity | Rs.5,000 / Rs.25,000 |
## 9. Discrepancies to Clarify at Pre-bid
| # | Topic | Value in one place [ref] | Conflicting value [ref] | Clarification to seek |
|---|---|---|---|---|
| 1 | Maternity limit | Rs.25,000 / Rs.50,000 [Clause 7.3] | Rs.5,000 / Rs.25,000 [Annexure A] | Which limit applies |
"""

BRIEF_TITLES = [
    "1. Tender Overview", "2. Key Dates & Schedule", "3. Eligibility Criteria",
    "4. Scope of Work / Deliverables", "5. Commercial Terms", "6. Evaluation Process",
    "7. Documents to be Submitted", "8. Appendices & Annexures", "9. Discrepancies to Clarify at Pre-bid",
]


class TenderBriefExportTests(unittest.TestCase):
    def _bid(self):
        results = {"tender-brief": BRIEF, "bid-manager": MANAGER, "legal-compliance": "## Legal\nClause detail",
                   "final": FINAL}
        return SimpleNamespace(
            tender_name="Group Health Insurance", department="", portal="", reference_no="",
            submission_deadline="30.09.2026", recommended_quote=None, bid_confidence="",
            pipeline_result=json.dumps(results),
        )

    def _text(self, full, bid=None):
        path = build_pdf(bid or self._bid(), full=full)
        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        finally:
            os.unlink(path)

    def test_brief_splits_on_level_two_headings_only(self):
        sections = brief_sections(BRIEF)
        self.assertEqual([title for title, _ in sections], BRIEF_TITLES)
        annexures = dict(sections)["8. Appendices & Annexures"]
        self.assertIn("### Annexure A - Benefit table", annexures)
        self.assertTrue(is_discrepancy_section(BRIEF_TITLES[-1]))
        self.assertFalse(any(is_discrepancy_section(title) for title in BRIEF_TITLES[:-1]))

    def test_summary_with_brief_renders_every_brief_section_and_discrepancies(self):
        text = self._text(full=False)
        self.assertIn("Tender Brief", text)
        self.assertNotIn("Bid Summary", text)
        for title in BRIEF_TITLES:
            self.assertIn(title, text)
        self.assertIn("Society for Rural Development Services", text)
        self.assertIn("Annexure A - Benefit table", text)
        self.assertIn("Rs.5,000 / Rs.25,000 [Annexure A]", text)
        self.assertIn("Which limit applies", text)
        self.assertNotIn("| Activity |", text)
        # Specialist working stays in the Full report.
        self.assertNotIn("Clause detail", text)

    def test_summary_with_brief_ends_with_our_decision(self):
        text = self._text(full=False)
        self.assertIn("10. Our Bid Assessment", text)
        self.assertGreater(text.index("10. Our Bid Assessment"), text.index("9. Discrepancies"))
        assessment = text[text.index("10. Our Bid Assessment"):]
        self.assertIn("CONDITIONAL GO", assessment)
        self.assertIn("Government project experience", assessment)
        self.assertIn("Eligibility gaps", assessment)
        self.assertIn("IRDAI Licensed Insurance Company", assessment)
        self.assertIn("NOT CALCULABLE", text)
        self.assertIn("Top risks", assessment)
        self.assertIn("Next steps", assessment)
        # The brief already states the overview and dates.
        self.assertNotIn("Tender at a glance", text)
        self.assertNotIn("QUALITY-GATE", text)

    def test_full_report_puts_brief_first_in_appendix(self):
        text = self._text(full=True)
        self.assertIn("Full Bid Report", text)
        self.assertIn("Tender at a glance", text)
        appendix = text[text.index("Appendix: detailed specialist reports"):]
        self.assertIn("9. Discrepancies to Clarify at Pre-bid", appendix)
        self.assertLess(appendix.index("1. Tender Overview"), appendix.index("Bid Manager AI"))
        self.assertIn("Clause detail", appendix)
        self.assertNotIn("Our Bid Assessment", text)

    def test_empty_brief_keeps_the_short_summary(self):
        bid = self._bid()
        results = json.loads(bid.pipeline_result)
        results["tender-brief"] = "   "
        bid.pipeline_result = json.dumps(results)
        text = self._text(full=False, bid=bid)
        self.assertIn("Bid Summary", text)
        self.assertIn("Tender at a glance", text)
        self.assertNotIn("Our Bid Assessment", text)


def test_brief_citations_are_compacted():
    from app.api.v1.export import compact_citations
    text = "- EMD: Rs.10,00,000 [Source: RFP for Digital Media campaign for global summit.pdf, page 14]\n- Portal: eProc [Source: RFP.pdf]\n- Fee [Page 3]"
    out = compact_citations(text)
    assert "- EMD: Rs.10,00,000 [p.14]" in out
    assert "- Portal: eProc" in out and "Source" not in out
    assert "- Fee [p.3]" in out


TEN_HEADINGS = [
    "1. Basic Tender Information", "2. Important Dates & Timeline",
    "3. Eligibility & Qualification Criteria", "4. Detailed Scope of Work",
    "5. Commercial Terms", "6. Evaluation & Selection Process", "7. Documents Required",
    "8. Risk Analysis & Critical Points", "9. Final Bid Recommendation",
    "10. Open Points / Clarifications Required",
]

TEN_SECTION_BRIEF = "\n".join([
    "## 1. Basic Tender Information",
    "| Particulars | Details |", "|---|---|", "| Issuing Organization | Example Authority |",
    "## 2. Important Dates & Timeline",
    "| Activity | Date & Time | Remarks |", "|---|---|---|", "| Bid Submission Closing | 20 Oct 2026 | [p.2] |",
    "## 3. Eligibility & Qualification Criteria",
    "### 3.1 Legal & Basic Eligibility", "- Registered firm [Cl. 4]",
    "### 3.5 Consortium / Joint Venture (JV) Status",
    "| Particulars | Details |", "|---|---|", "| JV allowed? | Silent |",
    "## 4. Detailed Scope of Work", "### 4.1 Overall Scope", "- Run a campaign",
    "### 4.3 Bill of Quantities / Quantity Summary",
    "| S.No | Location/Item | Description | Quantity | Unit | Remarks |", "|---|---|---|---|---|---|",
    "| 1 | Delhi | Banner | 10 | Nos | - |",
    "## 5. Commercial Terms", "| Term | Full Details |", "|---|---|", "| EMD/Bid Security | Rs.1,00,000 |",
    "## 6. Evaluation & Selection Process", "- QCBS 70:30",
    "## 7. Documents Required", "### A. Technical Bid Documents", "1. PAN",
    "## 8. Risk Analysis & Critical Points",
    "| Risk/Gap | Severity | Possible Impact | Recommended Action |", "|---|---|---|---|",
    "| Short timeline | High | Delay | Plan early |",
    "## 9. Final Bid Recommendation",
    "- **Decision:** CONDITIONAL GO", "- **Justification:** Eligible subject to JV clarity",
    "- **Mandatory Actions Before Bidding:**", "1. Raise JV query",
    "## 10. Open Points / Clarifications Required", "- JV status",
])


def _pdf_text(pipeline: dict, full: bool = False) -> str:
    bid = SimpleNamespace(
        tender_name="Digital Media Campaign", department="", portal="", reference_no="T/1",
        submission_deadline="", recommended_quote="", bid_confidence="",
        pipeline_result=json.dumps(pipeline),
    )
    path = build_pdf(bid, full=full)
    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    finally:
        os.unlink(path)


def test_ten_section_brief_replaces_separate_bid_assessment():
    text = _pdf_text({
        "tender-brief": TEN_SECTION_BRIEF,
        "bid-manager": "## Decision\n**CONDITIONAL BID**\n## Eligibility\nSomething",
        "final": "## Final recommendation\nBid it",
    })
    for heading in TEN_HEADINGS:
        assert heading in text, heading
    assert "CONDITIONAL GO" in text
    assert "3.1 Legal & Basic Eligibility" in text
    assert "Our Bid Assessment" not in text
    assert "| Particulars" not in text


def test_without_brief_old_summary_still_renders():
    text = _pdf_text({
        "bid-manager": "## Decision\n**CONDITIONAL BID**\n## Eligibility\nSomething",
        "final": "## Final recommendation\nBid it",
    })
    assert "Bid Summary" in text
    assert "Tender Brief" not in text
    assert "Our Bid Assessment" not in text


def test_tender_brief_prompt_has_all_ten_headings():
    from app.agents.registry import AGENT_SYSTEM_PROMPTS
    prompt = AGENT_SYSTEM_PROMPTS["tender-brief"]
    for heading in TEN_HEADINGS:
        assert f"## {heading}" in prompt, heading
    assert "Not stated in the tender" in prompt
    assert "CONDITIONAL GO" in prompt
