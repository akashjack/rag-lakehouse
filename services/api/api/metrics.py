"""Prometheus metrics for the RAG API."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# ===== Metrics =====
REQUEST_COUNT = Counter(
    "rag_api_requests_total",
    "Total API requests",
    ["endpoint", "method", "status"],
)

RETRIEVAL_LATENCY = Histogram(
    "rag_retrieval_latency_seconds",
    "Time spent on retrieval (embed + search)",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

LLM_LATENCY = Histogram(
    "rag_llm_latency_seconds",
    "Time spent on LLM generation",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

SEARCH_RESULT_COUNT = Histogram(
    "rag_search_result_count",
    "Number of chunks returned per search",
    buckets=[1, 2, 3, 5, 10, 20],
)

# ===== /metrics endpoint =====
router = APIRouter()


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
