"""Conversion, OCR and archive handling for tender uploads.

The command-line tools (soffice, tesseract, pdftoppm, lsar/unar) live in the
server image, not on a developer laptop, so they are faked here; the Docker
integration check exercises the real ones.
"""
import asyncio
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from app.core import document_convert as dc
from app.core import pdf_extract
from app.core.document_extract import DocumentExtractionError, extract_document_text
from app.core.tender_inputs import read_uploads


def _docx_bytes(*paragraphs: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paragraphs)
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def _pdf(*pages: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    for text in pages:
        pdf.add_page()
        if text:
            pdf.multi_cell(0, 6, text)
    return bytes(pdf.output())


def _upload(name, data, ctype=""):
    return UploadFile(file=io.BytesIO(data), filename=name, headers=Headers({"content-type": ctype}))


@pytest.fixture
def fake_soffice(monkeypatch):
    """soffice that 'converts' by writing a prepared file into --outdir."""
    calls = []
    outputs = {"docx": _docx_bytes("Converted tender: EMD Rs 2,00,000"),
               "pdf": _pdf("Converted slides: bid due 15.10.2026 " * 5)}

    def run(cmd, timeout, env=None, cwd=None):
        calls.append(cmd)
        target = cmd[cmd.index("--convert-to") + 1]
        out_dir = Path(cmd[cmd.index("--outdir") + 1])
        if target in outputs:
            (out_dir / f"input.{target}").write_bytes(outputs[target])
        elif target == "xlsx":
            import openpyxl
            wb = openpyxl.Workbook(); wb.active.append(["Item", "Qty"]); wb.active.append(["Pole", 4])
            wb.save(out_dir / "input.xlsx")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(dc, "_tool", lambda *names: "/usr/bin/" + names[0])
    monkeypatch.setattr(dc, "_run", run)
    return calls


# ------------------------------------------------------------------ routing


@pytest.mark.parametrize("name,target", [
    ("old.doc", "docx"), ("letter.rtf", "docx"), ("nit.odt", "docx"), ("works.wps", "docx"),
    ("boq.ods", "xlsx"), ("deck.ppt", "pdf"), ("deck.pptx", "pdf"), ("deck.odp", "pdf"),
])
def test_office_formats_are_converted_by_extension(fake_soffice, name, target):
    text = extract_document_text(b"office bytes", name)
    assert fake_soffice[0][fake_soffice[0].index("--convert-to") + 1] == target
    assert {"docx": "EMD Rs 2,00,000", "xlsx": "Pole | 4", "pdf": "bid due 15.10.2026"}[target] in text


def test_office_conversion_runs_in_private_profile_and_temp_dir(fake_soffice):
    extract_document_text(b"x", "old.doc")
    cmd = fake_soffice[0]
    assert "--headless" in cmd
    profile = next(a for a in cmd if a.startswith("-env:UserInstallation=file://"))
    assert "taa-convert-" in profile
    assert not Path(cmd[-1]).exists()  # temp dir cleaned up


@pytest.mark.parametrize("mime,target", [
    ("application/msword", "docx"), ("application/rtf", "docx"),
    ("application/vnd.oasis.opendocument.spreadsheet", "xlsx"),
    ("application/vnd.ms-powerpoint", "pdf"),
])
def test_office_formats_are_routed_by_mime_without_a_name(fake_soffice, mime, target):
    extract_document_text(b"x", "", mime)
    assert fake_soffice[0][fake_soffice[0].index("--convert-to") + 1] == target


def test_images_are_routed_to_ocr(monkeypatch):
    monkeypatch.setattr(dc, "ocr_image", lambda data: "OCR TEXT")
    for name in ["a.jpg", "a.jpeg", "a.png", "a.tif", "a.tiff", "a.bmp", "a.webp"]:
        assert extract_document_text(b"img", name) == "OCR TEXT"
    assert extract_document_text(b"img", "", "image/png") == "OCR TEXT"


def test_existing_formats_pass_through_unchanged():
    assert extract_document_text(_docx_bytes("Plain DOCX"), "a.docx") == "Plain DOCX"
    assert extract_document_text(b"EMD 5000", "a.txt") == "EMD 5000"


# --------------------------------------------------------- conversion errors


def test_missing_libreoffice_gives_plain_message(monkeypatch):
    monkeypatch.setattr(dc, "_tool", lambda *names: None)
    with pytest.raises(DocumentExtractionError, match=r"Word file \(\.doc\) cannot be converted.*\.docx or PDF"):
        extract_document_text(b"x", "old.doc")


def test_failed_conversion_gives_plain_message(monkeypatch):
    monkeypatch.setattr(dc, "_tool", lambda *names: "/usr/bin/soffice")
    monkeypatch.setattr(dc, "_run", lambda cmd, timeout, env=None, cwd=None:
                        subprocess.CompletedProcess(cmd, 1, b"", b"Error: source file could not be loaded"))
    with pytest.raises(DocumentExtractionError, match="could not be converted"):
        extract_document_text(b"x", "deck.pptx")


def test_conversion_timeout_gives_plain_message(monkeypatch):
    def slow(cmd, timeout, env=None, cwd=None):
        assert timeout == dc.CONVERT_TIMEOUT
        raise subprocess.TimeoutExpired(cmd, timeout)
    monkeypatch.setattr(dc, "_tool", lambda *names: "/usr/bin/soffice")
    monkeypatch.setattr(dc, "_run", slow)
    with pytest.raises(DocumentExtractionError, match="took too long"):
        extract_document_text(b"x", "nit.odt")


def test_run_kills_a_hung_process():
    with pytest.raises(subprocess.TimeoutExpired):
        dc._run(["sleep", "5"], 0.2)


# ---------------------------------------------------------- password message


def test_password_protected_pdf_has_clear_message():
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_pdf("Secret tender text " * 20))))
    writer.encrypt(user_password="s3cret", owner_password="owner", algorithm="RC4-128")
    buf = io.BytesIO(); writer.write(buf)
    with pytest.raises(DocumentExtractionError, match="^This file is password-protected. Remove the password and upload it again.$"):
        extract_document_text(buf.getvalue(), "locked.pdf")


def test_owner_only_pdf_is_still_read():
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_pdf("Open tender text for all bidders " * 10))))
    writer.encrypt(user_password="", owner_password="owner", algorithm="RC4-128")
    buf = io.BytesIO(); writer.write(buf)
    assert "Open tender text" in extract_document_text(buf.getvalue(), "secured.pdf")


class _FakeOle:
    def __init__(self, streams):
        self.streams = streams

    def exists(self, name):
        return name in self.streams

    def openstream(self, name):
        return io.BytesIO(self.streams[name])


def test_encrypted_office_files_are_detected():
    assert dc._ole_is_encrypted(_FakeOle({"EncryptionInfo": b"", "EncryptedPackage": b""}))  # .docx/.xlsx
    assert dc._ole_is_encrypted(_FakeOle({"EncryptedSummary": b""}))  # .ppt
    fib = bytearray(32); fib[10:12] = (0x0100).to_bytes(2, "little")
    assert dc._ole_is_encrypted(_FakeOle({"WordDocument": bytes(fib)}))  # .doc
    assert not dc._ole_is_encrypted(_FakeOle({"WordDocument": bytes(32)}))
    bof = (0x0809).to_bytes(2, "little") + (4).to_bytes(2, "little") + b"\0" * 4
    filepass = (0x002F).to_bytes(2, "little") + (2).to_bytes(2, "little") + b"\0\0"
    assert dc._ole_is_encrypted(_FakeOle({"Workbook": bof + filepass}))  # .xls
    assert not dc._ole_is_encrypted(_FakeOle({"Workbook": bof}))


def test_encrypted_ole_upload_gets_password_message(monkeypatch):
    monkeypatch.setattr(dc, "_ole_file_encrypted", lambda data: True)
    with pytest.raises(DocumentExtractionError, match="password-protected"):
        extract_document_text(dc._OLE_MAGIC + b"rest", "locked.docx")


def test_encrypted_opendocument_is_detected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("META-INF/manifest.xml", '<manifest:encryption-data manifest:checksum="x"/>')
    with pytest.raises(DocumentExtractionError, match="password-protected"):
        extract_document_text(buf.getvalue(), "locked.odt")


# ------------------------------------------------------------------- OCR


def test_ocr_marker_format():
    assert dc.format_ocr_page(3, "  EMD Rs 50,000\n") == (
        "[Text read by OCR from page 3 — verify figures against the original]\nEMD Rs 50,000"
    )


def test_only_pages_without_text_are_ocrd_and_marked(monkeypatch):
    asked = []

    def fake_ocr(data, pages):
        asked.extend(pages)
        return {2: "Scanned annexure: turnover Rs 5 crore"}

    monkeypatch.setattr(dc, "ocr_pdf_pages", fake_ocr)
    monkeypatch.setattr(pdf_extract, "_ocr_pages", lambda data: pytest.fail("vision must not run"))
    text = extract_document_text(_pdf("Notice inviting tender. " * 10, ""), "mixed.pdf")
    assert asked == [2]
    assert "--- PAGE 1 ---\nNotice inviting tender." in text
    assert ("--- PAGE 2 ---\n[Text read by OCR from page 2 — verify figures against the original]\n"
            "Scanned annexure: turnover Rs 5 crore") in text


def test_vision_is_only_a_fallback_when_configured(monkeypatch):
    monkeypatch.setattr(dc, "ocr_pdf_pages", lambda data, pages: {})
    monkeypatch.setattr(pdf_extract, "_vision_configured", lambda: False)
    monkeypatch.setattr(pdf_extract, "_ocr_pages", lambda data: pytest.fail("vision not configured"))
    with pytest.raises(DocumentExtractionError, match="Could not read any text"):
        extract_document_text(_pdf("", ""), "scan.pdf")

    monkeypatch.setattr(pdf_extract, "_vision_configured", lambda: True)
    monkeypatch.setattr(pdf_extract, "_ocr_pages", lambda data: "--- PAGE 1 ---\nvision text")
    assert extract_document_text(_pdf("", ""), "scan.pdf") == "--- PAGE 1 ---\nvision text"


def test_ocr_pdf_pages_caps_pages_and_renders_each(monkeypatch):
    rendered = []

    def fake_render(pdf, page, work):
        rendered.append(page)
        path = Path(work, f"p{page}.png"); path.write_bytes(b"png"); return path

    monkeypatch.setattr(dc, "ocr_available", lambda: True)
    monkeypatch.setattr(dc, "_render_page", fake_render)
    monkeypatch.setattr(dc, "_tesseract", lambda image, work: f"text of {image.name}")
    monkeypatch.setattr(dc, "OCR_MAX_PAGES", 3)
    found = dc.ocr_pdf_pages(b"%PDF-", [2, 4, 6, 8])
    assert sorted(rendered) == [2, 4, 6]
    assert found == {2: "text of p2.png", 4: "text of p4.png", 6: "text of p6.png"}


def test_tesseract_uses_english_and_hindi(monkeypatch):
    seen = []

    def run(cmd, timeout, env=None, cwd=None):
        seen.append(cmd)
        if "--list-langs" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"List of available languages (3):\neng\nhin\nosd\n", b"")
        return subprocess.CompletedProcess(cmd, 0, "बोली EMD 500".encode(), b"")

    monkeypatch.setattr(dc, "_tool", lambda *names: "/usr/bin/" + names[0])
    monkeypatch.setattr(dc, "_run", run)
    dc._ocr_languages.cache_clear()
    try:
        assert dc._tesseract(Path("/x/page.png"), "/tmp") == "बोली EMD 500"
    finally:
        dc._ocr_languages.cache_clear()
    assert seen[-1][seen[-1].index("-l") + 1] == "eng+hin"


def test_image_ocr_marks_each_page(monkeypatch):
    from PIL import Image

    buf = io.BytesIO(); Image.new("RGB", (800, 400), "white").save(buf, "PNG")
    monkeypatch.setattr(dc, "ocr_available", lambda: True)
    monkeypatch.setattr(dc, "_tesseract", lambda image, work: "Tender No. 12/2026")
    text = extract_document_text(buf.getvalue(), "photo.png")
    assert text == ("--- PAGE 1 ---\n[Text read by OCR from page 1 — verify figures against the original]\n"
                    "Tender No. 12/2026")


def test_image_without_ocr_or_text_gives_plain_message(monkeypatch):
    from PIL import Image

    buf = io.BytesIO(); Image.new("RGB", (100, 100), "white").save(buf, "PNG")
    monkeypatch.setattr(dc, "ocr_available", lambda: False)
    with pytest.raises(DocumentExtractionError, match="not available on this server"):
        extract_document_text(buf.getvalue(), "a.png")
    monkeypatch.setattr(dc, "ocr_available", lambda: True)
    monkeypatch.setattr(dc, "_tesseract", lambda image, work: "")
    with pytest.raises(DocumentExtractionError, match="No readable text"):
        extract_document_text(buf.getvalue(), "a.png")
    with pytest.raises(DocumentExtractionError, match="could not be opened"):
        extract_document_text(b"\x89PNG broken", "a.png")


# --------------------------------------------------------------- archives


def test_archive_kind_by_name_mime_and_magic():
    assert dc.archive_kind("t.rar", "", b"") == "rar"
    assert dc.archive_kind("upload", "", b"Rar!\x1a\x07\x01\x00") == "rar"
    assert dc.archive_kind("t.7z", "", b"") == "7z"
    assert dc.archive_kind("upload", "", b"7z\xbc\xaf\x27\x1c") == "7z"
    assert dc.archive_kind("t.zip", "", b"") == "zip"
    assert dc.archive_kind("upload", "application/zip", b"") == "zip"
    assert dc.archive_kind("upload", "", b"PK\x03\x04") == "zip"
    for name in ["a.docx", "a.xlsx", "a.pptx", "a.odt", "a.ods", "a.odp"]:
        assert dc.archive_kind(name, "", b"PK\x03\x04rest") is None


def test_docx_upload_is_read_as_a_document_not_a_zip():
    docs, errors = asyncio.run(read_uploads([_upload("NIT.docx", _docx_bytes("EMD Rs 1 lakh"))]))
    assert errors == []
    assert docs[0].text == "EMD Rs 1 lakh"


def _fake_unar(monkeypatch, contents, files, *, lsar_stdout=None, lsar_stderr=b""):
    """lsar returns `contents`; unar writes `files` (relative path -> bytes)."""
    calls = []

    def run(cmd, timeout, env=None, cwd=None):
        calls.append(cmd)
        if cmd[0].endswith("lsar"):
            out = lsar_stdout if lsar_stdout is not None else json.dumps({"lsarContents": contents}).encode()
            return subprocess.CompletedProcess(cmd, 0, out, lsar_stderr)
        out_dir = Path(cmd[cmd.index("-o") + 1])
        wanted = cmd[cmd.index("-i") + 2:]
        for entry in contents:
            name = entry["XADFileName"]
            if str(entry["XADIndex"]) in wanted and name in files:
                (out_dir / name).parent.mkdir(parents=True, exist_ok=True)
                (out_dir / name).write_bytes(files[name])
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(dc, "_tool", lambda *names: "/usr/bin/" + names[0])
    monkeypatch.setattr(dc, "_run", run)
    return calls


def _entry(i, name, size=10, **flags):
    return {"XADIndex": i, "XADFileName": name, "XADFileSize": size, **flags}


@pytest.mark.parametrize("name", ["tender.rar", "tender.7z"])
def test_rar_and_7z_are_expanded_and_filtered(monkeypatch, name):
    contents = [_entry(0, "NIT.txt"), _entry(1, "annex/BOQ.txt"), _entry(2, "__MACOSX/._NIT.txt"),
                _entry(3, ".hidden.txt"), _entry(4, "inner.zip"), _entry(5, "annex", 0, XADIsDirectory=1),
                _entry(6, "inner.rar")]
    files = {"NIT.txt": b"Bid due 15.10.2026", "annex/BOQ.txt": b"Item | Qty"}
    calls = _fake_unar(monkeypatch, contents, files)
    docs, errors = asyncio.run(read_uploads([_upload(name, b"archive bytes")]))
    assert errors == []
    assert sorted(d.filename for d in docs) == ["BOQ.txt", "NIT.txt"]
    unar = calls[-1]
    assert unar[unar.index("-i") + 2:] == ["0", "1"]
    assert "-no-recursion" in unar


def test_archive_entry_limit(monkeypatch):
    contents = [_entry(i, f"f{i}.txt") for i in range(26)]
    _fake_unar(monkeypatch, contents, {})
    docs, errors = asyncio.run(read_uploads([_upload("many.rar", b"x")]))
    assert docs == [] and "more than 25 files" in errors[0]


def test_archive_size_limit_from_listing(monkeypatch):
    _fake_unar(monkeypatch, [_entry(0, "big.pdf", 201 * 1024 * 1024)], {})
    docs, errors = asyncio.run(read_uploads([_upload("big.7z", b"x")]))
    assert docs == [] and "200 MB" in errors[0]


def test_archive_size_limit_on_disk(monkeypatch):
    _fake_unar(monkeypatch, [_entry(0, "a.txt", 1)], {"a.txt": b"x" * (1024 * 1024 + 1)})
    with pytest.raises(dc.ConversionError, match="1 MB limit"):
        dc.expand_archive(b"x", "rar", 25, 1024 * 1024)


def test_encrypted_archive_gets_password_message(monkeypatch):
    _fake_unar(monkeypatch, [_entry(0, "a.txt", XADIsEncrypted=1)], {})
    docs, errors = asyncio.run(read_uploads([_upload("locked.rar", b"x")]))
    assert errors == ["locked.rar: " + dc.PASSWORD_MESSAGE]
    _fake_unar(monkeypatch, [], {}, lsar_stdout=b"", lsar_stderr=b"This archive requires a password to unpack.")
    docs, errors = asyncio.run(read_uploads([_upload("locked.7z", b"x")]))
    assert errors == ["locked.7z: " + dc.PASSWORD_MESSAGE]


def test_corrupt_archive_and_missing_tool(monkeypatch):
    _fake_unar(monkeypatch, [], {}, lsar_stdout=b"Couldn't open archive.")
    docs, errors = asyncio.run(read_uploads([_upload("bad.rar", b"x")]))
    assert "corrupt" in errors[0]
    monkeypatch.setattr(dc, "_tool", lambda *names: None)
    docs, errors = asyncio.run(read_uploads([_upload("t.7z", b"x")]))
    assert "cannot be opened on this server" in errors[0]


def test_zip_skips_nested_rar_and_7z():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("NIT.txt", "EMD 5000"); z.writestr("more.rar", "x"); z.writestr("more.7z", "x")
    docs, errors = asyncio.run(read_uploads([_upload("t.zip", buf.getvalue())]))
    assert [d.filename for d in docs] == ["NIT.txt"] and errors == []
