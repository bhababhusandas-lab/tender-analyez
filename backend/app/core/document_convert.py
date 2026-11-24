"""Turn tender files the plain readers cannot handle into ones they can.

`document_extract` reads PDF, DOCX, XLSX/XLS and plain text. Tenders also
arrive as old Word files, OpenDocument, RTF, PowerPoint, scans, photos and
RAR/7z bundles. This module bridges the gap with free command-line tools that
are installed in the server image:

* LibreOffice (``soffice --headless``): .doc/.rtf/.odt/.wps -> .docx,
  .ods -> .xlsx, .ppt/.pptx/.odp -> .pdf. The existing readers then do the rest.
* Tesseract OCR (English + Hindi) with poppler's ``pdftoppm`` for scanned PDF
  pages and image files. OCR text is always marked so readers know to check
  figures against the original.
* ``lsar``/``unar`` for .rar and .7z archives, with the same limits as .zip.

Every tool runs in its own temporary folder with a time limit and is cleaned
up afterwards. Failures raise `ConversionError` with a plain-English message
that `document_extract` passes on to the user.
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("document_convert")

PASSWORD_MESSAGE = "This file is password-protected. Remove the password and upload it again."

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MIME = "application/pdf"

TO_DOCX = {".doc", ".rtf", ".odt", ".wps"}
TO_XLSX = {".ods"}
TO_PDF = {".ppt", ".pptx", ".odp"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
ARCHIVE_SUFFIXES = (".zip", ".rar", ".7z")

# Formats that are zip packages themselves; a "PK" header on these is not an archive upload.
_ZIP_BASED_DOCUMENTS = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}

MIME_TO_SUFFIX = {
    "application/msword": ".doc",
    "application/rtf": ".rtf",
    "text/rtf": ".rtf",
    "application/vnd.oasis.opendocument.text": ".odt",
    "application/vnd.oasis.opendocument.spreadsheet": ".ods",
    "application/vnd.oasis.opendocument.presentation": ".odp",
    "application/vnd.ms-works": ".wps",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
    "application/vnd.rar": ".rar",
    "application/x-rar-compressed": ".rar",
    "application/x-7z-compressed": ".7z",
}

CONVERT_TIMEOUT = int(os.getenv("DOC_CONVERT_TIMEOUT", "120"))  # seconds per file
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "300"))
OCR_TIME_BUDGET = int(os.getenv("OCR_TIME_BUDGET", "900"))  # seconds per document
OCR_PAGE_TIMEOUT = 120
OCR_DPI = 300
OCR_WORKERS = max(1, min(4, os.cpu_count() or 1))
ARCHIVE_TIMEOUT = 120

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_RAR_MAGIC = b"Rar!\x1a\x07"
_7Z_MAGIC = b"7z\xbc\xaf\x27\x1c"


class ConversionError(Exception):
    """A file could not be converted; the message is safe to show the user."""


@dataclass
class Prepared:
    """What `document_extract` should read next. `text` set means: done, use it."""

    data: bytes
    filename: str
    content_type: str
    text: str | None = None


def _suffix(filename: str, content_type: str) -> str:
    suffix = Path(filename or "").suffix.casefold()
    if suffix:
        return suffix
    mime = (content_type or "").split(";", 1)[0].strip().casefold()
    return MIME_TO_SUFFIX.get(mime, "")


def prepare_upload(data: bytes, filename: str = "", content_type: str = "") -> Prepared:
    """Convert or OCR a file the plain readers cannot read; pass others through."""
    suffix = _suffix(filename, content_type)
    if is_password_protected(data, suffix):
        raise ConversionError(PASSWORD_MESSAGE)
    stem = Path(filename or "document").stem or "document"
    if suffix in TO_DOCX:
        return Prepared(convert_office(data, suffix, "docx"), f"{stem}.docx", DOCX_MIME)
    if suffix in TO_XLSX:
        return Prepared(convert_office(data, suffix, "xlsx"), f"{stem}.xlsx", XLSX_MIME)
    if suffix in TO_PDF:
        return Prepared(convert_office(data, suffix, "pdf"), f"{stem}.pdf", PDF_MIME)
    if suffix in IMAGE_SUFFIXES:
        return Prepared(data, filename, content_type, text=ocr_image(data))
    return Prepared(data, filename, content_type)


# --------------------------------------------------------------------------- tools


def _tool(*names: str) -> str | None:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def _offline_env(home: str) -> dict[str, str]:
    """A minimal environment: private HOME, and any web fetch sent to a dead proxy."""
    dead = "http://127.0.0.1:9"
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": home,
        "TMPDIR": home,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OMP_THREAD_LIMIT": "1",
        "http_proxy": dead, "https_proxy": dead, "ftp_proxy": dead,
        "HTTP_PROXY": dead, "HTTPS_PROXY": dead, "no_proxy": "", "NO_PROXY": "",
    }


def _run(cmd: list[str], timeout: float, env: dict[str, str] | None = None,
         cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a tool; on timeout kill its whole process group (soffice forks)."""
    proc = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd=cwd, start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.communicate()
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


# ----------------------------------------------------------------- password check


def is_password_protected(data: bytes, suffix: str) -> bool:
    try:
        if data[:5] == b"%PDF-" or suffix == ".pdf":
            return _pdf_needs_password(data)
        if data[:8] == _OLE_MAGIC:
            return _ole_file_encrypted(data)
        if data[:4] == b"PK\x03\x04" and suffix in {".odt", ".ods", ".odp"}:
            return _odf_encrypted(data)
    except Exception as exc:  # a broken file is reported by the reader, not here
        log.info("password check skipped: %s", exc)
    return False


def _pdf_needs_password(data: bytes) -> bool:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if not reader.is_encrypted:
        return False
    try:
        return not reader.decrypt("")  # PasswordType.NOT_DECRYPTED == 0
    except Exception as exc:  # e.g. AES without a crypto library: let the reader try
        log.info("could not test PDF password: %s", exc)
        return False


def _ole_file_encrypted(data: bytes) -> bool:
    import olefile

    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        return _ole_is_encrypted(ole)
    finally:
        ole.close()


def _ole_is_encrypted(ole) -> bool:
    """Encrypted OOXML, Word 97-2003, Excel 97-2003 and PowerPoint 97-2003 files."""
    if ole.exists("EncryptedPackage") or ole.exists("EncryptionInfo"):
        return True  # password-protected .docx/.xlsx/.pptx are OLE containers
    if ole.exists("EncryptedSummary"):
        return True  # PowerPoint
    if ole.exists("WordDocument"):
        fib = ole.openstream("WordDocument").read(12)
        return len(fib) >= 12 and bool(int.from_bytes(fib[10:12], "little") & 0x0100)  # fEncrypted
    for name in ("Workbook", "Book"):
        if ole.exists(name):
            return _biff_has_filepass(ole.openstream(name).read(64 * 1024))
    return False


def _biff_has_filepass(stream: bytes) -> bool:
    pos = 0
    for _ in range(200):
        if pos + 4 > len(stream):
            break
        rtype = int.from_bytes(stream[pos:pos + 2], "little")
        size = int.from_bytes(stream[pos + 2:pos + 4], "little")
        if rtype == 0x002F:  # FILEPASS
            return True
        if rtype == 0x000A:  # EOF of the globals substream
            break
        pos += 4 + size
    return False


def _odf_encrypted(data: bytes) -> bool:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        try:
            manifest = package.read("META-INF/manifest.xml")
        except KeyError:
            return False
    return b"encryption-data" in manifest


# ----------------------------------------------------------- office conversion


_KIND = {".doc": "Word", ".rtf": "RTF", ".odt": "OpenDocument text", ".wps": "Works",
         ".ods": "OpenDocument spreadsheet", ".ppt": "PowerPoint", ".pptx": "PowerPoint",
         ".odp": "OpenDocument presentation"}
_SAVE_AS = {"docx": ".docx or PDF", "xlsx": ".xlsx or CSV", "pdf": "PDF"}


def convert_office(data: bytes, suffix: str, target: str) -> bytes:
    """Convert one office file with LibreOffice headless and return the new file's bytes."""
    kind = _KIND.get(suffix, suffix.lstrip(".").upper())
    advice = f"Save it as {_SAVE_AS[target]} and upload it again."
    soffice = _tool("soffice", "libreoffice")
    if not soffice:
        raise ConversionError(f"This {kind} file ({suffix}) cannot be converted on this server. {advice}")
    with tempfile.TemporaryDirectory(prefix="taa-convert-") as tmp:
        src = Path(tmp, "input" + suffix)
        src.write_bytes(data)
        out_dir = Path(tmp, "out")
        out_dir.mkdir()
        profile = Path(tmp, "profile")
        cmd = [
            soffice, f"-env:UserInstallation={profile.as_uri()}",
            "--headless", "--invisible", "--norestore", "--nologo", "--nodefault",
            "--nolockcheck", "--convert-to", target, "--outdir", str(out_dir), str(src),
        ]
        try:
            result = _run(cmd, CONVERT_TIMEOUT, env=_offline_env(tmp), cwd=tmp)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(
                f"This {kind} file took too long to convert (over {CONVERT_TIMEOUT} seconds). {advice}"
            ) from exc
        produced = out_dir / f"input.{target}"
        if not produced.is_file() or produced.stat().st_size == 0:
            log.warning("soffice failed (%s): %s", result.returncode, (result.stderr or b"")[-500:])
            raise ConversionError(
                f"This {kind} file could not be converted. It may be damaged or password-protected. {advice}"
            )
        return produced.read_bytes()


# ------------------------------------------------------------------------- OCR


def format_ocr_page(page: int, text: str) -> str:
    return f"[Text read by OCR from page {page} — verify figures against the original]\n{text.strip()}"


def ocr_available() -> bool:
    return _tool("tesseract") is not None


@lru_cache(maxsize=1)
def _ocr_languages() -> str:
    try:
        listed = _run([_tool("tesseract") or "tesseract", "--list-langs"], 30)
        langs = set((listed.stdout or b"").decode(errors="replace").split())
    except Exception:
        langs = set()
    chosen = [lang for lang in ("eng", "hin") if lang in langs]
    return "+".join(chosen) or "eng"


def _tesseract(image: Path, work: str) -> str:
    cmd = [_tool("tesseract") or "tesseract", str(image), "stdout", "-l", _ocr_languages(), "--psm", "3"]
    result = _run(cmd, OCR_PAGE_TIMEOUT, env=_offline_env(work))
    if result.returncode != 0:
        log.warning("tesseract failed on %s: %s", image.name, (result.stderr or b"")[-300:])
        return ""
    return (result.stdout or b"").decode("utf-8", errors="replace").strip()


def _render_page(pdf: Path, page: int, work: str) -> Path | None:
    """Render one PDF page to a greyscale PNG at OCR_DPI (poppler, else pypdfium2)."""
    prefix = Path(work, f"page-{page}")
    pdftoppm = _tool("pdftoppm")
    if pdftoppm:
        cmd = [pdftoppm, "-r", str(OCR_DPI), "-gray", "-png", "-f", str(page), "-l", str(page),
               "-singlefile", str(pdf), str(prefix)]
        _run(cmd, OCR_PAGE_TIMEOUT, env=_offline_env(work))
        image = prefix.with_suffix(".png")
        return image if image.is_file() else None
    import pypdfium2 as pdfium  # fallback for machines without poppler

    doc = pdfium.PdfDocument(str(pdf))
    try:
        pil = doc[page - 1].render(scale=OCR_DPI / 72).to_pil().convert("L")
    finally:
        doc.close()
    image = prefix.with_suffix(".png")
    pil.save(image)
    return image


def ocr_pdf_pages(data: bytes, pages: list[int]) -> dict[int, str]:
    """OCR the given 1-based pages of a PDF. Returns {page: text} for pages that yielded text.

    At most OCR_MAX_PAGES pages and OCR_TIME_BUDGET seconds per document; pages
    left over keep whatever text layer they had.
    """
    if not pages or not ocr_available():
        return {}
    todo = pages[:OCR_MAX_PAGES]
    if len(pages) > len(todo):
        log.warning("OCR capped at %d of %d pages", len(todo), len(pages))
    deadline = time.monotonic() + OCR_TIME_BUDGET
    with tempfile.TemporaryDirectory(prefix="taa-ocr-") as tmp:
        pdf = Path(tmp, "input.pdf")
        pdf.write_bytes(data)

        def one(page: int) -> tuple[int, str]:
            if time.monotonic() > deadline:
                return page, ""
            try:
                image = _render_page(pdf, page, tmp)
                if image is None:
                    return page, ""
                try:
                    return page, _tesseract(image, tmp)
                finally:
                    image.unlink(missing_ok=True)
            except Exception as exc:
                log.warning("OCR failed on page %d: %s", page, exc)
                return page, ""

        with ThreadPoolExecutor(max_workers=OCR_WORKERS) as pool:
            results = dict(pool.map(one, todo))
    if time.monotonic() > deadline:
        log.warning("OCR time budget (%ss) reached; some pages were skipped", OCR_TIME_BUDGET)
    return {page: text for page, text in results.items() if text.strip()}


def ocr_image(data: bytes) -> str:
    """OCR a photo or scan (every frame of a multi-page TIFF)."""
    if not ocr_available():
        raise ConversionError(
            "Reading text from images is not available on this server. Upload a text-based PDF or DOCX."
        )
    from PIL import Image, ImageSequence, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ConversionError("This image could not be opened. Check that it is a valid picture file.") from exc
    blocks: list[str] = []
    deadline = time.monotonic() + OCR_TIME_BUDGET
    with tempfile.TemporaryDirectory(prefix="taa-ocr-") as tmp:
        for index, frame in enumerate(ImageSequence.Iterator(image), start=1):
            if index > OCR_MAX_PAGES or time.monotonic() > deadline:
                break
            page = frame.convert("L")
            if page.width < 1200:  # small photos read far better enlarged
                page = page.resize((page.width * 2, page.height * 2))
            path = Path(tmp, f"frame-{index}.png")
            page.save(path)
            text = _tesseract(path, tmp)
            path.unlink(missing_ok=True)
            if text:
                blocks.append(f"--- PAGE {index} ---\n{format_ocr_page(index, text)}")
    if not blocks:
        raise ConversionError(
            "No readable text was found in this image. Upload a clearer scan or a text-based PDF."
        )
    return "\n\n".join(blocks)


# -------------------------------------------------------------------- archives


def archive_kind(filename: str, content_type: str, raw: bytes) -> str | None:
    """'zip', 'rar', '7z' or None. Zip-based documents (.docx, .odt …) are not archives."""
    suffix = _suffix(filename, content_type)
    mime = (content_type or "").split(";", 1)[0].strip().casefold()
    if suffix == ".rar" or raw[:6] == _RAR_MAGIC:
        return "rar"
    if suffix == ".7z" or raw[:6] == _7Z_MAGIC:
        return "7z"
    if suffix == ".zip" or mime in {"application/zip", "application/x-zip-compressed"}:
        return "zip"
    if raw[:4] == b"PK\x03\x04" and suffix not in _ZIP_BASED_DOCUMENTS:
        return "zip"
    return None


def _skip_entry(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return (not base or base.startswith(".") or "__MACOSX" in path
            or base.casefold().endswith(ARCHIVE_SUFFIXES))


def expand_archive(raw: bytes, kind: str, max_entries: int, max_bytes: int) -> list[tuple[str, bytes]]:
    """Expand a .rar/.7z with lsar/unar; same filtering and limits as the zip reader."""
    label = kind.upper() if kind == "rar" else kind
    lsar, unar = _tool("lsar"), _tool("unar")
    if not (lsar and unar):
        raise ConversionError(f"{label} archives cannot be opened on this server. Upload a .zip or the documents directly.")
    with tempfile.TemporaryDirectory(prefix="taa-archive-") as tmp:
        archive = Path(tmp, f"upload.{kind}")
        archive.write_bytes(raw)
        env = _offline_env(tmp)
        try:
            listed = _run([lsar, "-j", str(archive)], ARCHIVE_TIMEOUT, env=env)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(f"This {label} archive took too long to open.") from exc
        try:
            listing = json.loads((listed.stdout or b"{}").decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            listing = {}
        error_text = ((listed.stderr or b"") + (listed.stdout or b"")).decode(errors="replace").casefold()
        contents = listing.get("lsarContents")
        if contents is None:
            if "password" in error_text or "encrypt" in error_text:
                raise ConversionError(PASSWORD_MESSAGE)
            raise ConversionError(f"This {label} archive is corrupt or not a real {label} file.")
        if listing.get("lsarEncrypted") or any(e.get("XADIsEncrypted") for e in contents):
            raise ConversionError(PASSWORD_MESSAGE)

        wanted: list[str] = []
        total = 0
        for entry in contents:
            name = str(entry.get("XADFileName", ""))
            if entry.get("XADIsDirectory") or entry.get("XADIsLink") or _skip_entry(name):
                continue
            total += int(entry.get("XADFileSize") or 0)
            if total > max_bytes:
                raise ConversionError(f"The archive's contents exceed the {max_bytes // (1024 * 1024)} MB limit.")
            if len(wanted) >= max_entries:
                raise ConversionError(f"The archive has more than {max_entries} files; upload the key documents directly.")
            wanted.append(str(entry.get("XADIndex")))
        if not wanted:
            return []

        out_dir = Path(tmp, "out")
        out_dir.mkdir()
        cmd = [unar, "-q", "-f", "-D", "-no-recursion", "-o", str(out_dir),
               "-i", str(archive), *wanted]
        try:
            _run(cmd, ARCHIVE_TIMEOUT, env=env)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(f"This {label} archive took too long to expand.") from exc

        entries: list[tuple[str, bytes]] = []
        written = 0
        for path in sorted(p for p in out_dir.rglob("*") if p.is_file() and not p.is_symlink()):
            relative = path.relative_to(out_dir).as_posix()
            if _skip_entry(relative):
                continue
            written += path.stat().st_size
            if written > max_bytes:  # sizes in the listing can lie
                raise ConversionError(f"The archive's contents exceed the {max_bytes // (1024 * 1024)} MB limit.")
            if len(entries) >= max_entries:
                raise ConversionError(f"The archive has more than {max_entries} files; upload the key documents directly.")
            entries.append((path.name, path.read_bytes()))
        return entries
