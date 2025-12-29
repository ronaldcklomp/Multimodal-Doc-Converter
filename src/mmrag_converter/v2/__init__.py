"""
V2.0 Multimodal RAG Ingestion Engine
=====================================
ENGINE_USE: Docling v2.66.0 (Native Layout Analysis)

This package provides V2.0 compliant components for the Multimodal RAG
Ingestion Engine as specified in SRS_Multimodal_Ingestion_V2.0.md.

Key Components:
- V2DocumentProcessor: Main document processing engine (Docling-native)
- ContextStateV2: Hierarchical state machine (REQ-STATE)
- IngestionChunk: Pydantic schema for ingestion.jsonl (SRS Section 6)

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from .state.context_state import (
    ContextStateV2,
    create_context_state,
)
from .schema.ingestion_schema import (
    Modality,
    FileType,
    ContentClassification,
    HierarchyMetadata,
    SpatialMetadata,
    ChunkMetadata,
    AssetReference,
    SemanticContext,
    IngestionChunk,
    create_text_chunk,
    create_image_chunk,
    create_table_chunk,
)
from .processor import (
    V2DocumentProcessor,
    create_processor,
)

__all__ = [
    "V2DocumentProcessor",
    "create_processor",
    "ContextStateV2",
    "create_context_state",
    "Modality",
    "FileType",
    "ContentClassification",
    "HierarchyMetadata",
    "SpatialMetadata",
    "ChunkMetadata",
    "AssetReference",
    "SemanticContext",
    "IngestionChunk",
    "create_text_chunk",
    "create_image_chunk",
    "create_table_chunk",
]

__version__ = "2.0.0"
