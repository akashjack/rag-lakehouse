"""Health check endpoint."""

from __future__ import annotations

import httpx
import oracledb
from fastapi import APIRouter
from pydantic import BaseModel

from api.config import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    oracle: str
    ollama: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()

    # Check Oracle
    try:
        conn = oracledb.connect(
            user=settings.oracle_user,
            password=settings.oracle_password,
            dsn=settings.oracle_dsn,
        )
        conn.close()
        oracle_status = "up"
    except Exception as e:
        oracle_status = f"down: {e}"

    # Check Ollama
    try:
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5)
        r.raise_for_status()
        ollama_status = "up"
    except Exception as e:
        ollama_status = f"down: {e}"

    overall = "ok" if oracle_status == "up" and ollama_status == "up" else "degraded"
    return HealthResponse(status=overall, oracle=oracle_status, ollama=ollama_status)
