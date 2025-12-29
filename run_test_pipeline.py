#!/usr/bin/env python3
"""
V2.0 Test Pipeline Orchestrator
================================
ENGINE_USE: Docling v2.66.0, Using all-MiniLM-L6-v2

Master script to:
1. Process all PDFs in /examples/sample_docs
2. Generate fresh ingestion.jsonl
3. Verify Qdrant connectivity
4. Ingest into multi_modal_knowledge collection
5. Execute three test queries

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""

import json
import logging
import sys
import time
from pathlib import Path

# Configure logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Now import our modules
from src.mmrag_converter.v2.processor import V2DocumentProcessor
from src.database.ingestor import QdrantIngestor, IngestionResult
from src.database.retriever import QdrantRetriever, SearchFilter
from src.database.config import QdrantConfig

# ============================================================================
# STEP 1: VERIFY QDRANT CONNECTIVITY
# ============================================================================

def verify_qdrant_connectivity(config: QdrantConfig) -> bool:
    """Verify that Qdrant is reachable at localhost:6333."""
    print("\n" + "=" * 70)
    print("STEP 0: VERIFY QDRANT CONNECTIVITY")
    print("=" * 70)
    
    # Format connection string
    if config.url:
        conn_str = config.url
    else:
        conn_str = f"{config.host}:{config.port}"
    
    try:
        client = config.get_client()
        
        # Try to get collection info (will create if not exists in next step)
        try:
            info = client.get_collection(config.collection_name)
            print(f"✓ Qdrant reachable at {conn_str}")
            print(f"✓ Collection '{config.collection_name}' exists")
            print(f"  - Points: {info.points_count}")
            print(f"  - Status: {info.status.value if info.status else 'unknown'}")
            return True
        except Exception as e:
            if "not found" in str(e).lower():
                print(f"✓ Qdrant reachable at {conn_str}")
                print(f"✓ Collection '{config.collection_name}' will be created")
                return True
            raise
    
    except Exception as e:
        print(f"✗ FAILED: Cannot reach Qdrant at {conn_str}")
        print(f"  Error: {e}")
        print("\nEnsure Qdrant container is running:")
        print("  docker-compose up -d qdrant")
        return False


# ============================================================================
# STEP 1: DOCUMENT PROCESSING
# ============================================================================

def process_documents(output_dir: str = "./test_output") -> str:
    """
    Process all PDFs in /examples/sample_docs using V2DocumentProcessor.
    
    Returns:
        Path to generated ingestion.jsonl
    """
    print("\n" + "=" * 70)
    print("STEP 1: DOCUMENT PROCESSING")
    print("=" * 70)
    
    processor = V2DocumentProcessor(
        output_dir=output_dir,
        enable_ocr=False,  # Disable OCR - tesseract not installed
        ocr_engine="easyocr",
    )
    
    # Find all PDFs in examples/sample_docs
    sample_docs_dir = Path("examples/sample_docs")
    pdf_files = sorted(sample_docs_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"✗ No PDF files found in {sample_docs_dir}")
        sys.exit(1)
    
    print(f"✓ Found {len(pdf_files)} PDF files to process")
    
    # Process each PDF and collect chunks
    all_chunks = []
    total_files_processed = 0
    
    for pdf_file in pdf_files:
        print(f"\n  Processing: {pdf_file.name}")
        
        try:
            chunk_count = 0
            for chunk in processor.process_document(str(pdf_file)):
                all_chunks.append(chunk)
                chunk_count += 1
            
            print(f"    ✓ Generated {chunk_count} chunks")
            total_files_processed += 1
            
        except Exception as e:
            print(f"    ✗ Error processing {pdf_file.name}: {e}")
            import traceback
            traceback.print_exc()
    
    if not all_chunks:
        print("\n✗ FAILED: No chunks generated from any documents")
        sys.exit(1)
    
    # Write ingestion.jsonl
    output_path = Path(output_dir) / "ingestion.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            json_line = json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False)
            f.write(json_line + "\n")
    
    print(f"\n✓ DOCUMENT PROCESSING COMPLETE")
    print(f"  - Files processed: {total_files_processed}/{len(pdf_files)}")
    print(f"  - Total chunks generated: {len(all_chunks)}")
    print(f"  - Output: {output_path}")
    
    return str(output_path)


# ============================================================================
# STEP 2: DATABASE INGESTION
# ============================================================================

def ingest_into_qdrant(jsonl_path: str, config: QdrantConfig) -> IngestionResult:
    """
    Run ingestor.py to load ingestion.jsonl into Qdrant.
    
    Returns:
        IngestionResult with statistics
    """
    print("\n" + "=" * 70)
    print("STEP 2: DATABASE INGESTION")
    print("=" * 70)
    
    print(f"✓ Using embedding model: {config.embedding_model.value}")
    print(f"✓ Collection: {config.collection_name}")
    print(f"✓ Vector size: {config.vector_size}")
    
    ingestor = QdrantIngestor(config=config, auto_create_collection=True)
    
    print(f"\nIngesting from: {jsonl_path}")
    result = ingestor.ingest_jsonl(
        jsonl_path=jsonl_path,
        batch_size=50,
        show_progress=True,
        skip_duplicates=True,
    )
    
    print(f"\n✓ INGESTION COMPLETE")
    print(f"  - Total chunks: {result.total_chunks}")
    print(f"  - Inserted: {result.inserted}")
    print(f"  - Skipped (duplicates): {result.skipped_duplicates}")
    print(f"  - Errors: {result.errors}")
    print(f"  - Success rate: {result.success_rate:.1f}%")
    print(f"  - Duration: {result.duration_seconds:.1f}s")
    
    # Show collection stats
    stats = ingestor.get_collection_stats()
    print(f"\nCollection Statistics:")
    print(f"  - Total points: {stats.get('points_count', 0)}")
    print(f"  - Status: {stats.get('status', 'unknown')}")
    
    return result


# ============================================================================
# STEP 3: VALIDATION & RETRIEVAL
# ============================================================================

def test_queries(config: QdrantConfig) -> None:
    """
    Execute three test queries and display detailed results.
    """
    print("\n" + "=" * 70)
    print("STEP 3: VALIDATION & RETRIEVAL TEST")
    print("=" * 70)
    
    retriever = QdrantRetriever(config=config)
    
    # Test queries
    queries = [
        'ROG Ally battery life and performance',
        'B-2 Spirit stealth and mission role',
        'New features in Google Search AI',
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n{'-' * 70}")
        print(f"QUERY {i}: {query}")
        print(f"{'-' * 70}")
        
        try:
            results = retriever.search(query, top_k=3)
            
            if not results:
                print("  ⚠ No results found")
                continue
            
            # Display top result in detail
            top_result = results[0]
            print(f"\n  TOP RESULT:")
            print(f"  ├─ Similarity Score: {top_result.score:.4f}")
            print(f"  ├─ Source: {top_result.source}")
            print(f"  ├─ Page: {top_result.page_number}")
            print(f"  ├─ Modality: {top_result.modality}")
            
            if top_result.breadcrumb:
                breadcrumb_str = " > ".join(top_result.breadcrumb)
                print(f"  ├─ Breadcrumb: {breadcrumb_str}")
            
            if top_result.asset_path:
                print(f"  ├─ Asset: {top_result.asset_path}")
            
            # Show text snippet
            text_preview = top_result.text[:200]
            if len(top_result.text) > 200:
                text_preview += "..."
            print(f"  └─ Text Snippet:")
            for line in text_preview.split('\n'):
                print(f"     {line}")
            
            # Show other results briefly
            if len(results) > 1:
                print(f"\n  OTHER RESULTS ({len(results)-1} more):")
                for j, result in enumerate(results[1:], 2):
                    print(f"    [{j}] {result.source} (p.{result.page_number}) - Score: {result.score:.4f}")
        
        except Exception as e:
            print(f"  ✗ Error executing query: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'-' * 70}")
    print("✓ RETRIEVAL TESTS COMPLETE")
    print(f"{'-' * 70}")


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

def main():
    """Main orchestrator function."""
    print("\n" + "=" * 70)
    print("V2.0 TEST PIPELINE ORCHESTRATOR")
    print("=" * 70)
    print("ENGINE_USE: Docling v2.66.0")
    print("Embedding Model: all-MiniLM-L6-v2")
    print()
    
    start_time = time.time()
    
    try:
        # Initialize config
        config = QdrantConfig()
        
        # Step 0: Verify Qdrant
        if not verify_qdrant_connectivity(config):
            sys.exit(1)
        
        # Step 1: Process documents
        jsonl_path = process_documents(output_dir="./test_output")
        
        # Step 2: Ingest into Qdrant
        result = ingest_into_qdrant(jsonl_path, config)
        
        if result.inserted == 0 and result.skipped_duplicates == 0:
            print("\n✗ CRITICAL: No chunks were ingested into Qdrant")
            sys.exit(1)
        
        # Step 3: Test retrieval
        test_queries(config)
        
        # Final summary
        elapsed = time.time() - start_time
        print("\n" + "=" * 70)
        print("PIPELINE EXECUTION COMPLETE ✓")
        print("=" * 70)
        print(f"Total duration: {elapsed:.1f}s")
        print(f"\nNext steps:")
        print(f"  1. Review the generated chunks in test_output/ingestion.jsonl")
        print(f"  2. Check test_output/assets/ for extracted images")
        print(f"  3. Use retriever.py for additional queries")
        print()
    
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
