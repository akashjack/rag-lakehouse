"""FastAPI gateway for the RAG lakehouse.

Endpoints:
  GET  /health          — Oracle + Ollama liveness check
  GET  /search?q=...    — Dense or hybrid retrieval (JSON)
  POST /ask             — SSE streaming LLM answer
"""

from __future__ import annotations

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.metrics import router as metrics_router
from api.routes.ask import router as ask_router
from api.routes.health import router as health_router
from api.routes.search import router as search_router

log = structlog.get_logger(__name__)

app = FastAPI(
    title="RAG Lakehouse API",
    description="Hybrid retrieval + LLM generation over Kubernetes, Spring, Angular docs",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router)
app.include_router(health_router)
app.include_router(search_router)
app.include_router(ask_router)


@app.on_event("startup")
async def startup() -> None:
    log.info("api.startup", version="0.1.0")


if __name__ == "__main__":
    from api.config import get_settings

    s = get_settings()
    uvicorn.run("api.main:app", host=s.host, port=s.port, reload=s.debug)
