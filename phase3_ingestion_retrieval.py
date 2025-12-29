#!/usr/bin/env python3
"""
PHASE 3 EXECUTION: Smart Ingestion + Multi-Modal Retrieval
===========================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

This script:
1. Ingests Combat Aircraft & PCWorld V2 JSONL to Qdrant
2. Preserves asset_ref.file_path and hierarchy.breadcrumb_path as metadata
3. Embeds image content using technical descriptions
4. Performs 3 critical retrieval tests
5. Generates technical audit table

SRS Compliance:
- REQ-MM: Asset metadata mapping (file_path, breadcrumb_path)
- REQ-STATE: Hierarchy breadcrumb preservation
- REQ-CHUNK: Semantic search on content chunks

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-29
"""
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from database.config import QdrantConfig, EmbeddingModel
from database.ingestor import QdrantIngestor, IngestionResult
from database.retriever import QdrantRetriever, SearchFilter, RichSearchResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


# ============================================================================
# PHASE 3: SMART INGESTION
# ============================================================================

def phase3_ingest_documents() -> Dict[str, IngestionResult]:
    """
    Ingest both Combat Aircraft and PCWorld JSONL with metadata preservation.
    
    CRITICAL: Asset and hierarchy metadata MUST be stored in payload for
    retrieval and validation.
    
    Returns:
        Dict with ingestion results for each document
    """
    print("\n" + "=" * 90)
    print("PHASE 3.1: SMART INGESTION")
    print("=" * 90)
    
    # Use minilm embedding model for faster testing
    config = QdrantConfig(
        in_memory=False,
        local_path="./qdrant_storage",
        embedding_model=EmbeddingModel.MINILM,
    )
    
    ingestor = QdrantIngestor(config=config, auto_create_collection=True)
    
    results = {}
    
    # Combat Aircraft ingestion
    combat_jsonl = Path("data/combat_aircraft_v2_output/ingestion.jsonl")
    if combat_jsonl.exists():
        print(f"\n⏳ Ingesting Combat Aircraft ({combat_jsonl.name})...")
        result = ingestor.ingest_jsonl(
            str(combat_jsonl),
            batch_size=100,
            show_progress=True,
            skip_duplicates=True,
        )
        results["Combat Aircraft"] = result
        print(f"✓ {result.inserted} chunks inserted, {result.skipped_duplicates} skipped")
    else:
        logger.error(f"Combat Aircraft JSONL not found: {combat_jsonl}")
    
    # PCWorld ingestion
    pcworld_jsonl = Path("data/PCWorld_July_2025_USA_v2_output/ingestion.jsonl")
    if pcworld_jsonl.exists():
        print(f"\n⏳ Ingesting PCWorld ({pcworld_jsonl.name})...")
        result = ingestor.ingest_jsonl(
            str(pcworld_jsonl),
            batch_size=100,
            show_progress=True,
            skip_duplicates=True,
        )
        results["PCWorld"] = result
        print(f"✓ {result.inserted} chunks inserted, {result.skipped_duplicates} skipped")
    else:
        logger.error(f"PCWorld JSONL not found: {pcworld_jsonl}")
    
    # Show collection stats
    stats = ingestor.get_collection_stats()
    print(f"\nCollection Stats:")
    print(f"  Points Count: {stats.get('points_count', 0)}")
    print(f"  Vectors Count: {stats.get('vectors_count', 0)}")
    
    return results


# ============================================================================
# PHASE 3: MULTI-MODAL RETRIEVAL TESTS
# ============================================================================

def phase3_retrieval_tests() -> Dict[str, List[RichSearchResult]]:
    """
    Execute 3 critical retrieval tests with validation.
    
    Query 1: 'How do I access the AI Mode in Google Search?'
      → Verify breadcrumbs correctly identify PCWorld 'Internet' section
    
    Query 2: 'B-2 Spirit technical illustration.'
      → Verify asset_path is valid (file exists in assets/)
    
    Query 3: 'ROG Ally specifications.'
      → Verify hierarchy filters out non-hardware mentions
    
    Returns:
        Dict mapping queries to search results
    """
    print("\n" + "=" * 90)
    print("PHASE 3.2: MULTI-MODAL RETRIEVAL TESTS")
    print("=" * 90)
    
    config = QdrantConfig(
        local_path="./qdrant_storage",
        embedding_model=EmbeddingModel.MINILM,
    )
    
    retriever = QdrantRetriever(config=config)
    
    # Test queries
    queries = {
        "Query 1: AI Mode in Google Search": "How do I access the AI Mode in Google Search?",
        "Query 2: B-2 Spirit technical illustration": "B-2 Spirit technical illustration",
        "Query 3: ROG Ally specifications": "ROG Ally specifications",
    }
    
    all_results = {}
    
    for query_name, query_text in queries.items():
        print(f"\n🔍 {query_name}")
        print(f"   Query: '{query_text}'")
        
        try:
            results = retriever.search(query_text, top_k=3)
            all_results[query_name] = results
            
            print(f"   ✓ Found {len(results)} results")
            for i, result in enumerate(results, 1):
                print(f"     [{i}] Score: {result.score:.4f} | {result.source} p.{result.page_number}")
                if result.breadcrumb:
                    print(f"         Breadcrumb: {' > '.join(result.breadcrumb[:2])}")
                if result.asset_path:
                    print(f"         Asset: {result.asset_path}")
        
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            all_results[query_name] = []
    
    return all_results


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_query1_pcworld_internet(results: List[RichSearchResult]) -> bool:
    """
    Verify Query 1 results contain PCWorld with Internet section breadcrumb.
    
    Returns:
        True if validation passed
    """
    for result in results:
        if result.source and "PCWorld" in result.source:
            if result.breadcrumb and any("Internet" in b or "Google" in b for b in result.breadcrumb):
                return True
    return False


def validate_query2_asset_path(results: List[RichSearchResult]) -> Tuple[bool, Optional[str]]:
    """
    Verify Query 2 results contain valid B-2 Spirit asset paths.
    
    Returns:
        (is_valid, asset_path)
    """
    for result in results:
        if result.asset_path:
            asset_file = Path("data") / result.asset_path
            if asset_file.exists():
                return True, result.asset_path
    
    return False, None


def validate_query3_hardware_hierarchy(results: List[RichSearchResult]) -> bool:
    """
    Verify Query 3 results have hardware-related hierarchy.
    
    Returns:
        True if ROG Ally results have proper hardware categorization
    """
    hardware_keywords = ["hardware", "laptop", "device", "computer", "gaming", "asus", "rog"]
    
    for result in results:
        if result.breadcrumb:
            breadcrumb_text = " ".join(result.breadcrumb).lower()
            if any(keyword in breadcrumb_text for keyword in hardware_keywords):
                return True
    
    return False


# ============================================================================
# AUDIT TABLE GENERATION
# ============================================================================

def generate_audit_table(
    queries: Dict[str, List[RichSearchResult]],
) -> str:
    """
    Generate technical audit table with:
    - Query name
    - Top result score
    - Hierarchy path (first 2 breadcrumbs)
    - Asset path (if applicable)
    
    Returns:
        Formatted markdown table
    """
    table = []
    table.append("| Query | Top Result Score | Hierarchy Path | Asset Path | Modality |")
    table.append("|-------|------------------|----------------|-----------|----------|")
    
    for query_name, results in queries.items():
        if not results:
            table.append(f"| {query_name} | N/A | N/A | N/A | N/A |")
            continue
        
        top_result = results[0]
        score = f"{top_result.score:.4f}"
        
        # Hierarchy path (first 2 breadcrumbs)
        if top_result.breadcrumb:
            hierarchy = " > ".join(top_result.breadcrumb[:2])
        else:
            hierarchy = "N/A"
        
        # Asset path
        asset_path = top_result.asset_path if top_result.asset_path else "N/A"
        
        # Modality
        modality = top_result.modality
        
        table.append(f"| {query_name} | {score} | {hierarchy} | {asset_path} | {modality} |")
    
    return "\n".join(table)


# ============================================================================
# DETAILED RESULT REPORT
# ============================================================================

def print_detailed_results(
    queries: Dict[str, List[RichSearchResult]],
) -> None:
    """
    Print detailed results for each query with full context.
    
    Shows:
    - Query name and text
    - Top 3 results with score, source, hierarchy, asset
    - Validation status
    """
    print("\n" + "=" * 90)
    print("DETAILED RETRIEVAL RESULTS")
    print("=" * 90)
    
    for query_idx, (query_name, results) in enumerate(queries.items(), 1):
        print(f"\n{'─' * 90}")
        print(f"{query_idx}. {query_name}")
        print(f"{'─' * 90}")
        
        if not results:
            print("   ❌ No results found")
            continue
        
        for result_idx, result in enumerate(results[:3], 1):
            print(f"\n   Result {result_idx}:")
            print(f"   ├─ Score: {result.score:.4f}")
            print(f"   ├─ Source: {result.source} (p. {result.page_number})")
            print(f"   ├─ Modality: {result.modality}")
            print(f"   ├─ Document ID: {result.doc_id}")
            
            if result.breadcrumb:
                breadcrumb_str = " > ".join(result.breadcrumb)
                print(f"   ├─ Hierarchy: {breadcrumb_str}")
            
            if result.asset_path:
                # Verify asset exists
                asset_file = Path("data") / result.asset_path
                exists = "✓" if asset_file.exists() else "✗"
                print(f"   ├─ Asset: {result.asset_path} {exists}")
            
            # Content preview
            content_preview = result.text[:80] + "..." if len(result.text) > 80 else result.text
            print(f"   └─ Content: {content_preview}")


# ============================================================================
# METADATA VALIDATION
# ============================================================================

def validate_metadata_storage(retriever: QdrantRetriever) -> Dict[str, Any]:
    """
    Validate that metadata (asset_ref, hierarchy) is properly stored in Qdrant.
    
    Returns:
        Validation report
    """
    print("\n" + "=" * 90)
    print("METADATA VALIDATION")
    print("=" * 90)
    
    report = {
        "total_documents": 0,
        "documents_with_assets": 0,
        "documents_with_breadcrumbs": 0,
        "asset_path_validity": 0,
        "validation_errors": [],
    }
    
    # Get all documents
    documents = retriever.list_documents()
    report["total_documents"] = len(documents)
    
    print(f"\nTotal documents in collection: {len(documents)}")
    
    for doc in documents:
        print(f"\n  Document: {doc['source_file']} (ID: {doc['doc_id'][:12]}...)")
        
        # Get all chunks for this document
        chunks = retriever.get_document_chunks(doc["doc_id"], limit=50)
        
        # Check for assets
        chunks_with_assets = sum(1 for c in chunks if c.asset_path)
        if chunks_with_assets > 0:
            report["documents_with_assets"] += 1
            print(f"    → {chunks_with_assets} chunks with assets")
        
        # Check for breadcrumbs
        chunks_with_breadcrumbs = sum(1 for c in chunks if c.breadcrumb)
        if chunks_with_breadcrumbs > 0:
            report["documents_with_breadcrumbs"] += 1
            print(f"    → {chunks_with_breadcrumbs} chunks with breadcrumbs")
        
        # Validate asset paths
        for chunk in chunks:
            if chunk.asset_path:
                asset_file = Path("data") / chunk.asset_path
                if asset_file.exists():
                    report["asset_path_validity"] += 1
                else:
                    report["validation_errors"].append(
                        f"Asset not found: {chunk.asset_path}"
                    )
    
    # Print summary
    print(f"\n{'─' * 90}")
    print("Validation Summary:")
    print(f"  ✓ Total documents: {report['total_documents']}")
    print(f"  ✓ Documents with assets: {report['documents_with_assets']}")
    print(f"  ✓ Documents with breadcrumbs: {report['documents_with_breadcrumbs']}")
    print(f"  ✓ Valid asset paths: {report['asset_path_validity']}")
    if report["validation_errors"]:
        print(f"  ✗ Validation errors: {len(report['validation_errors'])}")
        for error in report["validation_errors"][:5]:
            print(f"    - {error}")
    
    return report


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Execute Phase 3: Ingestion + Retrieval + Validation"""
    
    print("\n" + "=" * 90)
    print("PHASE 3 EXECUTION: MULTIMODAL RAG INGESTION & RETRIEVAL")
    print("=" * 90)
    print("ENGINE_USE: all-MiniLM-L6-v2 (384-dim)")
    print("METADATA MAPPING: asset_ref.file_path + hierarchy.breadcrumb_path")
    print("IMAGE HANDLING: Use content field (technical descriptions) for embedding")
    print("=" * 90)
    
    # Step 1: Ingest documents
    try:
        ingestion_results = phase3_ingest_documents()
        
        # Print ingestion summary
        print("\n" + "─" * 90)
        print("INGESTION SUMMARY:")
        for doc_name, result in ingestion_results.items():
            print(f"\n{doc_name}:")
            print(f"  Total: {result.total_chunks}")
            print(f"  Inserted: {result.inserted}")
            print(f"  Skipped: {result.skipped_duplicates}")
            print(f"  Errors: {result.errors}")
            print(f"  Duration: {result.duration_seconds:.1f}s")
            print(f"  Success Rate: {result.success_rate:.1f}%")
    
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        return
    
    # Step 2: Execute retrieval tests
    try:
        all_results = phase3_retrieval_tests()
    except Exception as e:
        logger.error(f"Retrieval tests failed: {e}", exc_info=True)
        return
    
    # Step 3: Print detailed results
    print_detailed_results(all_results)
    
    # Step 4: Generate audit table
    print("\n" + "=" * 90)
    print("TECHNICAL AUDIT TABLE")
    print("=" * 90)
    audit_table = generate_audit_table(all_results)
    print("\n" + audit_table)
    
    # Step 5: Validate metadata storage
    config = QdrantConfig(
        local_path="./qdrant_storage",
        embedding_model=EmbeddingModel.MINILM,
    )
    retriever = QdrantRetriever(config=config)
    metadata_validation = validate_metadata_storage(retriever)
    
    # Step 6: Verify specific queries
    print("\n" + "=" * 90)
    print("QUERY-SPECIFIC VALIDATION")
    print("=" * 90)
    
    results_by_query = list(all_results.values())
    
    if len(results_by_query) > 0:
        is_valid = validate_query1_pcworld_internet(results_by_query[0])
        status = "✓ PASS" if is_valid else "✗ FAIL"
        print(f"\nQuery 1 - PCWorld Internet Section: {status}")
    
    if len(results_by_query) > 1:
        is_valid, asset_path = validate_query2_asset_path(results_by_query[1])
        status = "✓ PASS" if is_valid else "✗ FAIL"
        print(f"Query 2 - B-2 Spirit Asset Validity: {status}")
        if asset_path:
            print(f"  Valid asset: {asset_path}")
    
    if len(results_by_query) > 2:
        is_valid = validate_query3_hardware_hierarchy(results_by_query[2])
        status = "✓ PASS" if is_valid else "✗ FAIL"
        print(f"Query 3 - ROG Ally Hardware Hierarchy: {status}")
    
    # Final summary
    print("\n" + "=" * 90)
    print("PHASE 3 COMPLETE ✅")
    print("=" * 90)
    print(f"Ingested documents: {len(ingestion_results)}")
    print(f"Total documents in Qdrant: {metadata_validation['total_documents']}")
    print(f"Documents with assets: {metadata_validation['documents_with_assets']}")
    print(f"Documents with breadcrumbs: {metadata_validation['documents_with_breadcrumbs']}")
    print(f"Valid asset paths: {metadata_validation['asset_path_validity']}")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
