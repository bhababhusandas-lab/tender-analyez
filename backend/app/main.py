import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.v1.chat import router as chat_router
from app.api.v1.agents import router as agents_router
from app.api.v1.documents import router as documents_router
from app.api.v1.tender_analysis import router as tender_router
from app.api.v1.tender_roadmap import router as roadmap_router
from app.api.v1.auth import router as auth_router
from app.api.v1.admin import router as admin_router
from app.api.v1.usage import router as usage_router
from app.api.v1.discussion import router as discussion_router
from app.api.v1.company import router as company_router
from app.api.v1.bids import router as bids_router
from app.api.v1.past_bids import router as past_bids_router
from app.api.v1.export import router as export_router
from app.api.v1.analysis_jobs import router as analysis_jobs_router
from app.api.v1.tenders import router as tenders_router
from app.api.v1.notifications import router as notifications_router
from app.core.db.session import engine
from app.core.db import models
from app.core.db.migrate import ensure_schema
from app.core.response_compression import AdaptiveCompressionMiddleware
from app.core.tender_history import backfill_from_bids

models.Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="Unique Type", version="2.0.0")
app.add_middleware(AdaptiveCompressionMiddleware, minimum_size=1024)

# === Per-IP rate limiting ===
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.core.ratelimit import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _run_backfill() -> None:
    try:
        backfilled = backfill_from_bids()
        if backfilled:
            print(f"[history] added {backfilled} Bid Tracker entries to tender history")
    except Exception as exc:  # never let a history backfill take the app down
        print(f"[history] backfill skipped: {exc}")


@app.on_event("startup")
async def _enlarge_thread_pool() -> None:
    # Default ThreadPoolExecutor is small (cpu+4). Enlarge so all 7 phases can run in parallel.
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=32))
    # Backfill runs in a background thread so a slow/large backfill never delays startup.
    threading.Thread(target=_run_backfill, daemon=True).start()



app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

for r in [auth_router, admin_router, usage_router, discussion_router, chat_router, agents_router, documents_router, tender_router, roadmap_router,
          company_router, bids_router, past_bids_router, export_router, analysis_jobs_router, tenders_router, notifications_router]:
    app.include_router(r, prefix="/api/v1")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Unique Type"}


# Dynamic config.js — reads SITE_URL env var so we can change API URL without redeploying
import os as _os
from fastapi.responses import PlainTextResponse

@app.get("/config.js")
async def config_js():
    site_url = _os.getenv("SITE_URL", "")
    js = f'window.API_URL = "{site_url}";\n'
    return PlainTextResponse(js, media_type="application/javascript")


# Serve React frontend static files
STATIC_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file() and full_path != "config.js":
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
