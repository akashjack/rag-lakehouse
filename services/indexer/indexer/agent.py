"""LangGraph multi-agent RAG orchestrator.

Graph: START -> router -> retriever -> generator -> reranker -> END
                              ^                          |
                              |______ retry (once) _______|

Nodes
- router:    heuristic intent classifier, may rewrite the query
- retriever: hybrid_search() via OllamaEmbedder
- generator: ask() from rag_chain, collects streamed tokens
- reranker:  quality check; retries once with simplified query if poor
"""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from indexer.config import IndexerSettings
from indexer.embedders.ollama_embedder import OllamaEmbedder
from indexer.rag_chain import ask, build_citations
from indexer.store.connection import build_pool
from indexer.store.repository import hybrid_search

log = structlog.get_logger(__name__)


# =========================================================================
# State
# =========================================================================


class AgentState(TypedDict):
    question: str
    augmented_question: str
    intent: str
    query_vector: list[float]
    chunks: list[dict[str, Any]]
    answer_parts: list[str]
    citations: list[dict[str, Any]]
    retry_count: int
    final_answer: str


# =========================================================================
# Nodes
# =========================================================================


def router_node(state: AgentState) -> dict[str, Any]:
    q = state["question"].strip()
    words = q.lower().split()

    multi_hop_signals = {"compare", "difference", "versus", "vs", "both", "relationship"}
    ambiguous_signals = {"it", "this", "that", "they", "them"}

    if any(w in multi_hop_signals for w in words):
        intent = "multi_hop"
        augmented = q
    elif len(words) <= 3 and any(w in ambiguous_signals for w in words):
        intent = "ambiguous"
        augmented = f"explain in detail: {q}"
    else:
        intent = "factual"
        augmented = q

    log.info("agent.router", intent=intent, augmented=augmented)
    return {"intent": intent, "augmented_question": augmented}


def make_retriever_node(settings: IndexerSettings, pool):
    def retriever_node(state: AgentState) -> dict[str, Any]:
        q = state["augmented_question"]
        with OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embed_model,
            dimension=settings.embedding_dim,
            timeout_seconds=settings.embed_timeout_seconds,
        ) as embedder:
            query_vector = embedder.embed_batch([q])[0]

        chunks = hybrid_search(
            pool,
            query_vector=query_vector,
            query_text=q,
            k=settings.rag_top_k,
            embedding_model_ver=settings.embedding_model_version,
        )
        log.info("agent.retriever", chunks=len(chunks), query=q)
        return {"query_vector": query_vector, "chunks": chunks}

    return retriever_node


def make_generator_node(settings: IndexerSettings):
    def generator_node(state: AgentState) -> dict[str, Any]:
        chunks = state["chunks"]
        question = state["augmented_question"]
        parts: list[str] = []
        for token in ask(settings, chunks, question):
            parts.append(token)
        answer = "".join(parts)
        citations = build_citations(chunks, settings.rag_max_context_chars)
        log.info("agent.generator", answer_chars=len(answer), citations=len(citations))
        return {"answer_parts": parts, "citations": citations, "final_answer": answer}

    return generator_node


def make_reranker_node(settings: IndexerSettings, pool):
    def reranker_node(state: AgentState) -> dict[str, Any]:
        answer = state.get("final_answer", "")
        retry_count = state.get("retry_count", 0)
        no_info_phrases = [
            "i don't have enough information",
            "not in the context",
            "cannot find",
            "no relevant",
        ]
        is_poor = len(answer.strip()) < 30 or any(p in answer.lower() for p in no_info_phrases)
        if is_poor and retry_count == 0:
            words = [w for w in state["augmented_question"].split() if len(w) > 3]
            fallback = words[0] if words else state["augmented_question"]
            log.info("agent.reranker.retry", fallback=fallback)
            return {"augmented_question": fallback, "retry_count": retry_count + 1}
        log.info("agent.reranker.accept", answer_chars=len(answer), retries=retry_count)
        return {"retry_count": retry_count}

    return reranker_node


def _should_retry(state: AgentState) -> str:
    answer = state.get("final_answer", "")
    retry_count = state.get("retry_count", 0)
    no_info_phrases = [
        "i don't have enough information",
        "not in the context",
        "cannot find",
        "no relevant",
    ]
    is_poor = len(answer.strip()) < 30 or any(p in answer.lower() for p in no_info_phrases)
    if is_poor and retry_count == 1:
        return "retriever"
    return END


# =========================================================================
# Graph
# =========================================================================


def build_graph(settings: IndexerSettings):
    pool = build_pool(settings)
    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("retriever", make_retriever_node(settings, pool))
    graph.add_node("generator", make_generator_node(settings))
    graph.add_node("reranker", make_reranker_node(settings, pool))
    graph.add_edge(START, "router")
    graph.add_edge("router", "retriever")
    graph.add_edge("retriever", "generator")
    graph.add_edge("generator", "reranker")
    graph.add_conditional_edges("reranker", _should_retry)
    return graph.compile(), pool


def run_agent(settings: IndexerSettings, question: str) -> dict[str, Any]:
    """Run the full agent graph and return the final state."""
    agent, pool = build_graph(settings)
    initial_state: AgentState = {
        "question": question,
        "augmented_question": question,
        "intent": "factual",
        "query_vector": [],
        "chunks": [],
        "answer_parts": [],
        "citations": [],
        "retry_count": 0,
        "final_answer": "",
    }
    try:
        final_state = agent.invoke(initial_state)
    finally:
        pool.close()
    return final_state
