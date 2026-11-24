import io
import unittest
import zipfile

from app.core.document_extract import DocumentExtractionError, extract_document_text, extract_docx_text
from app.core.tender_evidence import extract_tender_evidence, format_evidence_block


def _docx_bytes(*paragraphs: str) -> bytes:
    body = "".join(
        f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>' for text in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    destination = io.BytesIO()
    with zipfile.ZipFile(destination, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return destination.getvalue()


class DocumentExtractionTests(unittest.TestCase):
    def test_docx_paragraphs_are_extracted(self):
        data = _docx_bytes("Tender reference ABC/12", "Deadline 18:00 IST")
        self.assertEqual(
            extract_docx_text(data),
            "Tender reference ABC/12\nDeadline 18:00 IST",
        )

    def test_docx_is_routed_by_extension(self):
        data = _docx_bytes("Supply of 100 laptops")
        self.assertEqual(extract_document_text(data, "tender.docx"), "Supply of 100 laptops")

    def test_invalid_docx_has_actionable_error(self):
        with self.assertRaisesRegex(DocumentExtractionError, "valid, unencrypted Word document"):
            extract_docx_text(b"not a zip package")

    def test_legacy_doc_without_converter_gives_guidance(self):
        from unittest import mock
        with mock.patch("app.core.document_convert._tool", return_value=None):
            with self.assertRaisesRegex(DocumentExtractionError, r"\.docx or PDF"):
                extract_document_text(b"binary", "old.doc")

    def test_unknown_binary_type_is_rejected(self):
        with self.assertRaisesRegex(DocumentExtractionError, "Unsupported tender file type"):
            extract_document_text(b"binary", "archive.zip")

    def test_metadata_candidates_keep_document_and_page_citations(self):
        text = """--- SOURCE DOCUMENT: notice.pdf ---
--- PAGE 4 ---
Tender Reference / NIT Number: FD/IT/2026/104
Estimated Contract Value (₹): ₹12,50,00,000
EMD Amount: ₹25,00,000
--- PAGE 7 ---
Bid Submission Deadline: 30 September 2026 at 15:00 IST
Bid Opening Date: 1 October 2026 at 16:00 IST
Contract Duration: 24 months
Procurement Portal: https://tender.telangana.gov.in
"""
        evidence = extract_tender_evidence(text)
        values = {item.field: item for item in evidence}
        self.assertEqual(values["Tender Reference / NIT Number"].value, "FD/IT/2026/104")
        self.assertEqual(values["EMD Amount"].value, "₹25,00,000")
        self.assertEqual(values["Bid Submission Deadline"].page, "7")
        self.assertEqual(values["Contract Duration / Period"].value, "24 months")
        self.assertEqual(values["Procurement Portal"].value, "https://tender.telangana.gov.in")
        block = format_evidence_block(evidence)
        self.assertIn("notice.pdf, page 4", block)
        self.assertIn("₹12,50,00,000", block)

    def test_metadata_candidates_scan_later_documents(self):
        text = """--- SOURCE DOCUMENT: volume-1.docx ---
Scope of work only.
--- SOURCE DOCUMENT: volume-2.docx ---
NIT No: TSIIC/PROC/88/2026
Last date for bid submission: 18 October 2026, 17:00 IST
"""
        evidence = extract_tender_evidence(text)
        self.assertTrue(any(item.value == "TSIIC/PROC/88/2026" for item in evidence))
        self.assertTrue(any(item.source == "volume-2.docx" for item in evidence))

    def test_duration_prose_is_not_mistaken_for_a_label(self):
        text = """--- SOURCE DOCUMENT: scope.docx ---
During the contract period, additional applications may be requested.
The engagement is expected to run over approximately 6 Weeks from contract signature.
"""
        evidence = extract_tender_evidence(text)
        durations = [item.value for item in evidence if item.field == "Contract Duration / Period"]
        self.assertEqual(durations, ["approximately 6 Weeks"])

    def test_project_label_is_a_title_candidate_and_delivery_is_duration(self):
        text = """--- SOURCE DOCUMENT: sample.pdf ---
Project: Supply, Installation and Maintenance of Citizen Service Kiosks
Delivery and installation must be completed within 90 calendar days of the purchase order.
"""
        values = {item.field: item.value for item in extract_tender_evidence(text)}
        self.assertEqual(values["Tender Title"], "Supply, Installation and Maintenance of Citizen Service Kiosks")
        self.assertEqual(values["Contract Duration / Period"], "90 calendar days of the purchase order")


def test_xlsx_is_extracted_as_pipe_tables():
    import io, openpyxl
    from app.core.document_extract import extract_document_text
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "BOQ"
    ws.append(["Item", "Qty", "Rate"]); ws.append(["LED pole", 100, 5000]); ws.append([None, None, None]); ws.append(["Total", "", 500000])
    buf = io.BytesIO(); wb.save(buf)
    out = extract_document_text(buf.getvalue(), "boq.xlsx")
    assert "--- SHEET: BOQ ---" in out
    assert "Item | Qty | Rate" in out
    assert "LED pole | 100 | 5000" in out
    assert "Total |  | 500000" in out


def test_legacy_xls_is_rejected_with_guidance():
    from app.core.document_extract import extract_document_text, DocumentExtractionError
    try:
        extract_document_text(b"\\xd0\\xcf", "old.xls")
        assert False, "should have raised"
    except DocumentExtractionError as exc:
        assert ".xlsx" in str(exc)


def test_legacy_xls_is_extracted():
    import io
    xlwt = __import__("pytest").importorskip("xlwt")  # test-only writer; not a runtime dep
    from app.core.document_extract import extract_document_text
    wb = xlwt.Workbook(); ws = wb.add_sheet("BOQ")
    for c, h in enumerate(["Item", "Qty", "Rate"]): ws.write(0, c, h)
    for c, v in enumerate(["LED pole", 100, 5000]): ws.write(1, c, v)
    buf = io.BytesIO(); wb.save(buf)
    out = extract_document_text(buf.getvalue(), "boq.xls")
    assert "--- SHEET: BOQ ---" in out and "Item | Qty | Rate" in out and "LED pole | 100 | 5000" in out
