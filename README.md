# Production RAG Lakehouse System

Enterprise-grade Retrieval-Augmented Generation (RAG) platform built using:

- Apache Iceberg
- MinIO
- PySpark
- Oracle 23ai Vector Search
- LangChain
- LangGraph
- OpenAI Embeddings
- FastAPI
- Docker

## Architecture

Document Sources
→ Ingestion Layer
→ MinIO Object Storage
→ Apache Iceberg Lakehouse
→ Embedding Pipeline
→ Oracle 23ai Vector Store
→ Hybrid Retrieval
→ LangGraph Agent Workflow
→ LLM Response Generation
