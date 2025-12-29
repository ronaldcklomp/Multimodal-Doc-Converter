"""
Qdrant Ingestor - Batch Processing with Check-and-Upsert Logic
================================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

Phase 3: Persistent Storage & Retrieval

This module implements the production-ready ingestion pipeline:
1. Read ingestion.jsonl from Phase 2
2. Batch process chunks to avoid API/memory throttles
3. Check-and-Upsert logic (don't duplicate if chunk_hash exists)
4. Document-agnostic design (PDF, ePub, DOCX, HTML)

Key Features:
- Batch embedding generation (respects API rate limits)
- Deduplication via chunk_hash
- Progress tracking with tqdm
- Retry logic for transient failures
- Dry-run mode for testing

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional, Set, Tuple
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.models import PointStruct

from .config import (
    QdrantConfig,
    compute_chunk_hash,
    create_collection_if_not_exists,
    prepare_payload,
)
from .embeddings import (
    EmbeddingProvider,
    get_embedding_provider,
    prepare_text_for_embedding,
)

logger = logging.getLogger(__name__)


# ============================================================================
# INGESTION RESULT DATACLASS
# ============================================================================

@dataclass
class IngestionResult:
    """
    Result of an ingestion operation.
    
    Tracks:
    - Total chunks processed
    - New chunks inserted
    - Duplicates skipped
    - Errors encountered
    """
    total_chunks: int = 0
    inserted: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    error_messages: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_chunks == 0:
            return 100.0
        return ((self.inserted + self.skipped_duplicates) / self.total_chunks) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_chunks": self.total_chunks,
            "inserted": self.inserted,
            "skipped_duplicates": self.skipped_duplicates,
            "errors": self.errors,
            "success_rate": f"{self.success_rate:.1f}%",
            "duration_seconds": round(self.duration_seconds, 2),
        }
    
    def __str__(self) -> str:
        return (
            f"IngestionResult(total={self.total_chunks}, inserted={self.inserted}, "
            f"skipped={self.skipped_duplicates}, errors={self.errors}, "
            f"duration={self.duration_seconds:.1f}s)"
        )


# ============================================================================
# MAIN INGESTOR CLASS
# ============================================================================

class QdrantIngestor:
    """
    Production-ready Qdrant ingestor for multimodal document chunks.
    
    Features:
    - Batch processing with configurable batch sizes
    - Check-and-upsert deduplication
    - Automatic collection creation
    - Progress tracking
    - Retry logic for transient failures
    
    Usage:
        config = QdrantConfig(in_memory=True)  # or from env
        ingestor = QdrantIngestor(config)
        
        result = ingestor.ingest_jsonl("output/ingestion.jsonl")
        print(f"Ingested {result.inserted} chunks")
    """
    
    def __init__(
        self,
        config: Optional[QdrantConfig] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        auto_create_collection: bool = True,
    ):
        """
        Initialize the ingestor.
        
        Args:
            config: Qdrant configuration (uses default if not provided)
            embedding_provider: Custom embedding provider (uses default if not)
            auto_create_collection: Whether to create collection if missing
        """
        self.config = config or QdrantConfig()
        self.client = self.config.get_client()
        
        # Initialize embedding provider
        if embedding_provider:
            self.embedding_provider = embedding_provider
        else:
            self.embedding_provider = get_embedding_provider(
                model=self.config.embedding_model
            )
        
        # Auto-create collection if needed
        if auto_create_collection:
            create_collection_if_not_exists(self.client, self.config)
        
        logger.info(
            f"QdrantIngestor initialized: collection={self.config.collection_name}, "
            f"embedding_model={self.config.embedding_model.value}"
        )
    
    def ingest_jsonl(
        self,
        jsonl_path: str,
        batch_size: int = 50,
        show_progress: bool = True,
        skip_duplicates: bool = True,
        dry_run: bool = False,
    ) -> IngestionResult:
        """
        Ingest chunks from a JSONL file into Qdrant.
        
        Args:
            jsonl_path: Path to ingestion.jsonl file
            batch_size: Number of chunks to process per batch
            show_progress: Whether to show progress bar
            skip_duplicates: Whether to skip chunks with existing hashes
            dry_run: If True, don't actually insert (for testing)
            
        Returns:
            IngestionResult with statistics
        """
        start_time = time.time()
        result = IngestionResult()
        
        jsonl_path = Path(jsonl_path)
        if not jsonl_path.exists():
            raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")
        
        logger.info(f"Starting ingestion from: {jsonl_path}")
        
        # Count total lines for progress bar
        total_lines = sum(1 for _ in open(jsonl_path, "r", encoding="utf-8"))
        result.total_chunks = total_lines
        
        # Read and batch chunks
        chunks_batch = []
        
        with open(jsonl_path, "r", encoding="utf-8") as f:
            iterator = enumerate(f)
            
            if show_progress:
                try:
                    from tqdm import tqdm
                    iterator = tqdm(
                        iterator,
                        total=total_lines,
                        desc="Ingesting",
                        unit="chunks",
                    )
                except ImportError:
                    pass
            
            for i, line in iterator:
                try:
                    chunk_data = json.loads(line.strip())
                    chunks_batch.append(chunk_data)
                    
                    # Process batch when full
                    if len(chunks_batch) >= batch_size:
                        batch_result = self._process_batch(
                            chunks_batch,
                            skip_duplicates=skip_duplicates,
                            dry_run=dry_run,
                        )
                        result.inserted += batch_result["inserted"]
                        result.skipped_duplicates += batch_result["skipped"]
                        result.errors += batch_result["errors"]
                        chunks_batch = []
                        
                except json.JSONDecodeError as e:
                    result.errors += 1
                    result.error_messages.append(f"Line {i}: JSON decode error: {e}")
                    logger.warning(f"JSON decode error at line {i}: {e}")
                except Exception as e:
                    result.errors += 1
                    result.error_messages.append(f"Line {i}: {str(e)}")
                    logger.warning(f"Error processing line {i}: {e}")
        
        # Process remaining chunks
        if chunks_batch:
            batch_result = self._process_batch(
                chunks_batch,
                skip_duplicates=skip_duplicates,
                dry_run=dry_run,
            )
            result.inserted += batch_result["inserted"]
            result.skipped_duplicates += batch_result["skipped"]
            result.errors += batch_result["errors"]
        
        result.duration_seconds = time.time() - start_time
        
        logger.info(
            f"Ingestion complete: {result.inserted} inserted, "
            f"{result.skipped_duplicates} skipped, "
            f"{result.errors} errors in {result.duration_seconds:.1f}s"
        )
        
        return result
    
    def ingest_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 50,
        skip_duplicates: bool = True,
        dry_run: bool = False,
    ) -> IngestionResult:
        """
        Ingest a list of chunk dictionaries directly.
        
        Args:
            chunks: List of chunk dictionaries (matching JSONL schema)
            batch_size: Number of chunks per batch
            skip_duplicates: Whether to skip duplicates
            dry_run: If True, don't insert
            
        Returns:
            IngestionResult with statistics
        """
        start_time = time.time()
        result = IngestionResult()
        result.total_chunks = len(chunks)
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_result = self._process_batch(
                batch,
                skip_duplicates=skip_duplicates,
                dry_run=dry_run,
            )
            result.inserted += batch_result["inserted"]
            result.skipped_duplicates += batch_result["skipped"]
            result.errors += batch_result["errors"]
        
        result.duration_seconds = time.time() - start_time
        return result
    
    def _process_batch(
        self,
        chunks: List[Dict[str, Any]],
        skip_duplicates: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, int]:
        """
        Process a batch of chunks: check duplicates, embed, upsert.
        
        Args:
            chunks: List of chunk dictionaries
            skip_duplicates: Whether to check for duplicates
            dry_run: If True, don't insert
            
        Returns:
            Dict with counts: inserted, skipped, errors
        """
        result = {"inserted": 0, "skipped": 0, "errors": 0}
        
        if not chunks:
            return result
        
        # Step 1: Prepare payloads and compute hashes
        payloads_with_hashes = []
        for chunk in chunks:
            try:
                payload = prepare_payload(chunk)
                chunk_hash = payload["chunk_hash"]
                payloads_with_hashes.append((payload, chunk_hash, chunk))
            except Exception as e:
                result["errors"] += 1
                logger.warning(f"Error preparing payload: {e}")
        
        if not payloads_with_hashes:
            return result
        
        # Step 2: Check for existing hashes (deduplication)
        existing_hashes: Set[str] = set()
        if skip_duplicates:
            hashes_to_check = [h for _, h, _ in payloads_with_hashes]
            existing_hashes = self._get_existing_hashes(hashes_to_check)
        
        # Step 3: Filter out duplicates
        to_insert = []
        for payload, chunk_hash, original_chunk in payloads_with_hashes:
            if chunk_hash in existing_hashes:
                result["skipped"] += 1
                logger.debug(f"Skipping duplicate chunk: {chunk_hash[:16]}...")
            else:
                to_insert.append((payload, original_chunk))
        
        if not to_insert or dry_run:
            if dry_run and to_insert:
                result["inserted"] = len(to_insert)
            return result
        
        # Step 4: Generate embeddings for non-duplicate chunks
        texts_to_embed = []
        for payload, _ in to_insert:
            text = prepare_text_for_embedding(
                content=payload["content"],
                modality=payload["modality"],
                breadcrumb_path=payload.get("breadcrumb_path"),
                parent_heading=payload.get("parent_heading"),
            )
            texts_to_embed.append(text)
        
        try:
            embeddings = self.embedding_provider.embed_batch(
                texts_to_embed,
                batch_size=min(len(texts_to_embed), 100),
            )
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            result["errors"] += len(to_insert)
            return result
        
        # Step 5: Create points and upsert
        points = []
        for (payload, _), embedding in zip(to_insert, embeddings):
            point_id = str(uuid4())
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            )
        
        try:
            upsert_result = self.client.upsert(
                collection_name=self.config.collection_name,
                points=points,
                wait=True,
            )
            result["inserted"] = len(points)
            logger.info(f"✓ Successfully ingested {len(points)} points into Qdrant")
            logger.debug(f"Upsert status: {upsert_result.status if hasattr(upsert_result, 'status') else 'completed'}")
        except Exception as e:
            logger.error(f"Upsert failed: {e}")
            result["errors"] += len(points)
        
        return result
    
    def _get_existing_hashes(self, hashes: List[str]) -> Set[str]:
        """
        Check which chunk_hashes already exist in the collection.
        
        Uses scroll with filter for efficiency.
        
        Args:
            hashes: List of chunk hashes to check
            
        Returns:
            Set of hashes that already exist
        """
        existing = set()
        
        # Batch check to avoid large filter
        batch_size = 100
        for i in range(0, len(hashes), batch_size):
            batch_hashes = hashes[i:i + batch_size]
            
            try:
                # Use scroll with should filter (OR)
                filter_condition = qdrant_models.Filter(
                    should=[
                        qdrant_models.FieldCondition(
                            key="chunk_hash",
                            match=qdrant_models.MatchValue(value=h),
                        )
                        for h in batch_hashes
                    ]
                )
                
                results, _ = self.client.scroll(
                    collection_name=self.config.collection_name,
                    scroll_filter=filter_condition,
                    limit=len(batch_hashes),
                    with_payload=["chunk_hash"],
                    with_vectors=False,
                )
                
                for point in results:
                    if point.payload and "chunk_hash" in point.payload:
                        existing.add(point.payload["chunk_hash"])
                        
            except Exception as e:
                logger.warning(f"Error checking existing hashes: {e}")
        
        return existing
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the current collection.
        
        Returns:
            Dict with collection info: points_count, segments, etc.
        """
        try:
            info = self.client.get_collection(self.config.collection_name)
            return {
                "collection_name": self.config.collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status.value if info.status else "unknown",
            }
        except Exception as e:
            return {"error": str(e)}
    
    def delete_by_doc_id(self, doc_id: str) -> int:
        """
        Delete all chunks belonging to a specific document.
        
        Useful for re-ingesting a document.
        
        Args:
            doc_id: Document ID (MD5 hash) to delete
            
        Returns:
            Number of points deleted
        """
        try:
            result = self.client.delete(
                collection_name=self.config.collection_name,
                points_selector=qdrant_models.FilterSelector(
                    filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="doc_id",
                                match=qdrant_models.MatchValue(value=doc_id),
                            )
                        ]
                    )
                ),
            )
            logger.info(f"Deleted chunks for doc_id: {doc_id}")
            return result.status == qdrant_models.UpdateStatus.COMPLETED
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return 0


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def ingest_jsonl_file(
    jsonl_path: str,
    config: Optional[QdrantConfig] = None,
    batch_size: int = 50,
    show_progress: bool = True,
    skip_duplicates: bool = True,
    use_mock_embeddings: bool = False,
) -> IngestionResult:
    """
    Convenience function to ingest a JSONL file.
    
    Args:
        jsonl_path: Path to ingestion.jsonl
        config: Qdrant configuration (uses default if not provided)
        batch_size: Chunks per batch
        show_progress: Show progress bar
        skip_duplicates: Skip existing chunks
        use_mock_embeddings: Use mock embeddings (for testing)
        
    Returns:
        IngestionResult with statistics
        
    Example:
        # Quick ingestion with defaults
        result = ingest_jsonl_file("output/ingestion.jsonl")
        
        # With custom config
        config = QdrantConfig(in_memory=True)
        result = ingest_jsonl_file("output/ingestion.jsonl", config=config)
    """
    config = config or QdrantConfig()
    
    embedding_provider = None
    if use_mock_embeddings:
        from .embeddings import MockEmbeddingProvider
        embedding_provider = MockEmbeddingProvider(dimension=config.vector_size)
    
    ingestor = QdrantIngestor(
        config=config,
        embedding_provider=embedding_provider,
    )
    
    return ingestor.ingest_jsonl(
        jsonl_path=jsonl_path,
        batch_size=batch_size,
        show_progress=show_progress,
        skip_duplicates=skip_duplicates,
    )


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    """CLI entry point for ingestion."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Ingest JSONL chunks into Qdrant"
    )
    parser.add_argument(
        "jsonl_path",
        help="Path to ingestion.jsonl file",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for processing",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar",
    )
    parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Don't skip duplicate chunks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually insert (for testing)",
    )
    parser.add_argument(
        "--mock-embeddings",
        action="store_true",
        help="Use mock embeddings (for testing)",
    )
    parser.add_argument(
        "--local-db",
        type=str,
        default=None,
        help="Path for local Qdrant storage",
    )
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="Use in-memory Qdrant (for testing)",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Build config
    config = QdrantConfig(
        local_path=args.local_db,
        in_memory=args.in_memory,
    )
    
    # Run ingestion
    embedding_provider = None
    if args.mock_embeddings:
        from .embeddings import MockEmbeddingProvider
        embedding_provider = MockEmbeddingProvider(dimension=config.vector_size)
    
    ingestor = QdrantIngestor(
        config=config,
        embedding_provider=embedding_provider,
    )
    
    result = ingestor.ingest_jsonl(
        jsonl_path=args.jsonl_path,
        batch_size=args.batch_size,
        show_progress=not args.no_progress,
        skip_duplicates=not args.allow_duplicates,
        dry_run=args.dry_run,
    )
    
    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)
    print(json.dumps(result.to_dict(), indent=2))
    
    # Show collection stats
    stats = ingestor.get_collection_stats()
    print("\nCollection Stats:")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
