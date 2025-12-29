"""
Qdrant Retriever - Rich Search Results with Context
=====================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

Phase 3: Persistent Storage & Retrieval

This module implements the search/retrieval interface:
1. Semantic search with vector similarity
2. Rich results with full context
3. Filtering by document, modality, page, etc.
4. Hybrid search (vector + keyword)

Rich Result Structure:
- text: The actual content
- source: Source file and page
- breadcrumb: Full hierarchical path
- asset_path: Path to image/table (if applicable)
- score: Similarity score
- metadata: Full payload for advanced use

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from .config import QdrantConfig, create_collection_if_not_exists
from .embeddings import (
    EmbeddingProvider,
    get_embedding_provider,
    prepare_text_for_embedding,
)

logger = logging.getLogger(__name__)


# ============================================================================
# RICH SEARCH RESULT DATACLASS
# ============================================================================

@dataclass
class RichSearchResult:
    """
    A rich search result with full context for RAG applications.
    
    Provides everything needed for:
    - Displaying results to users
    - Building RAG context windows
    - Citing sources in responses
    
    Attributes:
        text: The actual content text
        source: Source file name
        page_number: Page number in source
        breadcrumb: Full hierarchical path
        modality: Content type (text, image, table)
        score: Similarity score (0-1)
        asset_path: Path to image/table file (if any)
        visual_description: AI description of visual (if any)
        prev_context: Text before this chunk
        next_context: Text after this chunk
        doc_id: Document identifier
        chunk_id: Unique chunk identifier
        metadata: Full payload for advanced use
    """
    text: str
    source: str
    page_number: int
    breadcrumb: List[str]
    modality: str
    score: float
    
    # Optional fields
    asset_path: Optional[str] = None
    visual_description: Optional[str] = None
    prev_context: Optional[str] = None
    next_context: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    bbox: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def citation(self) -> str:
        """Generate a citation string for the result."""
        breadcrumb_str = " > ".join(self.breadcrumb) if self.breadcrumb else ""
        if breadcrumb_str:
            return f"{self.source}, p.{self.page_number} ({breadcrumb_str})"
        return f"{self.source}, p.{self.page_number}"
    
    @property
    def context_window(self) -> str:
        """Generate a context window with surrounding text."""
        parts = []
        if self.prev_context:
            parts.append(f"[...] {self.prev_context}")
        parts.append(self.text)
        if self.next_context:
            parts.append(f"{self.next_context} [...]")
        return " ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "text": self.text,
            "source": self.source,
            "page_number": self.page_number,
            "breadcrumb": self.breadcrumb,
            "modality": self.modality,
            "score": round(self.score, 4),
            "asset_path": self.asset_path,
            "visual_description": self.visual_description,
            "citation": self.citation,
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
        }
    
    def __repr__(self) -> str:
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return (
            f"RichSearchResult(score={self.score:.3f}, "
            f"source='{self.source}', page={self.page_number}, "
            f"text='{text_preview}')"
        )


# ============================================================================
# SEARCH FILTERS
# ============================================================================

@dataclass
class SearchFilter:
    """
    Filter configuration for search queries.
    
    All filters are optional and combined with AND logic.
    """
    doc_ids: Optional[List[str]] = None
    source_files: Optional[List[str]] = None
    file_types: Optional[List[str]] = None
    modalities: Optional[List[str]] = None
    page_range: Optional[tuple] = None  # (min_page, max_page)
    content_classification: Optional[str] = None
    exclude_non_editorial: bool = False
    
    def to_qdrant_filter(self) -> Optional[qdrant_models.Filter]:
        """Convert to Qdrant filter condition."""
        conditions = []
        
        if self.doc_ids:
            conditions.append(
                qdrant_models.FieldCondition(
                    key="doc_id",
                    match=qdrant_models.MatchAny(any=self.doc_ids),
                )
            )
        
        if self.source_files:
            conditions.append(
                qdrant_models.FieldCondition(
                    key="source_file",
                    match=qdrant_models.MatchAny(any=self.source_files),
                )
            )
        
        if self.file_types:
            conditions.append(
                qdrant_models.FieldCondition(
                    key="file_type",
                    match=qdrant_models.MatchAny(any=self.file_types),
                )
            )
        
        if self.modalities:
            conditions.append(
                qdrant_models.FieldCondition(
                    key="modality",
                    match=qdrant_models.MatchAny(any=self.modalities),
                )
            )
        
        if self.page_range:
            min_page, max_page = self.page_range
            if min_page is not None:
                conditions.append(
                    qdrant_models.FieldCondition(
                        key="page_number",
                        range=qdrant_models.Range(gte=min_page),
                    )
                )
            if max_page is not None:
                conditions.append(
                    qdrant_models.FieldCondition(
                        key="page_number",
                        range=qdrant_models.Range(lte=max_page),
                    )
                )
        
        if self.content_classification:
            conditions.append(
                qdrant_models.FieldCondition(
                    key="content_classification",
                    match=qdrant_models.MatchValue(value=self.content_classification),
                )
            )
        
        if self.exclude_non_editorial:
            conditions.append(
                qdrant_models.FieldCondition(
                    key="content_classification",
                    match=qdrant_models.MatchValue(value="editorial"),
                )
            )
        
        if not conditions:
            return None
        
        return qdrant_models.Filter(must=conditions)


# ============================================================================
# MAIN RETRIEVER CLASS
# ============================================================================

class QdrantRetriever:
    """
    Production-ready Qdrant retriever for RAG applications.
    
    Features:
    - Semantic search with configurable top-k
    - Rich results with full context
    - Flexible filtering
    - Score threshold control
    - Batch search support
    
    Usage:
        retriever = QdrantRetriever()
        
        # Simple search
        results = retriever.search("How to install the software?")
        
        # Search with filters
        results = retriever.search(
            query="installation steps",
            filter=SearchFilter(file_types=["pdf"], modalities=["text"]),
            top_k=10,
        )
    """
    
    def __init__(
        self,
        config: Optional[QdrantConfig] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        """
        Initialize the retriever.
        
        Args:
            config: Qdrant configuration
            embedding_provider: Custom embedding provider
        """
        self.config = config or QdrantConfig()
        self.client = self.config.get_client()
        
        if embedding_provider:
            self.embedding_provider = embedding_provider
        else:
            self.embedding_provider = get_embedding_provider(
                model=self.config.embedding_model
            )
        
        logger.info(
            f"QdrantRetriever initialized: collection={self.config.collection_name}"
        )
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[SearchFilter] = None,
        score_threshold: Optional[float] = None,
        include_metadata: bool = True,
    ) -> List[RichSearchResult]:
        """
        Search for relevant chunks using semantic similarity.
        
        Args:
            query: Search query text
            top_k: Maximum number of results
            filter: Optional search filter
            score_threshold: Minimum score threshold (0-1)
            include_metadata: Whether to include full metadata
            
        Returns:
            List of RichSearchResult objects
        """
        # Generate query embedding
        query_embedding = self.embedding_provider.embed_text(query)
        
        # Build filter
        qdrant_filter = filter.to_qdrant_filter() if filter else None
        
        # Execute search using query_points (new API)
        search_result = self.client.query_points(
            collection_name=self.config.collection_name,
            query=query_embedding,
            query_filter=qdrant_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        ).points
        
        # Convert to rich results
        results = []
        for point in search_result:
            result = self._point_to_rich_result(point, include_metadata)
            results.append(result)
        
        logger.debug(f"Search returned {len(results)} results for: {query[:50]}...")
        return results
    
    def search_by_doc(
        self,
        query: str,
        doc_id: str,
        top_k: int = 5,
        modalities: Optional[List[str]] = None,
    ) -> List[RichSearchResult]:
        """
        Search within a specific document.
        
        Args:
            query: Search query
            doc_id: Document ID to search within
            top_k: Maximum results
            modalities: Filter by content types
            
        Returns:
            List of RichSearchResult
        """
        filter = SearchFilter(
            doc_ids=[doc_id],
            modalities=modalities,
        )
        return self.search(query, top_k=top_k, filter=filter)
    
    def search_images(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[SearchFilter] = None,
    ) -> List[RichSearchResult]:
        """
        Search for relevant images/figures.
        
        Args:
            query: Search query (searches visual descriptions & context)
            top_k: Maximum results
            filter: Additional filters
            
        Returns:
            List of RichSearchResult for image chunks
        """
        if filter is None:
            filter = SearchFilter(modalities=["image"])
        else:
            filter.modalities = ["image"]
        
        return self.search(query, top_k=top_k, filter=filter)
    
    def search_tables(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[SearchFilter] = None,
    ) -> List[RichSearchResult]:
        """
        Search for relevant tables.
        
        Args:
            query: Search query
            top_k: Maximum results
            filter: Additional filters
            
        Returns:
            List of RichSearchResult for table chunks
        """
        if filter is None:
            filter = SearchFilter(modalities=["table"])
        else:
            filter.modalities = ["table"]
        
        return self.search(query, top_k=top_k, filter=filter)
    
    def get_context_window(
        self,
        chunk_id: str,
        window_size: int = 2,
    ) -> List[RichSearchResult]:
        """
        Get surrounding chunks for context expansion.
        
        Args:
            chunk_id: Central chunk ID
            window_size: Number of chunks before/after
            
        Returns:
            List of surrounding chunks (ordered by page)
        """
        # First, get the target chunk to find its context
        target_results, _ = self.client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="chunk_id",
                        match=qdrant_models.MatchValue(value=chunk_id),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
        )
        
        if not target_results:
            return []
        
        target = target_results[0]
        doc_id = target.payload.get("doc_id")
        page_num = target.payload.get("page_number", 1)
        
        # Get surrounding chunks from same document
        min_page = max(1, page_num - window_size)
        max_page = page_num + window_size
        
        results, _ = self.client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="doc_id",
                        match=qdrant_models.MatchValue(value=doc_id),
                    ),
                    qdrant_models.FieldCondition(
                        key="page_number",
                        range=qdrant_models.Range(gte=min_page, lte=max_page),
                    ),
                ]
            ),
            limit=50,
            with_payload=True,
        )
        
        # Convert and sort by page number
        rich_results = [
            self._point_to_rich_result(p, include_metadata=True)
            for p in results
        ]
        rich_results.sort(key=lambda r: (r.page_number, r.chunk_id or ""))
        
        return rich_results
    
    def get_document_chunks(
        self,
        doc_id: str,
        limit: int = 100,
        modalities: Optional[List[str]] = None,
    ) -> List[RichSearchResult]:
        """
        Get all chunks for a specific document.
        
        Args:
            doc_id: Document ID
            limit: Maximum chunks to return
            modalities: Filter by content types
            
        Returns:
            List of all chunks from the document
        """
        conditions = [
            qdrant_models.FieldCondition(
                key="doc_id",
                match=qdrant_models.MatchValue(value=doc_id),
            )
        ]
        
        if modalities:
            conditions.append(
                qdrant_models.FieldCondition(
                    key="modality",
                    match=qdrant_models.MatchAny(any=modalities),
                )
            )
        
        results, _ = self.client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=qdrant_models.Filter(must=conditions),
            limit=limit,
            with_payload=True,
        )
        
        rich_results = [
            self._point_to_rich_result(p, include_metadata=True)
            for p in results
        ]
        rich_results.sort(key=lambda r: r.page_number)
        
        return rich_results
    
    def _point_to_rich_result(
        self,
        point: Any,
        include_metadata: bool = True,
    ) -> RichSearchResult:
        """Convert a Qdrant point to a RichSearchResult."""
        payload = point.payload or {}
        score = getattr(point, "score", 1.0)
        
        return RichSearchResult(
            text=payload.get("content", ""),
            source=payload.get("source_file", ""),
            page_number=payload.get("page_number", 0),
            breadcrumb=payload.get("breadcrumb_path", []),
            modality=payload.get("modality", "text"),
            score=score,
            asset_path=payload.get("asset_path"),
            visual_description=payload.get("visual_description"),
            prev_context=payload.get("prev_text_snippet"),
            next_context=payload.get("next_text_snippet"),
            doc_id=payload.get("doc_id"),
            chunk_id=payload.get("chunk_id"),
            bbox=payload.get("bbox"),
            metadata=payload if include_metadata else {},
        )
    
    def list_documents(self) -> List[Dict[str, Any]]:
        """
        List all unique documents in the collection.
        
        Returns:
            List of document info dicts
        """
        # Use scroll to get unique doc_ids
        all_docs = {}
        offset = None
        
        while True:
            results, offset = self.client.scroll(
                collection_name=self.config.collection_name,
                limit=100,
                offset=offset,
                with_payload=["doc_id", "source_file", "file_type"],
                with_vectors=False,
            )
            
            for point in results:
                doc_id = point.payload.get("doc_id")
                if doc_id and doc_id not in all_docs:
                    all_docs[doc_id] = {
                        "doc_id": doc_id,
                        "source_file": point.payload.get("source_file"),
                        "file_type": point.payload.get("file_type"),
                    }
            
            if offset is None:
                break
        
        return list(all_docs.values())


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def search_knowledge_base(
    query: str,
    top_k: int = 5,
    config: Optional[QdrantConfig] = None,
    filter: Optional[SearchFilter] = None,
    use_mock_embeddings: bool = False,
) -> List[RichSearchResult]:
    """
    Convenience function for quick searches.
    
    Args:
        query: Search query
        top_k: Number of results
        config: Qdrant configuration
        filter: Search filter
        use_mock_embeddings: Use mock embeddings (for testing)
        
    Returns:
        List of RichSearchResult
        
    Example:
        results = search_knowledge_base("How to install?")
        for r in results:
            print(f"[{r.score:.2f}] {r.citation}: {r.text[:100]}...")
    """
    config = config or QdrantConfig()
    
    embedding_provider = None
    if use_mock_embeddings:
        from .embeddings import MockEmbeddingProvider
        embedding_provider = MockEmbeddingProvider(dimension=config.vector_size)
    
    retriever = QdrantRetriever(
        config=config,
        embedding_provider=embedding_provider,
    )
    
    return retriever.search(query, top_k=top_k, filter=filter)


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    """CLI entry point for search."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(
        description="Search the knowledge base"
    )
    parser.add_argument(
        "query",
        help="Search query",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of results",
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Filter by document ID",
    )
    parser.add_argument(
        "--file-type",
        type=str,
        default=None,
        help="Filter by file type (pdf, epub, etc.)",
    )
    parser.add_argument(
        "--modality",
        type=str,
        choices=["text", "image", "table"],
        default=None,
        help="Filter by modality",
    )
    parser.add_argument(
        "--local-db",
        type=str,
        default=None,
        help="Path to local Qdrant storage",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock embeddings (for testing)",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(level=logging.WARNING)
    
    # Build config and filter
    config = QdrantConfig(local_path=args.local_db) if args.local_db else None
    
    filter = None
    if args.doc_id or args.file_type or args.modality:
        filter = SearchFilter(
            doc_ids=[args.doc_id] if args.doc_id else None,
            file_types=[args.file_type] if args.file_type else None,
            modalities=[args.modality] if args.modality else None,
        )
    
    # Execute search
    results = search_knowledge_base(
        query=args.query,
        top_k=args.top_k,
        config=config,
        filter=filter,
        use_mock_embeddings=args.mock,
    )
    
    # Output results
    if args.json:
        output = [r.to_dict() for r in results]
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print(f"SEARCH RESULTS for: '{args.query}'")
        print(f"{'=' * 60}")
        
        if not results:
            print("\nNo results found.")
        else:
            for i, r in enumerate(results, 1):
                print(f"\n[{i}] Score: {r.score:.3f}")
                print(f"    Source: {r.citation}")
                print(f"    Modality: {r.modality}")
                if r.asset_path:
                    print(f"    Asset: {r.asset_path}")
                print(f"    Text: {r.text[:200]}...")
                print("-" * 60)


if __name__ == "__main__":
    main()
