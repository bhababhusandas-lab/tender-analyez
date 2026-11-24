# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS application
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Tools for reading every common tender format (see app/core/document_convert.py):
# LibreOffice without the GUI converts .doc/.rtf/.odt/.wps/.ods/.ppt/.pptx/.odp;
# Tesseract (English + Hindi) and poppler OCR scanned PDFs and images; unar opens
# .rar/.7z. Noto fonts cover Devanagari so converted Hindi text keeps its glyphs.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
        fonts-noto-core fonts-dejavu-core \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
        poppler-utils unar && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*

WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend-build /src/frontend/dist ./frontend/dist

RUN mkdir -p /data/uploads && \
    useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000
CMD ["gunicorn", "app.main:app", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "1800", "--graceful-timeout", "60", "--keep-alive", "75", "--access-logfile", "-", "--error-logfile", "-"]
