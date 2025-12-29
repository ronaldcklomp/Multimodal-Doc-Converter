"""
Database Module - Qdrant Vector Store Integration for V2.0
============================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

Phase 3: Persistent Storage & Retrieval

This module provides production-ready Qdrant integration for the multimodal
RAG ingestion pipeline. It is document-agnostic and supports:
- PDF (spatial metadata, bboxes)
- ePub (structural metadata, file boundaries)  
- DOCX/HTML (hierarchical metadata)

Key Components:
- config: Collection schema and Qdrant configuration
- embeddings: Unified embedding interface (OpenAI/BGE-M3)
- ingestor: Batch processing with check-and-upsert logic
- retriever: Rich search results with context

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

from .config import (
    QdrantConfig,
    EmbeddingModel,
    COLLECTION_NAME,
    create_collection_if_not_exists,
)
from .embeddings import EmbeddingProvider, get_embedding_provider
from .ingestor import QdrantIngestor, ingest_jsonl_file
from .retriever import QdrantRetriever, RichSearchResult, search_knowledge_base

__all__ = [
    # Config
    "QdrantConfig",
    "EmbeddingModel", 
    "COLLECTION_NAME",
    "create_collection_if_not_exists",
    # Embeddings
    "EmbeddingProvider",
    "get_embedding_provider",
    # Ingestor
    "QdrantIngestor",
    "ingest_jsonl_file",
    # Retriever
    "QdrantRetriever",
    "RichSearchResult",
    "search_knowledge_base",
]

__version__ = "1.0.0"
