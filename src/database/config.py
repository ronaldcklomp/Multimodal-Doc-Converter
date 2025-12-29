"""
Qdrant Configuration & Collection Schema
==========================================
ENGINE_USE: Claude 4.5 Opus (Architect)

Defines the 'multi_modal_knowledge' collection schema that is:
- Document Agnostic: Supports PDF, ePub, DOCX, HTML
- Vector Flexible: 1536-dim (OpenAI) or 1024-dim (BGE-M3)
- Metadata Rich: Full JSONL metadata with spatial, structural, breadcrumbs

Collection Schema Design:
-------------------------
vectors:
  - 1536-dim for OpenAI text-embedding-3-small/large
  - 1024-dim for BGE-M3 (BAAI/bge-m3)

payload:
  - chunk_id: UUID v4 (primary identifier)
  - chunk_hash: SHA256 for deduplication
  - doc_id: MD5 of source file
  - modality: text | image | table
  - content: Actual text content
  - metadata: Full JSONL metadata structure
    - source_file, file_type, page_number
    - hierarchy: parent_heading, breadcrumb_path, level
    - spatial: bbox [x0, y0, x1, y1] (PDF only)
    - content_classification: editorial | advertisement | etc.
  - asset_ref: file_path, visual_description (for images)
  - semantic_context: prev_text_snippet, next_text_snippet

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.models import Distance, VectorParams

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

COLLECTION_NAME = "multi_modal_knowledge"

# Vector dimensions for supported embedding models
VECTOR_DIMS = {
    "openai": 1536,       # text-embedding-3-small, text-embedding-ada-002
    "openai-large": 3072, # text-embedding-3-large
    "bge-m3": 1024,       # BAAI/bge-m3
    "minilm": 384,        # all-MiniLM-L6-v2 (for testing)
}


class EmbeddingModel(str, Enum):
    """Supported embedding models."""
    OPENAI = "openai"
    OPENAI_LARGE = "openai-large"
    BGE_M3 = "bge-m3"
    MINILM = "minilm"  # For local testing


# ============================================================================
# CONFIGURATION DATACLASS
# ============================================================================

@dataclass
class QdrantConfig:
    """
    Qdrant connection and collection configuration.
    
    Supports:
    - Local Qdrant (file-based or memory)
    - Qdrant Cloud (with API key)
    - Custom host/port
    
    Environment Variables:
    - QDRANT_URL: Full URL to Qdrant server
    - QDRANT_API_KEY: API key for Qdrant Cloud
    - QDRANT_HOST: Host for local/custom server
    - QDRANT_PORT: Port for local/custom server
    - EMBEDDING_MODEL: Which embedding model to use
    """
    # Connection settings
    url: Optional[str] = field(default_factory=lambda: os.getenv("QDRANT_URL"))
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    host: str = field(default_factory=lambda: os.getenv("QDRANT_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("QDRANT_PORT", "6333")))
    
    # Collection settings
    collection_name: str = COLLECTION_NAME
    embedding_model: EmbeddingModel = field(
        default_factory=lambda: EmbeddingModel(
            os.getenv("EMBEDDING_MODEL", "openai")
        )
    )
    
    # Performance settings
    batch_size: int = 100
    use_grpc: bool = False
    prefer_grpc: bool = True
    
    # Local storage (if not using remote)
    local_path: Optional[str] = None
    in_memory: bool = False
    
    @property
    def vector_size(self) -> int:
        """Get vector dimension for the configured embedding model."""
        return VECTOR_DIMS.get(self.embedding_model.value, 1536)
    
    def get_client(self) -> QdrantClient:
        """
        Create and return a QdrantClient based on configuration.
        
        Priority:
        1. URL (for Qdrant Cloud or custom deployment)
        2. Local path (for file-based storage)
        3. In-memory (for testing)
        4. Host/port (for local Docker)
        """
        if self.url:
            logger.info(f"Connecting to Qdrant at: {self.url}")
            return QdrantClient(
                url=self.url,
                api_key=self.api_key,
                prefer_grpc=self.prefer_grpc,
            )
        elif self.local_path:
            logger.info(f"Using local Qdrant storage at: {self.local_path}")
            return QdrantClient(path=self.local_path)
        elif self.in_memory:
            logger.info("Using in-memory Qdrant (for testing)")
            return QdrantClient(":memory:")
        else:
            logger.info(f"Connecting to Qdrant at: {self.host}:{self.port}")
            return QdrantClient(
                host=self.host,
                port=self.port,
                prefer_grpc=self.prefer_grpc,
            )


# ============================================================================
# PAYLOAD SCHEMA (for validation)
# ============================================================================

def compute_chunk_hash(content: str, doc_id: str, page_number: int) -> str:
    """
    Compute a deterministic hash for deduplication.
    
    Hash = SHA256(doc_id + page_number + content)
    
    This ensures that identical content from the same document
    location won't be duplicated on re-ingestion.
    """
    hash_input = f"{doc_id}:{page_number}:{content}"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def prepare_payload(
    chunk_data: Dict[str, Any],
    chunk_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepare a payload dictionary for Qdrant insertion.
    
    Ensures all required fields are present and properly typed.
    Handles both flat and nested structures from ingestion.jsonl.
    
    Args:
        chunk_data: Raw chunk dictionary from JSONL
        chunk_hash: Optional pre-computed hash
        
    Returns:
        Flattened payload dict for Qdrant
    """
    # Extract metadata (handles both nested and flat)
    metadata = chunk_data.get("metadata", {})
    if isinstance(metadata, str):
        # If metadata is a JSON string, parse it
        import json
        metadata = json.loads(metadata)
    
    # Extract hierarchy
    hierarchy = metadata.get("hierarchy", {})
    if isinstance(hierarchy, str):
        import json
        hierarchy = json.loads(hierarchy)
    
    # Extract spatial (PDF-specific)
    spatial = metadata.get("spatial", {})
    if isinstance(spatial, str):
        import json
        spatial = json.loads(spatial)
    
    # Extract asset reference (for images)
    asset_ref = chunk_data.get("asset_ref", {})
    if isinstance(asset_ref, str):
        import json
        asset_ref = json.loads(asset_ref)
    
    # Extract semantic context
    semantic_ctx = chunk_data.get("semantic_context", {})
    if isinstance(semantic_ctx, str):
        import json
        semantic_ctx = json.loads(semantic_ctx)
    
    # Build payload
    content = chunk_data.get("content", "")
    doc_id = chunk_data.get("doc_id", "")
    page_number = metadata.get("page_number", 1)
    
    # Compute hash if not provided
    if not chunk_hash:
        chunk_hash = compute_chunk_hash(content, doc_id, page_number)
    
    payload = {
        # Core identifiers
        "chunk_id": chunk_data.get("chunk_id", ""),
        "chunk_hash": chunk_hash,
        "doc_id": doc_id,
        
        # Content
        "modality": chunk_data.get("modality", "text"),
        "content": content,
        
        # Source metadata
        "source_file": metadata.get("source_file", ""),
        "file_type": metadata.get("file_type", "pdf"),
        "page_number": page_number,
        
        # Hierarchy (for all document types)
        "parent_heading": hierarchy.get("parent_heading"),
        "breadcrumb_path": hierarchy.get("breadcrumb_path", []),
        "heading_level": hierarchy.get("level"),
        
        # Spatial (PDF-specific)
        "bbox": spatial.get("bbox") if spatial else None,
        
        # Content classification
        "content_classification": metadata.get(
            "content_classification", "editorial"
        ),
        
        # Asset reference (for images/tables)
        "asset_path": asset_ref.get("file_path") if asset_ref else None,
        "visual_description": asset_ref.get("visual_description") if asset_ref else None,
        
        # Semantic context (for multimodal anchoring)
        "prev_text_snippet": semantic_ctx.get("prev_text_snippet") if semantic_ctx else None,
        "next_text_snippet": semantic_ctx.get("next_text_snippet") if semantic_ctx else None,
    }
    
    return payload


# ============================================================================
# COLLECTION CREATION
# ============================================================================

def create_collection_if_not_exists(
    client: QdrantClient,
    config: QdrantConfig,
    recreate: bool = False,
) -> bool:
    """
    Create the multi_modal_knowledge collection if it doesn't exist.
    
    Collection Features:
    - Cosine similarity (normalized embeddings)
    - Payload indexing for fast filtering
    - HNSW index for efficient search
    
    Args:
        client: QdrantClient instance
        config: QdrantConfig with collection settings
        recreate: If True, delete and recreate existing collection
        
    Returns:
        True if collection was created, False if it already existed
    """
    collection_name = config.collection_name
    
    # Check if collection exists
    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)
    
    if exists and recreate:
        logger.warning(f"Recreating collection: {collection_name}")
        client.delete_collection(collection_name)
        exists = False
    elif exists:
        logger.info(f"Collection already exists: {collection_name}")
        return False
    
    # Create collection with optimized settings
    logger.info(
        f"Creating collection: {collection_name} "
        f"(vector_size={config.vector_size}, model={config.embedding_model.value})"
    )
    
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=config.vector_size,
            distance=Distance.COSINE,
            on_disk=True,  # Optimize for large collections
        ),
        # Optimized HNSW settings
        hnsw_config=qdrant_models.HnswConfigDiff(
            m=16,                    # Number of edges per node
            ef_construct=100,        # Construction time/accuracy trade-off
            full_scan_threshold=10000,
            max_indexing_threads=0,  # Use all available
            on_disk=False,           # Keep HNSW in RAM for speed
        ),
        # Enable quantization for large collections
        quantization_config=qdrant_models.ScalarQuantization(
            scalar=qdrant_models.ScalarQuantizationConfig(
                type=qdrant_models.ScalarType.INT8,
                quantile=0.99,
                always_ram=True,
            ),
        ),
        # Optimistic concurrency
        on_disk_payload=True,
    )
    
    # Create payload indexes for common filter fields
    _create_payload_indexes(client, collection_name)
    
    logger.info(f"Collection created successfully: {collection_name}")
    return True


def _create_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    """
    Create payload indexes for efficient filtering.
    
    Indexed fields:
    - chunk_hash: For deduplication checks
    - doc_id: Filter by document
    - modality: Filter by content type
    - file_type: Filter by source format
    - page_number: Range queries
    - content_classification: Filter editorial vs ads
    - breadcrumb_path: Full-text search on headings
    """
    indexes = [
        ("chunk_hash", qdrant_models.PayloadSchemaType.KEYWORD),
        ("doc_id", qdrant_models.PayloadSchemaType.KEYWORD),
        ("modality", qdrant_models.PayloadSchemaType.KEYWORD),
        ("file_type", qdrant_models.PayloadSchemaType.KEYWORD),
        ("page_number", qdrant_models.PayloadSchemaType.INTEGER),
        ("content_classification", qdrant_models.PayloadSchemaType.KEYWORD),
        ("source_file", qdrant_models.PayloadSchemaType.KEYWORD),
        ("asset_path", qdrant_models.PayloadSchemaType.KEYWORD),
    ]
    
    for field_name, field_type in indexes:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_type,
            )
            logger.debug(f"Created index for field: {field_name}")
        except Exception as e:
            # Index might already exist
            logger.debug(f"Index creation skipped for {field_name}: {e}")
    
    # Create text index for breadcrumb path (for full-text search)
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="breadcrumb_path",
            field_schema=qdrant_models.TextIndexParams(
                type="text",
                tokenizer=qdrant_models.TokenizerType.WORD,
                min_token_len=2,
                max_token_len=20,
                lowercase=True,
            ),
        )
        logger.debug("Created text index for breadcrumb_path")
    except Exception as e:
        logger.debug(f"Text index creation skipped: {e}")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_default_config() -> QdrantConfig:
    """
    Get default configuration from environment variables.
    
    Returns:
        QdrantConfig with settings from environment
    """
    return QdrantConfig()


def get_local_config(path: str = "./qdrant_data") -> QdrantConfig:
    """
    Get configuration for local file-based storage.
    
    Args:
        path: Directory for Qdrant storage
        
    Returns:
        QdrantConfig for local storage
    """
    return QdrantConfig(local_path=path, in_memory=False)


def get_memory_config() -> QdrantConfig:
    """
    Get configuration for in-memory storage (testing).
    
    Returns:
        QdrantConfig for in-memory storage
    """
    return QdrantConfig(in_memory=True)
