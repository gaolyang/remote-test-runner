from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.cases import router as cases_router
from backend.api.sessions import router as sessions_router
from backend.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Remote Test Runner & Evidence Collector", version="0.1.0")
app.include_router(cases_router)
app.include_router(sessions_router)
app.mount("/assets", StaticFiles(directory=settings.frontend_dir), name="assets")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(settings.frontend_dir / "index.html")

