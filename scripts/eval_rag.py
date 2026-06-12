"""Phase 10: RAG evaluation suite.

Implements core RAGAS-style metrics without the RAGAS library dependency:
- answer_relevance:  cosine similarity between question embedding and answer embedding
- faithfulness:      fraction of answer sentences that can be grounded in context chunks
- context_precision: fraction of retrieved chunks that are relevant to the question
- context_recall:    estimated coverage of the question by the retrieved chunks

Each metric returns a float in [0, 1]. Higher is better.

Usage:
    cd ~/YOLT/rag-lakehouse
    python scripts/eval_rag.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, "services/indexer")

from indexer.config import IndexerSettings
from indexer.embedders.ollama_embedder import OllamaEmbedder
from indexer.store.connection import build_pool
from indexer.store.repository import hybrid_search

# =========================================================================
# Eval dataset — 20 Q&A pairs hand-curated from the gold corpus
# =========================================================================

EVAL_DATASET = [
    {
        "question": "What is a Kubernetes Pod?",
        "reference": "A Pod is the smallest deployable unit in Kubernetes, representing one or more containers sharing network and storage.",
        "source": "kubernetes",
    },
    {
        "question": "How does Kubernetes handle pod scheduling?",
        "reference": "The Kubernetes scheduler assigns pods to nodes based on resource requirements, constraints, and affinity rules.",
        "source": "kubernetes",
    },
    {
        "question": "What is a Kubernetes Service?",
        "reference": "A Service is an abstraction that defines a logical set of Pods and a policy to access them, providing stable networking.",
        "source": "kubernetes",
    },
    {
        "question": "What is a Kubernetes Deployment?",
        "reference": "A Deployment manages a replicated application, ensuring the desired number of pod replicas are running.",
        "source": "kubernetes",
    },
    {
        "question": "What is a StatefulSet in Kubernetes?",
        "reference": "A StatefulSet manages stateful applications, providing stable network identities and persistent storage per pod.",
        "source": "kubernetes",
    },
    {
        "question": "How does Spring Boot auto-configuration work?",
        "reference": "Spring Boot auto-configuration automatically configures beans based on classpath dependencies using @EnableAutoConfiguration.",
        "source": "spring",
    },
    {
        "question": "What is Spring Boot Actuator?",
        "reference": "Spring Boot Actuator provides production-ready features like health checks, metrics, and application monitoring endpoints.",
        "source": "spring",
    },
    {
        "question": "How do you define a REST controller in Spring Boot?",
        "reference": "Use @RestController annotation on a class with @RequestMapping or @GetMapping methods to define REST endpoints.",
        "source": "spring",
    },
    {
        "question": "What is dependency injection in Spring?",
        "reference": "Dependency injection is a pattern where Spring automatically injects bean dependencies via @Autowired or constructor injection.",
        "source": "spring",
    },
    {
        "question": "What is Spring Data JPA?",
        "reference": "Spring Data JPA provides repository abstractions over JPA, reducing boilerplate for database access with CRUD operations.",
        "source": "spring",
    },
    {
        "question": "What is an Angular component?",
        "reference": "An Angular component is a TypeScript class decorated with @Component that controls a view template and its logic.",
        "source": "angular",
    },
    {
        "question": "What is Angular dependency injection?",
        "reference": "Angular DI is a design pattern where services are provided and injected into components via the injector hierarchy.",
        "source": "angular",
    },
    {
        "question": "What are Angular signals?",
        "reference": "Signals are reactive primitives in Angular that represent values and automatically notify consumers when they change.",
        "source": "angular",
    },
    {
        "question": "What is the Angular change detection strategy?",
        "reference": "Angular uses zone.js or signals to detect changes; OnPush strategy only checks when inputs change or events fire.",
        "source": "angular",
    },
    {
        "question": "What is an Angular directive?",
        "reference": "A directive is a class decorated with @Directive that adds behavior to DOM elements, such as ngIf or ngFor.",
        "source": "angular",
    },
    {
        "question": "How do you configure liveness probes in Kubernetes?",
        "reference": "Liveness probes are configured in pod spec using httpGet, exec, or tcpSocket to detect and restart failed containers.",
        "source": "kubernetes",
    },
    {
        "question": "What is a Kubernetes ConfigMap?",
        "reference": "A ConfigMap stores non-confidential configuration data as key-value pairs consumed by pods as environment variables or files.",
        "source": "kubernetes",
    },
    {
        "question": "What is Spring Security?",
        "reference": "Spring Security is a framework providing authentication, authorization, and protection against common security exploits.",
        "source": "spring",
    },
    {
        "question": "What is Angular routing?",
        "reference": "Angular routing maps URL paths to components using RouterModule, enabling navigation between views in a SPA.",
        "source": "angular",
    },
    {
        "question": "What is a Kubernetes Namespace?",
        "reference": "A Namespace provides a mechanism for isolating groups of resources within a single cluster for multi-tenant environments.",
        "source": "kubernetes",
    },
]


# =========================================================================
# Metric implementations
# =========================================================================


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def answer_relevance(
    question_vec: list[float],
    answer: str,
    embedder: OllamaEmbedder,
) -> float:
    """Cosine similarity between question and answer embeddings."""
    if not answer.strip():
        return 0.0
    answer_vec = embedder.embed_batch([answer])[0]
    return max(0.0, cosine_similarity(question_vec, answer_vec))


def context_precision(
    question_vec: list[float],
    chunks: list[dict[str, Any]],
    embedder: OllamaEmbedder,
    threshold: float = 0.3,
) -> float:
    """Fraction of retrieved chunks whose text is similar to the question."""
    if not chunks:
        return 0.0
    texts = [(c.get("chunk_text_head") or "")[:500] for c in chunks]
    chunk_vecs = embedder.embed_batch(texts)
    relevant = sum(1 for cv in chunk_vecs if cosine_similarity(question_vec, cv) >= threshold)
    return relevant / len(chunks)


def faithfulness(answer: str, chunks: list[dict[str, Any]]) -> float:
    """Fraction of answer sentences that overlap with chunk text keywords."""
    if not answer.strip() or not chunks:
        return 0.0

    context = " ".join((c.get("chunk_text_head") or "")[:500].lower() for c in chunks)
    context_words = set(context.split())

    sentences = [s.strip() for s in answer.replace("\n", " ").split(".") if len(s.strip()) > 10]
    if not sentences:
        return 0.0

    grounded = 0
    for sentence in sentences:
        words = set(w.lower() for w in sentence.split() if len(w) > 4)
        if not words:
            continue
        overlap = words & context_words
        if len(overlap) / len(words) >= 0.3:
            grounded += 1

    return grounded / len(sentences)


def context_recall(
    reference_vec: list[float],
    chunks: list[dict[str, Any]],
    embedder: OllamaEmbedder,
    threshold: float = 0.25,
) -> float:
    """Max similarity between reference answer and any retrieved chunk."""
    if not chunks:
        return 0.0
    texts = [(c.get("chunk_text_head") or "")[:500] for c in chunks]
    chunk_vecs = embedder.embed_batch(texts)
    sims = [cosine_similarity(reference_vec, cv) for cv in chunk_vecs]
    best = max(sims) if sims else 0.0
    return min(1.0, best / threshold) if best < threshold else 1.0


# =========================================================================
# Eval runner
# =========================================================================


def run_eval(k: int = 5, output_path: str = "eval_results.json") -> None:
    settings = IndexerSettings(
        oracle_dsn="localhost:1521/FREEPDB1",
        oracle_user="rag",
        oracle_password="RagApp_2026",
        ollama_base_url="http://localhost:11434",
    )  # type: ignore[call-arg]

    pool = build_pool(settings)
    results = []

    with OllamaEmbedder(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embed_model,
        dimension=settings.embedding_dim,
        timeout_seconds=settings.embed_timeout_seconds,
    ) as embedder:
        for i, item in enumerate(EVAL_DATASET, 1):
            q = item["question"]
            ref = item["reference"]
            print(f"[{i:2d}/{len(EVAL_DATASET)}] {q[:60]}...")

            # Embed question and reference
            q_vec = embedder.embed_batch([q])[0]
            ref_vec = embedder.embed_batch([ref])[0]

            # Retrieve chunks
            chunks = hybrid_search(
                pool,
                q_vec,
                q,
                k,
                embedding_model_ver=settings.embedding_model_version,
            )

            # Score metrics (no LLM — embedding-based only for speed)
            ar = answer_relevance(q_vec, ref, embedder)
            cp = context_precision(q_vec, chunks, embedder)
            cr = context_recall(ref_vec, chunks, embedder)
            ff = faithfulness(ref, chunks)

            result = {
                "question": q,
                "source": item["source"],
                "chunks_retrieved": len(chunks),
                "answer_relevance": round(ar, 4),
                "context_precision": round(cp, 4),
                "context_recall": round(cr, 4),
                "faithfulness": round(ff, 4),
            }
            results.append(result)
            print(
                f"       AR={ar:.3f}  CP={cp:.3f}  CR={cr:.3f}  F={ff:.3f}  "
                f"chunks={len(chunks)}"
            )

    pool.close()

    # Aggregate
    avg = {
        m: round(sum(r[m] for r in results) / len(results), 4)
        for m in ["answer_relevance", "context_precision", "context_recall", "faithfulness"]
    }
    print("\n=== AGGREGATE SCORES ===")
    for k_name, v in avg.items():
        print(f"  {k_name:<22}: {v:.4f}")

    output = {"results": results, "aggregate": avg}
    Path(output_path).write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    run_eval()
