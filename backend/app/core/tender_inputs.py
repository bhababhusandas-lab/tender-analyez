"""Read and extract uploaded tender documents.

Shared by a new analysis and a re-analysis. Raw bytes are kept so the caller
can store the original file in the tender's history. A .zip, .rar or .7z upload is expanded
and each supported file inside it is read as its own document.
"""
import asyncio
import io
import zipfile
from dataclasses import dataclass

from fastapi import UploadFile

from app.core.document_convert import ARCHIVE_SUFFIXES, ConversionError, archive_kind, expand_archive
from app.core.document_extract import DocumentExtractionError, extract_document_text

MAX_FILES = 10
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_ZIP_ENTRIES = 25            # guard against zips with thousands of files
MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024  # guard against zip bombs


@dataclass
class UploadedDoc:
    filename: str
    mime_type: str
    raw: bytes
    text: str


def source_block(doc: UploadedDoc) -> str:
    """The marker format `tender_evidence.SOURCE_RE` recognises for citations."""
    return f"--- SOURCE DOCUMENT: {doc.filename} ---\n{doc.text}"


def _zip_entries(raw: bytes) -> list[tuple[str, bytes]]:
    """Return (name, bytes) for each real, supported-looking file in the zip.

    Directories, macOS metadata, hidden files, nested archives and the zip's
    own total uncompressed size are filtered/guarded here.
    """
    entries: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        total = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            base = info.filename.rsplit("/", 1)[-1]
            if not base or base.startswith(".") or "__MACOSX" in info.filename:
                continue
            if base.casefold().endswith(ARCHIVE_SUFFIXES):
                continue  # don't recurse into nested archives
            total += info.file_size
            if total > MAX_ZIP_UNCOMPRESSED:
                raise DocumentExtractionError("The zip's contents exceed the 200 MB limit.")
            if len(entries) >= MAX_ZIP_ENTRIES:
                raise DocumentExtractionError(f"The zip has more than {MAX_ZIP_ENTRIES} files; upload the key documents directly.")
            entries.append((base, zf.read(info)))
    return entries


def _extract_one(name: str, raw: bytes, mime: str) -> tuple[UploadedDoc | None, str | None]:
    try:
        text = extract_document_text(raw, name, mime)
        return UploadedDoc(name, mime or "application/octet-stream", raw, text), None
    except DocumentExtractionError as exc:
        return None, f"{name}: {exc}"
    except Exception as exc:
        return None, f"{name}: Could not read this document: {exc}"


def _read_sync(name: str, mime: str, raw: bytes) -> tuple[list[UploadedDoc], list[str], int]:
    """Process one uploaded file (expanding a zip/rar/7z) into docs + errors + bytes used."""
    docs: list[UploadedDoc] = []
    errors: list[str] = []
    kind = archive_kind(name, mime, raw)  # .docx/.xlsx are zips too, but not archives
    if kind:
        label = "zip" if kind == "zip" else "archive"
        try:
            if kind == "zip":
                entries = _zip_entries(raw)
            else:
                entries = expand_archive(raw, kind, MAX_ZIP_ENTRIES, MAX_ZIP_UNCOMPRESSED)
        except (DocumentExtractionError, ConversionError) as exc:
            return [], [f"{name}: {exc}"], len(raw)
        except zipfile.BadZipFile:
            return [], [f"{name}: this zip file is corrupt or not a real zip."], len(raw)
        if not entries:
            return [], [f"{name}: the {label} has no readable documents."], len(raw)
        used = 0
        for inner_name, inner_raw in entries:
            used += len(inner_raw)
            doc, err = _extract_one(inner_name, inner_raw, "")
            (docs.append(doc) if doc else errors.append(err))
        return docs, errors, used
    doc, err = _extract_one(name, raw, mime)
    return ([doc] if doc else []), ([err] if err else []), len(raw)


async def read_uploads(uploads: list[UploadFile]) -> tuple[list[UploadedDoc], list[str]]:
    if len(uploads) > MAX_FILES:
        return [], [f"Upload at most {MAX_FILES} files per analysis."]
    docs: list[UploadedDoc] = []
    errors: list[str] = []
    total = 0
    for upload in uploads:
        name = upload.filename or "unnamed"
        raw = await upload.read()
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            errors.append("The combined upload size exceeds the 50 MB limit.")
            break
        more_docs, more_errors, _ = await asyncio.to_thread(
            _read_sync, name, upload.content_type or "", raw
        )
        docs.extend(more_docs)
        errors.extend(more_errors)
    return docs, errors
