"""Text extraction for tender uploads supported by the analysis endpoint."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.core.document_convert import ConversionError, prepare_upload
from app.core.pdf_extract import PdfExtractionError, extract_pdf_text


class DocumentExtractionError(Exception):
    """Raised when an uploaded tender cannot be converted to usable text."""


def extract_docx_text(data: bytes) -> str:
    """Extract paragraphs and table cells from a DOCX package in document order."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise DocumentExtractionError(
            "Could not read this DOCX file. Check that it is a valid, unencrypted Word document."
        ) from exc

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise DocumentExtractionError("The DOCX document content is malformed.") from exc

    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    blocks: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            blocks.append(text)
    extracted = "\n".join(blocks).strip()
    if not extracted:
        raise DocumentExtractionError(
            "No readable text was found in this DOCX file. Paste the tender text directly or upload a text-based PDF."
        )
    return extracted


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_XLSX_MAX_ROWS = 2000  # a BOQ can be huge; keep enough to carry totals and key rows


def extract_xlsx_text(data: bytes) -> str:
    """Flatten each worksheet to a pipe-separated text table the model can read.

    Formulas are read as their last-calculated value. Empty rows and columns are
    dropped so a sparse sheet stays compact.
    """
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - dependency is installed in prod
        raise DocumentExtractionError("Excel support is not available on this server.") from exc
    try:
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise DocumentExtractionError(
            "This Excel file could not be read. Re-save it as .xlsx (or export the sheet to PDF/CSV) and try again."
        ) from exc
    parts: list[str] = []
    for sheet in book.worksheets:
        rows: list[str] = []
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= _XLSX_MAX_ROWS:
                rows.append(f"[… sheet '{sheet.title}' truncated after {_XLSX_MAX_ROWS} rows]")
                break
            cells = ["" if v is None else str(v).strip() for v in row]
            if any(cells):
                rows.append(" | ".join(cells).rstrip(" |"))
        if rows:
            parts.append(f"--- SHEET: {sheet.title} ---\n" + "\n".join(rows))
    book.close()
    text = "\n\n".join(parts).strip()
    if not text:
        raise DocumentExtractionError("The uploaded Excel file has no readable data.")
    return text


def extract_xls_text(data: bytes) -> str:
    """Flatten a legacy .xls workbook to pipe-separated text tables (xlrd)."""
    try:
        import xlrd
    except ImportError as exc:  # pragma: no cover
        raise DocumentExtractionError("Legacy Excel (.xls) support is not available on this server.") from exc
    try:
        book = xlrd.open_workbook(file_contents=data)
    except Exception as exc:
        raise DocumentExtractionError(
            "This .xls file could not be read. Save it as .xlsx (or export the sheet to PDF/CSV) and try again."
        ) from exc
    parts: list[str] = []
    for sheet in book.sheets():
        rows: list[str] = []
        for r in range(min(sheet.nrows, _XLSX_MAX_ROWS)):
            cells = []
            for v in sheet.row_values(r):
                if isinstance(v, float) and v.is_integer():
                    v = int(v)
                cells.append("" if v == "" else str(v).strip())
            if any(cells):
                rows.append(" | ".join(cells).rstrip(" |"))
        if sheet.nrows > _XLSX_MAX_ROWS:
            rows.append(f"[… sheet '{sheet.name}' truncated after {_XLSX_MAX_ROWS} rows]")
        if rows:
            parts.append(f"--- SHEET: {sheet.name} ---\n" + "\n".join(rows))
    text = "\n\n".join(parts).strip()
    if not text:
        raise DocumentExtractionError("The uploaded .xls file has no readable data.")
    return text


def extract_document_text(data: bytes, filename: str = "", content_type: str = "") -> str:
    """Route supported tender formats to a format-aware extractor."""
    try:  # convert/OCR formats the readers below cannot handle (see document_convert)
        prepared = prepare_upload(data, filename, content_type)
    except ConversionError as exc:
        raise DocumentExtractionError(str(exc)) from exc
    if prepared.text is not None:
        return prepared.text
    data, filename, content_type = prepared.data, prepared.filename, prepared.content_type
    suffix = Path(filename).suffix.casefold()
    mime = (content_type or "").split(";", 1)[0].strip().casefold()
    if suffix == ".pdf" or mime == "application/pdf":
        try:
            return extract_pdf_text(data)
        except PdfExtractionError as exc:
            raise DocumentExtractionError(str(exc)) from exc
    if suffix == ".docx" or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_docx_text(data)
    if suffix in {".txt", ".md", ".csv"} or mime.startswith("text/"):
        text = data.decode("utf-8-sig", errors="replace").strip()
        if text:
            return text
        raise DocumentExtractionError("The uploaded text file is empty.")
    if suffix == ".xlsx" or mime == XLSX_MIME:
        return extract_xlsx_text(data)
    if suffix == ".xls" or mime == "application/vnd.ms-excel":
        # Some browsers send .csv as application/vnd.ms-excel; treat a .csv name as text.
        if suffix == ".csv":
            return data.decode("utf-8-sig", errors="replace").strip()
        return extract_xls_text(data)
    if suffix == ".doc":
        raise DocumentExtractionError(
            "Legacy .doc files are not supported. Save the document as .docx or PDF and upload it again."
        )
    raise DocumentExtractionError(
        "Unsupported tender file type. Upload a PDF, Word, Excel, PowerPoint, OpenDocument, RTF, image, TXT, Markdown, or CSV file."
    )
