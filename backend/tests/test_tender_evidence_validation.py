"""Field validation for deterministic tender facts, including the real RR-2 tender."""
import re
from pathlib import Path

import pytest

from app.core.tender_evidence import canonical_fact_record, extract_tender_evidence

FIXTURE = Path(__file__).parent / "reviewed_tenders" / "rr2_radial_road_pkg1" / "tender.txt"


def _values(text: str, field: str) -> list[str]:
    return [item.value for item in extract_tender_evidence(text) if item.field == field]


@pytest.fixture(scope="module")
def rr2():
    evidence = extract_tender_evidence(FIXTURE.read_text())
    facts, conflicts = canonical_fact_record(evidence)
    return evidence, facts, conflicts


# ── The real tender ────────────────────────────────────────────────────────
def test_rr2_emd_is_the_nit_amount(rr2):
    _, facts, _ = rr2
    assert facts["EMD Amount"].value == "Rs. 12,37,20,000"
    assert facts["EMD Amount"].source == "RR2 Pkg 1 Bid document.pdf"


def test_rr2_estimated_contract_value(rr2):
    _, facts, _ = rr2
    assert "12,37,16,34,251" in facts["Estimated Contract Value"].value


def test_rr2_submission_deadline_has_date_and_time(rr2):
    evidence, facts, _ = rr2
    deadline = facts["Bid Submission Deadline"].value
    assert deadline.replace("/", ".").startswith("30.09.2026")
    assert "3:00 PM" in deadline.replace("03:00", "3:00").replace("3.00", "3:00")


def test_rr2_opening_and_pre_bid_dates(rr2):
    _, facts, _ = rr2
    assert facts["Technical Bid Opening"].value == "30.09.2026 @ 3.30 PM"
    assert facts["Pre-bid Meeting"].value == "22.09.2026 @ 11.30 AM"


def test_rr2_completion_period(rr2):
    _, facts, _ = rr2
    assert facts["Contract Duration / Period"].value == "18 months"


def test_rr2_no_junk_values(rr2):
    evidence, _, _ = rr2
    junk = {"of tenders", "of", "no", "construction"}
    for item in evidence:
        assert item.value.casefold() not in junk, item
        assert not item.value.lower().endswith(" from"), item
        if item.field in {"EMD Amount", "Estimated Contract Value"}:
            assert any(ch.isdigit() for ch in item.value), item
        if item.field == "Bid Submission Deadline":
            assert "2026" in item.value, item


# ── Validation rules ──────────────────────────────────────────────────────
@pytest.mark.parametrize("line", [
    "EMD, Transaction fee, hard copies of uploaded documents within the stipulated time",
    "EMD within the stipulated time or if any variation is noticed between the uploaded",
    "EMD of 2.50% at the time of concluding agreement.",
])
def test_emd_sentence_fragments_are_rejected(line):
    assert _values(f"--- SOURCE DOCUMENT: t.pdf ---\n{line}\n", "EMD Amount") == []


def test_deadline_without_a_date_is_rejected():
    text = "--- SOURCE DOCUMENT: t.pdf ---\n7) Last date and time for submission of Tenders\nSee NIT.\n"
    assert _values(text, "Bid Submission Deadline") == []


def test_estimated_value_prose_is_rejected():
    text = "--- SOURCE DOCUMENT: t.pdf ---\nestimated value of the work completed less the cumulative amount certified\n"
    assert _values(text, "Estimated Contract Value") == []


def test_contract_period_prose_is_not_a_duration():
    text = "--- SOURCE DOCUMENT: t.pdf ---\ncontract period plus defect liability period of two years\n"
    assert _values(text, "Contract Duration / Period") == []


@pytest.mark.parametrize("title", ["No", "of", "Construction of Radial Road 2 from"])
def test_trivial_titles_are_rejected(title):
    assert _values(f"--- SOURCE DOCUMENT: t.pdf ---\nName of Work: {title}\n\n", "Tender Title") == []


def test_title_fragment_is_continued_onto_the_next_lines():
    text = ("--- SOURCE DOCUMENT: t.pdf ---\n1) Name of the work : Construction of Radial Road 2 from\n"
            "ORR at Kothwalguda to NH-167N\n\n2) Other\n")
    assert _values(text, "Tender Title") == ["Construction of Radial Road 2 from ORR at Kothwalguda to NH-167N"]


# ── Table layouts ─────────────────────────────────────────────────────────
def test_pipe_separated_table_row():
    text = "--- SOURCE DOCUMENT: t.pdf ---\n| EMD Amount | Rs. 5,00,000 | Online |\n"
    assert _values(text, "EMD Amount") == ["Rs. 5,00,000"]


def test_tab_separated_table_row():
    text = "--- SOURCE DOCUMENT: t.pdf ---\nBid Submission Deadline\t15-10-2026 17:00\tOnline\n"
    assert _values(text, "Bid Submission Deadline") == ["15-10-2026 17:00"]


def test_value_on_the_next_line():
    text = "--- SOURCE DOCUMENT: t.pdf ---\nEarnest Money Deposit\n: ₹ 2,50,000/-\n"
    assert _values(text, "EMD Amount") == ["₹ 2,50,000"]


def test_amount_in_crore():
    text = "--- SOURCE DOCUMENT: t.pdf ---\nEstimated Contract Value: 45.60 Crore\n"
    assert _values(text, "Estimated Contract Value") == ["45.60 Crore"]


def test_written_month_dates_keep_their_time():
    text = "--- SOURCE DOCUMENT: t.pdf ---\nPre-bid Meeting: 22 September 2026 at 11:30 AM, HGCL office\n"
    assert _values(text, "Pre-bid Meeting") == ["22 September 2026 at 11:30 AM"]


def test_same_deadline_in_two_formats_is_one_fact():
    text = ("--- SOURCE DOCUMENT: a.pdf ---\nClosing Date\n30/09/2026 03:00 PM\n"
            "--- SOURCE DOCUMENT: b.pdf ---\nBid Submission Deadline: 30.09.2026 @ 3.00 PM\n")
    facts, conflicts = canonical_fact_record(extract_tender_evidence(text))
    assert "Bid Submission Deadline" in facts
    assert "Bid Submission Deadline" not in conflicts


def test_numbered_label_list_values_are_matched_by_position():
    text = ("--- SOURCE DOCUMENT: t.pdf ---\n8) Date and time of opening\nof tenders\n a) Technical Bid\n"
            " b) Pre-Bid\n\n:\n:\n\n30.09.2026 @ 3.30 PM\n22.09.2026 @ 11.30 AM at office,\n")
    assert _values(text, "Technical Bid Opening") == ["30.09.2026 @ 3.30 PM"]
    assert _values(text, "Pre-bid Meeting") == ["22.09.2026 @ 11.30 AM"]


# ── Eligibility facts from NIT prose and tables (RR-2) ─────────────────────
def test_rr2_technical_bid_opening_keeps_time(rr2):
    from app.core.tender_evidence import _parse_time, format_evidence_block

    evidence, facts, _ = rr2
    opening = facts["Technical Bid Opening"].value
    assert opening.startswith("30.09.2026")
    assert _parse_time(opening) == "15:30"
    block = format_evidence_block(evidence)
    assert "Technical Bid Opening: 30.09.2026 @ 3.30 PM (= 2026-09-30 15:30)" in block


def test_rr2_bid_capacity_formula_with_definitions(rr2):
    _, facts, _ = rr2
    formula = facts["Bid Capacity Formula"]
    assert formula.value == "2AN – B"
    assert "Bid Capacity" in formula.excerpt
    assert "A = Maximum value" in formula.excerpt and "N = Number of years" in formula.excerpt


def test_rr2_similar_work_and_liquid_assets(rr2):
    _, facts, _ = rr2
    assert facts["Similar Work Value"].value == "Rs.412.38 Cr"
    assert facts["Liquid Assets / Credit Facility"].value == "Rs. 206.20 Cr"


def test_rr2_key_personnel_and_equipment_lists(rr2):
    from app.core.tender_evidence import MAX_LIST_ITEMS

    _, facts, _ = rr2
    personnel = facts["Key Personnel"].value
    assert personnel.startswith("Project Manager: 1; Structure Manager: 1")
    assert "Diploma Engineer in Civil: 6" in personnel
    equipment = facts["Key Equipment"].value
    assert equipment.startswith("Dozer D -80/50: 2; Hydraulic excavators: 6")
    assert "more listed in the tender" in equipment
    for value in (personnel, equipment):
        items = value.split(" (+")[0].split("; ")
        assert 2 <= len(items) <= MAX_LIST_ITEMS
        for item in items:
            name, count = item.rsplit(": ", 1)
            assert count.isdigit() and len(name) >= 3
            assert not re.search(r"(?i)\b(?:minimum|required|s\. ?no)\b", name), item


def test_rr2_new_fields_have_no_junk(rr2):
    evidence, _, conflicts = rr2
    new_fields = {
        "Bid Capacity Formula", "Similar Work Value", "Liquid Assets / Credit Facility",
        "Key Personnel", "Key Equipment",
    }
    assert new_fields.isdisjoint(conflicts)
    for item in evidence:
        if item.field in new_fields:
            assert len(item.value) <= 700, item
        if item.field in {"Similar Work Value", "Liquid Assets / Credit Facility"}:
            assert re.fullmatch(r"Rs\.\s?\d[\d,]*(?:\.\d+)? Cr", item.value), item


def test_prose_amount_requires_a_threshold_and_currency():
    text = "d. Details of similar works completed as prime contractor.\nj. Availability of working capital [Liquid assets, credit facility]."
    assert _values(text, "Similar Work Value") == []
    assert _values(text, "Liquid Assets / Credit Facility") == []


def test_bid_capacity_variants():
    assert _values("Available bid capacity = 2 A N - B", "Bid Capacity Formula") == ["2AN – B"]
    assert _values("Bid capacity: 2.5AN – B", "Bid Capacity Formula") == ["2.5AN – B"]
    assert _values("Reference 2AN-B-17 in the drawing list", "Bid Capacity Formula") == []


# ── A fee, deposit or cap is never the contract value ──────────────────────
@pytest.mark.parametrize("text", [
    # Wrapped prose: the label closes a parenthetical and a fee cap follows.
    "shall collect 0.04% of ECV (estimated\ncontract value) with a cap of Rs.10,000=00 (Rupees Ten Thousand only) Non- Refundable\n",
    "Tender value based processing fee: Rs. 5,000\n",
    "Estimated cost of tender document fee Rs. 2,000\n",
    "Contract value: 2% EMD of Rs. 4,00,000\n",
    "Tender Value - transaction fee Rs. 11,800\n",
])
def test_fee_or_cap_is_not_a_contract_value(text):
    assert _values(text, "Estimated Contract Value") == []


def test_contract_value_equal_to_the_application_fee_is_dropped():
    text = "Application Fee: Rs 10,000/-\nEMD Amount: Rs. 10,00,000\nTender Value: Rs. 10,000\n"
    assert _values(text, "Estimated Contract Value") == []
    assert _values(text, "Application / Tender Fee") == ["Rs 10,000"]


def test_real_contract_value_is_still_read_next_to_fees():
    text = "Tender Fee: Rs. 5,000\nEMD: Rs. 5,00,000\nEstimated Contract Value (ECV): approx. Rs. 5.00 Crore\n"
    assert _values(text, "Estimated Contract Value") == ["Rs. 5.00 Crore"]
    assert _values(text, "Application / Tender Fee") == ["Rs. 5,000"]


def test_label_broken_by_a_pdf_hyphen_is_read():
    text = "Bid  Document Sub-\nmission End Date \n    03-10-2026 at 3.00 PM \n"
    assert _values(text, "Bid Submission Deadline") == ["03-10-2026 at 3.00 PM"]


def test_document_level_lists_are_capped():
    from app.core.tender_evidence import MAX_DOCUMENT_ITEMS, MAX_DOCUMENTS_VALUE_CHARS, MAX_VALUE_CHARS

    documents = "\n".join(f"{n}. Certificate number {n} issued by the competent authority for the firm" for n in range(1, 41))
    text = f"Documents to be uploaded\n{documents}\n\nA consortium is permitted.\n" + "\n".join(
        f"The Lead Member shall hold at least 5{n}% stake in the consortium number {n}." for n in range(9)
    )
    by_field = {item.field: item.value for item in extract_tender_evidence(text)}
    listed = by_field["Mandatory Documents"]
    assert len(listed.split(" (+")[0].split("; ")) <= MAX_DOCUMENT_ITEMS
    assert "more listed in the tender" in listed and len(listed) <= MAX_DOCUMENTS_VALUE_CHARS + 40
    assert len(by_field["Consortium / JV Conditions"]) <= MAX_VALUE_CHARS


def test_marks_breakdown_is_dropped_when_it_does_not_add_up():
    text = (
        "Technical Evaluation Criteria\nThe proposal shall be evaluated out of 100 marks. "
        "Bidders obtaining less than 60 marks shall not qualify.\nExperience 50\nPresentation 30\nTotal 100\n"
    )
    assert _values(text, "Technical Evaluation Marks") == ["Total 100 marks; minimum qualifying 60 marks"]
