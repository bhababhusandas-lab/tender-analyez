from app.core.tender_evidence import canonical_fact_record, extract_tender_evidence, prefer_newest_evidence

ORIGINAL = """--- SOURCE DOCUMENT: Tender.pdf ---
Bid Submission Deadline: 30.09.2026 17:00
EMD Amount: Rs 50,000
Tender Reference: SRDS/2026/50
"""
CORRIGENDUM = """--- SOURCE DOCUMENT: Corrigendum-1.pdf ---
Bid Submission Deadline: 07.10.2026 17:00
"""


def test_update_value_replaces_original_for_the_same_field():
    evidence = prefer_newest_evidence([extract_tender_evidence(CORRIGENDUM), extract_tender_evidence(ORIGINAL)])
    facts, conflicts = canonical_fact_record(evidence)
    assert facts["Bid Submission Deadline"].value.startswith("07.10.2026")
    assert facts["Bid Submission Deadline"].source == "Corrigendum-1.pdf"
    assert "Bid Submission Deadline" not in conflicts


def test_fields_missing_from_the_update_keep_the_original():
    evidence = prefer_newest_evidence([extract_tender_evidence(CORRIGENDUM), extract_tender_evidence(ORIGINAL)])
    facts, _ = canonical_fact_record(evidence)
    assert facts["EMD Amount"].value == "Rs 50,000"


def test_opening_date_line_is_not_read_as_the_submission_deadline():
    text = """--- SOURCE DOCUMENT: Tender.pdf ---
Closing Date and Time of Technical Bid Opening: 10.10.2026 15:00
"""
    evidence = extract_tender_evidence(text)
    assert not any(item.field == "Bid Submission Deadline" for item in evidence)


def test_plain_closing_date_lines_are_still_read_as_the_submission_deadline():
    closing_date = extract_tender_evidence(
        "--- SOURCE DOCUMENT: Tender.pdf ---\nClosing Date: 30.09.2026 17:00\n"
    )
    closing_date_and_time = extract_tender_evidence(
        "--- SOURCE DOCUMENT: Tender.pdf ---\nClosing Date and Time: 30.09.2026 17:00\n"
    )
    assert [item.value for item in closing_date if item.field == "Bid Submission Deadline"] == ["30.09.2026 17:00"]
    assert [item.value for item in closing_date_and_time if item.field == "Bid Submission Deadline"] == [
        "30.09.2026 17:00"
    ]


def test_conflicting_values_within_a_single_layer_still_conflict():
    text = """--- SOURCE DOCUMENT: Tender.pdf ---
Bid Submission Deadline: 30.09.2026 17:00
Closing Date: 01.10.2026 17:00
"""
    evidence = prefer_newest_evidence([extract_tender_evidence(text)])
    facts, conflicts = canonical_fact_record(evidence)
    assert "Bid Submission Deadline" not in facts
    values = {item.value for item in conflicts["Bid Submission Deadline"]}
    assert values == {"30.09.2026 17:00", "01.10.2026 17:00"}


def test_empty_newest_layer_leaves_the_originals_facts_intact():
    evidence = prefer_newest_evidence([[], extract_tender_evidence(ORIGINAL)])
    facts, _ = canonical_fact_record(evidence)
    assert facts["Bid Submission Deadline"].value.startswith("30.09.2026")
    assert facts["EMD Amount"].value == "Rs 50,000"


def test_hyphenated_opening_date_line_is_not_read_as_the_submission_deadline():
    text = """--- SOURCE DOCUMENT: Tender.pdf ---
Closing Date of Pre-bid Opening: 10.10.2026 15:00
"""
    evidence = extract_tender_evidence(text)
    assert not any(item.field == "Bid Submission Deadline" for item in evidence)


def test_closing_date_with_dash_separator_is_still_read_as_the_submission_deadline():
    text = """--- SOURCE DOCUMENT: Tender.pdf ---
Closing Date - 30.09.2026
"""
    evidence = extract_tender_evidence(text)
    assert [item.value for item in evidence if item.field == "Bid Submission Deadline"] == ["30.09.2026"]
