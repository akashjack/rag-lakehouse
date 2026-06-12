"""Contract tests for LangGraph agent (no live Oracle or LLM)."""

from __future__ import annotations

from langgraph.graph import END

from indexer.agent import AgentState, _should_retry, router_node


def _state(**kwargs) -> AgentState:
    defaults: AgentState = {
        "question": "what is a pod?",
        "augmented_question": "what is a pod?",
        "intent": "factual",
        "query_vector": [],
        "chunks": [],
        "answer_parts": [],
        "citations": [],
        "retry_count": 0,
        "final_answer": "",
    }
    defaults.update(kwargs)
    return defaults


def test_router_factual() -> None:
    result = router_node(_state(question="what is a kubernetes pod?"))
    assert result["intent"] == "factual"
    assert result["augmented_question"] == "what is a kubernetes pod?"


def test_router_multi_hop() -> None:
    result = router_node(_state(question="compare kubernetes pods versus deployments"))
    assert result["intent"] == "multi_hop"


def test_router_ambiguous() -> None:
    result = router_node(_state(question="what is it"))
    assert result["intent"] == "ambiguous"
    assert "explain" in result["augmented_question"].lower()


def test_should_retry_poor_answer() -> None:
    state = _state(final_answer="I don't have enough information.", retry_count=1)
    assert _should_retry(state) == "retriever"


def test_should_accept_good_answer() -> None:
    state = _state(
        final_answer="A Pod is the smallest deployable unit in Kubernetes. " * 3,
        retry_count=0,
    )
    assert _should_retry(state) == END


def test_no_retry_more_than_once() -> None:
    state = _state(final_answer="I don't have enough information.", retry_count=2)
    assert _should_retry(state) == END
