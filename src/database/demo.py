#!/usr/bin/env python3
"""
Qdrant Integration Demo - Phase 3 Demonstration
=================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

This script demonstrates the full Phase 3 workflow:
1. Create a sample ingestion.jsonl
2. Ingest into Qdrant (in-memory for demo)
3. Execute sample searches
4. Show rich result format

Run with:
    python -m src.database.demo

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.config import QdrantConfig, EmbeddingModel
from src.database.embeddings import MockEmbeddingProvider
from src.database.ingestor import QdrantIngestor
from src.database.retriever import QdrantRetriever, SearchFilter


# ============================================================================
# SAMPLE DATA
# ============================================================================

SAMPLE_CHUNKS = [
    # PDF text chunks
    {
        "chunk_id": "chunk-001",
        "doc_id": "a1b2c3d4e5f6",
        "modality": "text",
        "content": "Chapter 1: Introduction to Machine Learning. Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed. This technology has revolutionized many industries.",
        "metadata": {
            "source_file": "ml_handbook.pdf",
            "file_type": "pdf",
            "page_number": 1,
            "hierarchy": {
                "parent_heading": "Chapter 1: Introduction",
                "breadcrumb_path": ["Chapter 1: Introduction"],
                "level": 1
            },
            "content_classification": "editorial"
        }
    },
    {
        "chunk_id": "chunk-002",
        "doc_id": "a1b2c3d4e5f6",
        "modality": "text",
        "content": "Supervised learning is a type of machine learning where the model is trained on labeled data. The algorithm learns to map inputs to outputs based on example input-output pairs. Common applications include image classification and spam detection.",
        "metadata": {
            "source_file": "ml_handbook.pdf",
            "file_type": "pdf",
            "page_number": 5,
            "hierarchy": {
                "parent_heading": "1.1 Supervised Learning",
                "breadcrumb_path": ["Chapter 1: Introduction", "1.1 Supervised Learning"],
                "level": 2
            },
            "spatial": {
                "bbox": [72.0, 100.0, 540.0, 300.0]
            },
            "content_classification": "editorial"
        }
    },
    {
        "chunk_id": "chunk-003",
        "doc_id": "a1b2c3d4e5f6",
        "modality": "text",
        "content": "Unsupervised learning works with unlabeled data to discover hidden patterns and structures. Clustering and dimensionality reduction are common unsupervised techniques. K-means clustering is widely used for customer segmentation.",
        "metadata": {
            "source_file": "ml_handbook.pdf",
            "file_type": "pdf",
            "page_number": 10,
            "hierarchy": {
                "parent_heading": "1.2 Unsupervised Learning",
                "breadcrumb_path": ["Chapter 1: Introduction", "1.2 Unsupervised Learning"],
                "level": 2
            },
            "content_classification": "editorial"
        }
    },
    # Image chunk
    {
        "chunk_id": "chunk-004",
        "doc_id": "a1b2c3d4e5f6",
        "modality": "image",
        "content": "Figure 1.1: Neural Network Architecture. A diagram showing the layers of a deep neural network with input, hidden, and output layers connected by weighted edges.",
        "metadata": {
            "source_file": "ml_handbook.pdf",
            "file_type": "pdf",
            "page_number": 15,
            "hierarchy": {
                "parent_heading": "1.3 Deep Learning",
                "breadcrumb_path": ["Chapter 1: Introduction", "1.3 Deep Learning"],
                "level": 2
            },
            "spatial": {
                "bbox": [100.0, 200.0, 500.0, 450.0]
            },
            "content_classification": "editorial"
        },
        "asset_ref": {
            "file_path": "assets/a1b2c3d4e5f6_015_figure_01.png",
            "visual_description": "Multi-layer neural network diagram with 3 hidden layers"
        },
        "semantic_context": {
            "prev_text_snippet": "Deep learning uses multiple layers to progressively extract features...",
            "next_text_snippet": "The activation functions in each layer determine the non-linearity..."
        }
    },
    # Table chunk
    {
        "chunk_id": "chunk-005",
        "doc_id": "a1b2c3d4e5f6",
        "modality": "table",
        "content": "| Algorithm | Type | Use Case |\n|-----------|------|----------|\n| Linear Regression | Supervised | Prediction |\n| K-Means | Unsupervised | Clustering |\n| CNN | Deep Learning | Image Recognition |",
        "metadata": {
            "source_file": "ml_handbook.pdf",
            "file_type": "pdf",
            "page_number": 20,
            "hierarchy": {
                "parent_heading": "1.4 Algorithm Comparison",
                "breadcrumb_path": ["Chapter 1: Introduction", "1.4 Algorithm Comparison"],
                "level": 2
            },
            "content_classification": "editorial"
        },
        "asset_ref": {
            "file_path": "assets/a1b2c3d4e5f6_020_table_01.png"
        }
    },
    # EPUB chunks (different document)
    {
        "chunk_id": "chunk-006",
        "doc_id": "xyz789abc123",
        "modality": "text",
        "content": "Python is a versatile programming language widely used in data science and machine learning. Its simple syntax and rich ecosystem of libraries make it the preferred choice for ML practitioners.",
        "metadata": {
            "source_file": "python_guide.epub",
            "file_type": "epub",
            "page_number": 1,
            "hierarchy": {
                "parent_heading": "Introduction to Python",
                "breadcrumb_path": ["Part I", "Introduction to Python"],
                "level": 2
            },
            "content_classification": "editorial"
        }
    },
    {
        "chunk_id": "chunk-007",
        "doc_id": "xyz789abc123",
        "modality": "text",
        "content": "NumPy provides efficient array operations and mathematical functions. Pandas offers powerful data manipulation tools. Scikit-learn contains implementations of many machine learning algorithms.",
        "metadata": {
            "source_file": "python_guide.epub",
            "file_type": "epub",
            "page_number": 5,
            "hierarchy": {
                "parent_heading": "Essential Libraries",
                "breadcrumb_path": ["Part I", "Essential Libraries"],
                "level": 2
            },
            "content_classification": "editorial"
        }
    },
]


# ============================================================================
# DEMO FUNCTIONS
# ============================================================================

def create_sample_jsonl(output_path: str) -> str:
    """Create a sample ingestion.jsonl file."""
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in SAMPLE_CHUNKS:
            f.write(json.dumps(chunk) + "\n")
    return output_path


def run_demo():
    """Run the full Phase 3 demonstration."""
    print("=" * 70)
    print("PHASE 3: QDRANT INTEGRATION DEMO")
    print("ENGINE_USE: Claude 4.5 Opus (Architect)")
    print("=" * 70)
    
    # Step 1: Create sample JSONL
    print("\n[1/4] Creating sample ingestion.jsonl...")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        jsonl_path = f.name
    create_sample_jsonl(jsonl_path)
    print(f"  ✓ Created {len(SAMPLE_CHUNKS)} sample chunks")
    
    # Step 2: Initialize Qdrant (in-memory for demo)
    print("\n[2/4] Initializing Qdrant (in-memory)...")
    config = QdrantConfig(
        in_memory=True,
        embedding_model=EmbeddingModel.MINILM,  # 384-dim for testing
    )
    
    # Use mock embeddings for demo (no actual model needed)
    mock_provider = MockEmbeddingProvider(dimension=384)
    
    ingestor = QdrantIngestor(
        config=config,
        embedding_provider=mock_provider,
        auto_create_collection=True,
    )
    print(f"  ✓ Collection '{config.collection_name}' ready")
    
    # Step 3: Ingest chunks
    print("\n[3/4] Ingesting chunks...")
    result = ingestor.ingest_jsonl(
        jsonl_path=jsonl_path,
        batch_size=10,
        show_progress=False,
        skip_duplicates=True,
    )
    print(f"  ✓ Ingested: {result.inserted} chunks")
    print(f"  ✓ Skipped: {result.skipped_duplicates} duplicates")
    print(f"  ✓ Duration: {result.duration_seconds:.2f}s")
    
    # Show collection stats
    stats = ingestor.get_collection_stats()
    print(f"\n  Collection Stats:")
    print(f"    - Points: {stats.get('points_count', 0)}")
    print(f"    - Status: {stats.get('status', 'unknown')}")
    
    # Step 4: Execute searches
    print("\n[4/4] Executing sample searches...")
    
    # Share the same client instance to access the same in-memory collection
    retriever = QdrantRetriever(
        config=config,
        embedding_provider=mock_provider,
    )
    # Use the same client as the ingestor for in-memory mode
    retriever.client = ingestor.client
    
    # Search queries to demonstrate
    queries = [
        ("machine learning basics", None),
        ("neural network architecture", SearchFilter(modalities=["image"])),
        ("Python libraries for data science", SearchFilter(file_types=["epub"])),
        ("clustering algorithms", None),
    ]
    
    for query, search_filter in queries:
        print(f"\n{'─' * 60}")
        print(f"QUERY: \"{query}\"")
        if search_filter:
            filter_desc = []
            if search_filter.modalities:
                filter_desc.append(f"modality={search_filter.modalities}")
            if search_filter.file_types:
                filter_desc.append(f"file_type={search_filter.file_types}")
            print(f"FILTER: {', '.join(filter_desc)}")
        print("─" * 60)
        
        results = retriever.search(
            query=query,
            top_k=3,
            filter=search_filter,
        )
        
        if not results:
            print("  No results found.")
        else:
            for i, r in enumerate(results, 1):
                print(f"\n  [{i}] Score: {r.score:.4f}")
                print(f"      Citation: {r.citation}")
                print(f"      Modality: {r.modality}")
                if r.asset_path:
                    print(f"      Asset: {r.asset_path}")
                text_preview = r.text[:150].replace("\n", " ")
                print(f"      Text: {text_preview}...")
    
    # Demonstrate rich result structure
    print("\n" + "=" * 70)
    print("SAMPLE RICH RESULT (JSON)")
    print("=" * 70)
    
    sample_results = retriever.search("deep learning neural networks", top_k=1)
    if sample_results:
        rich_result = sample_results[0]
        print(json.dumps(rich_result.to_dict(), indent=2))
    
    # Cleanup
    os.unlink(jsonl_path)
    
    print("\n" + "=" * 70)
    print("✓ DEMO COMPLETE")
    print("=" * 70)
    
    return True


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    try:
        success = run_demo()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
