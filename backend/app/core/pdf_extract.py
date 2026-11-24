"""Tender PDF -> text.

Three paths, cheapest first:

1. pypdf text layer. Free and instant. Works for digitally-generated tenders,
   which is most of what GeM and CPPP serve.
2. Tesseract OCR (English + Hindi) for pages with little or no text — scanned
   tenders, or scanned annexures inside an otherwise digital PDF. Only those
   pages are OCR'd, and each is marked so readers verify figures (see
   `document_convert.ocr_pdf_pages`).
3. Vision model transcription, only if OCR is unavailable or still found
   nothing and a vision model is configured.
"""
import io
import base64
import logging

log = logging.getLogger("pdf_extract")

# Below this many characters per page we assume there is no usable text layer.
MIN_CHARS_PER_PAGE = 120

# Cap pages sent to the vision model — a 300-page tender would otherwise be
# both slow and expensive. The first pages carry the NIT, eligibility and BOQ.
MAX_OCR_PAGES = 20

OCR_PROMPT = (
    "This is a page from an Indian government tender document. "
    "Transcribe ALL text faithfully and completely. "
    "Render every table as a markdown table using | delimiters, preserving all "
    "columns and rows. Reproduce every number, amount, date, percentage and "
    "reference code exactly as printed — do not round, reformat or summarise. "
    "Output only the transcription, no commentary."
)


class PdfExtractionError(Exception):
    """Raised when a PDF yields no usable text by any method."""


# A page with fewer readable characters than this is treated as scanned and OCR'd.
OCR_PAGE_MIN_CHARS = 40


def _page_texts(data: bytes) -> list[str]:
    """Each page's embedded text layer ("" for pages without one)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    texts: list[str] = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception as e:  # one bad page must not lose the rest
            log.warning("pypdf could not read a page: %s", e)
            texts.append("")
    return texts


def _label(pages: list[str]) -> str:
    return "\n\n".join(f"--- PAGE {index} ---\n{page}" for index, page in enumerate(pages, start=1))


def _text_layer(data: bytes) -> tuple[str, int]:
    """Return (text, page_count) from the PDF's embedded text layer."""
    pages = _page_texts(data)
    return _label(pages), len(pages)


def _with_tesseract(data: bytes, pages: list[str]) -> list[str]:
    """Replace thin pages with marked OCR text where Tesseract can read them."""
    from app.core.document_convert import format_ocr_page, ocr_pdf_pages

    thin = [i for i, text in enumerate(pages, start=1) if len("".join(text.split())) < OCR_PAGE_MIN_CHARS]
    if not thin:
        return pages
    log.info("OCR for %d of %d pages with little or no text", len(thin), len(pages))
    found = ocr_pdf_pages(data, thin)
    return [format_ocr_page(i, found[i]) if i in found else text for i, text in enumerate(pages, start=1)]


def _render_pages(data: bytes, max_pages: int, dpi: int = 150) -> list[str]:
    """Rasterise pages to base64 PNGs for the vision model."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(io.BytesIO(data))
    images: list[str] = []
    for page in list(doc)[:max_pages]:
        pil = page.render(scale=dpi / 72).to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        images.append(base64.b64encode(buf.getvalue()).decode())
    return images


def _ocr_pages(data: bytes) -> str:
    """Transcribe a scanned PDF with a vision-capable model."""
    from app.core.llm.claude_client import vision_chat

    images = _render_pages(data, MAX_OCR_PAGES)
    if not images:
        return ""

    out: list[str] = []
    for i, b64 in enumerate(images, start=1):
        try:
            page_text = vision_chat(OCR_PROMPT, b64)
        except Exception as e:
            log.warning("OCR failed on page %d: %s", i, e)
            # Keep whatever earlier pages produced rather than losing everything.
            break
        if page_text.strip():
            out.append(f"--- PAGE {i} ---\n{page_text.strip()}")
    return "\n\n".join(out)


def extract_pdf_text(data: bytes) -> str:
    """Best-effort text for a tender PDF.

    Raises PdfExtractionError when nothing readable comes out, so the caller can
    tell the user their file could not be read instead of silently analysing an
    empty document.
    """
    page_texts: list[str] = []
    try:
        page_texts = _page_texts(data)
    except Exception as e:
        log.warning("pypdf could not read the file: %s", e)
    pages = len(page_texts)

    try:
        page_texts = _with_tesseract(data, page_texts)
    except Exception as e:
        log.error("Tesseract OCR failed: %s", e)
    text = _label(page_texts) if pages else ""

    readable = len("".join("".join(page_texts).split()))
    usable = pages > 0 and readable >= MIN_CHARS_PER_PAGE * pages
    if usable:
        return text

    ocr = ""
    if _vision_configured():
        log.info(
            "Text thin after OCR (%d chars over %d pages) — trying vision transcription",
            readable, pages,
        )
        try:
            ocr = _ocr_pages(data)
        except Exception as e:
            log.error("Vision OCR failed: %s", e)

    # Prefer whichever produced more content; a partial text layer can still
    # beat a failed OCR run.
    best = max((text or "").strip() if readable else "", (ocr or "").strip(), key=len)
    if not best:
        raise PdfExtractionError(
            "Could not read any text from this PDF. If it is a scanned "
            "document, check that it is not password-protected, then try "
            "re-uploading. You can also paste the tender text directly."
        )
    return best


def _vision_configured() -> bool:
    try:
        from app.core.config import settings

        return any(settings.models_for(p).get("vision") for p in settings.configured_providers())
    except Exception:
        return False
