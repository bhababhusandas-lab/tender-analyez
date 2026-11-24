# Unique Type

Upload a government tender (PDF, scanned PDF, Word, Excel, images or a ZIP of them) and a team of
**11 AI specialists** analyses it end to end, then a QA reviewer checks the result before it is shown.

| Specialist | What it produces |
|---|---|
| Tender Brief | Key dates, EMD, scope and who may bid |
| Bid Manager | Eligibility score and bid / no-bid view |
| Market Intelligence | Competition and pricing context |
| Legal & Compliance | Compliance matrix and risky clauses |
| Govt Relations | Department, approvals and process |
| Technical Expert | Technical requirements and gaps |
| Technical Writer | Proposal outline |
| Finance & Accounts | Financial eligibility and cash flow |
| Bid Pricing | BOQ costing and price band |
| Document Controller | Document checklist |
| Admin / HR | Manpower and certifications |
| QA Reviewer | Checks every claim against the tender text |

## Features
- **Reads every common tender format**: text PDFs, scanned PDFs and images (OCR in English and Hindi),
  .doc/.docx, .xls/.xlsx, .ppt, RTF, OpenDocument, ZIP/RAR/7z.
- **Evidence-grounded answers**: deterministic checks block claims that are not supported by the tender.
- **Live progress**: each specialist's step streams to the dashboard as it finishes.
- **Tender history** with versions, re-analysis after a corrigendum, and PDF export.
- **Bid tracker, document vault** (expiry tracking for certificates) and **company profile** used for fit scoring.
- **Discussion panel** to ask follow-up questions about a finished analysis.
- **Private AI**: runs on open-weight models through Ollama (default `qwen3:8b`), so tender documents never
  leave your own server. Several GPU servers can be listed; the first that answers is used.

## Tech stack
- **Backend:** Python, FastAPI, SQLAlchemy (SQLite), OpenAI-compatible client to Ollama
- **Frontend:** React, TypeScript, Vite, Tailwind CSS
- **Document pipeline:** pypdf, LibreOffice (headless), Tesseract OCR, poppler, unar
- **Tests:** pytest (349 tests)

## Run it

### With Docker
```bash
ollama pull qwen3:8b        # once, on the machine running Ollama
docker compose up --build   # then open http://localhost:8000
```

### Without Docker
```bash
# Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # set JWT_SECRET; point OLLAMA_BASE_URL at your Ollama
.venv/bin/uvicorn app.main:app --port 8001

# Frontend (second terminal)
cd frontend
npm install && npm run dev    # http://localhost:3000 (calls the backend on 8001)
```

The first account created with the email in `ADMIN_EMAILS` (default `admin@example.com`) is an
administrator and skips email verification.

### Tests
```bash
cd backend && .venv/bin/python -m pytest -q
```

## Project layout
```
backend/app/api/v1     REST endpoints (analysis, history, documents, auth, export)
backend/app/core       document reading, grounding checks, LLM router, database
backend/app/evals      per-specialist quality checks
backend/training       evaluation cases for each specialist
frontend/src/pages     dashboard screens
frontend/src/bidroom   live multi-agent analysis view
```
