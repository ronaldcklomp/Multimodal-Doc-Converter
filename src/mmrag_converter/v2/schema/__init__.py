"""V2.0 Schema Module - Pydantic models for ingestion.jsonl."""
from .ingestion_schema import (
    # Enums
    Modality,
    FileType,
    ContentClassification,
    # Schema models
    HierarchyMetadata,
    SpatialMetadata,
    ChunkMetadata,
    AssetReference,
    SemanticContext,
    IngestionChunk,
    # Factory functions
    create_text_chunk,
    create_image_chunk,
    create_table_chunk,
)

__all__ = [
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
