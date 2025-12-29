#!/usr/bin/env python3
"""
High-Density RAG Optimization & Validation Script
==================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

This script implements the optimization strategy for high-scale processing:
1. Clear Qdrant collection for clean test
2. Re-process documents with optimized settings:
   - Intelligent asset filtering (100x100px, 10KB minimum)
   - Optimized chunking (800 chars / ~150 tokens, 100 char / ~20 token overlap)
   - Strict sentence-aware splitting
3. Run validation queries with multi-result analysis
4. Report retrieval scores and quality metrics

Target: Retrieval scores > 0.6, eliminate hallucinated hits
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from database.config import QdrantConfig, create_collection_if_not_exists
from database.embeddings import get_embedding_provider
from database.ingestor import QdrantIngestor
from database.retriever import QdrantRetriever
from qdrant_client import QdrantClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def clear_collection(config: QdrantConfig) -> bool:
    """Clear the Qdrant collection for a clean test."""
    logger.info("=" * 80)
    logger.info("STEP 1: CLEARING QDRANT COLLECTION")
    logger.info("=" * 80)
    
    client = config.get_client()
    collection_name = config.collection_name
    
    try:
        # Check if collection exists
        collections = client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
        
        if exists:
            logger.info(f"Deleting existing collection: {collection_name}")
            client.delete_collection(collection_name)
            logger.info("✓ Collection deleted successfully")
        else:
            logger.info(f"Collection '{collection_name}' does not exist")
        
        # Recreate collection with optimized settings
        logger.info(f"Creating fresh collection: {collection_name}")
        create_collection_if_not_exists(client, config, recreate=False)
        logger.info("✓ Collection created successfully")
        
        return True
    except Exception as e:
        logger.error(f"Failed to clear collection: {e}")
        return False


def process_documents_optimized() -> bool:
    """
    Re-process documents with optimized settings.
    
    Uses run_test_pipeline.py with modified parameters.
    """
    logger.info("=" * 80)
    logger.info("STEP 2: RE-PROCESSING DOCUMENTS WITH OPTIMIZATIONS")
    logger.info("=" * 80)
    logger.info("Optimizations:")
    logger.info("  - Asset filtering: 100x100px minimum, 10KB minimum file size")
    logger.info("  - Chunking: ~800 characters (~150 tokens)")
    logger.info("  - Overlap: ~100 characters (~20 tokens)")
    logger.info("  - Sentence-aware splitting: ENFORCED")
    logger.info("=" * 80)
    
    import subprocess
    
    # Check if run_test_pipeline.py exists
    pipeline_script = Path(__file__).parent / "run_test_pipeline.py"
    if not pipeline_script.exists():
        logger.error(f"Pipeline script not found: {pipeline_script}")
        return False
    
    try:
        # Run the pipeline with optimized parameters
        # The chunker defaults have been updated in the code
        # Note: Processing all PDFs can take 15-20 minutes
        result = subprocess.run(
            [sys.executable, str(pipeline_script)],
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minute timeout for full processing
        )
        
        if result.returncode == 0:
            logger.info("✓ Document processing completed successfully")
            logger.info("Output:")
            for line in result.stdout.split('\n')[-20:]:  # Last 20 lines
                if line.strip():
                    logger.info(f"  {line}")
            return True
        else:
            logger.error(f"Document processing failed with code {result.returncode}")
            logger.error(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Document processing timed out")
        return False
    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        return False


def run_validation_queries(
    config: QdrantConfig,
    top_k: int = 3
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Run the 3 test queries and return Top 3 results for each.
    
    Queries:
    1. "ROG Ally" - gaming handheld device
    2. "B-2 Spirit" - stealth bomber aircraft
    3. "Google Search AI" - AI-powered search features
    
    Returns:
        Dict mapping query to list of results with score, source, page, snippet
    """
    logger.info("=" * 80)
    logger.info("STEP 3: VALIDATION QUERIES")
    logger.info("=" * 80)
    
    test_queries = [
        "ROG Ally",
        "B-2 Spirit",
        "Google Search AI",
    ]
    
    retriever = QdrantRetriever(config=config)
    results = {}
    
    for query in test_queries:
        logger.info(f"\nQuery: '{query}'")
        logger.info("-" * 80)
        
        try:
            # Search with the retriever
            search_results = retriever.search(
                query=query,
                top_k=top_k,
                filter=None,
            )
            
            query_results = []
            for idx, hit in enumerate(search_results, 1):
                # RichSearchResult has direct attributes, not payload
                score = hit.score
                source_file = hit.source
                page_number = hit.page_number
                content = hit.text
                modality = hit.modality
                
                # Create 200-char snippet
                snippet = content[:200].strip()
                if len(content) > 200:
                    snippet += "..."
                
                result_item = {
                    "rank": idx,
                    "score": round(score, 4),
                    "source": Path(source_file).name if source_file else "Unknown",
                    "page": page_number,
                    "modality": modality,
                    "snippet": snippet,
                }
                
                query_results.append(result_item)
                
                # Log the result
                logger.info(f"  [{idx}] Score: {result_item['score']:.4f}")
                logger.info(f"      Source: {result_item['source']}")
                logger.info(f"      Page: {result_item['page']}")
                logger.info(f"      Modality: {result_item['modality']}")
                logger.info(f"      Snippet: {result_item['snippet']}")
                logger.info("")
            
            results[query] = query_results
            
        except Exception as e:
            logger.error(f"Query '{query}' failed: {e}")
            results[query] = []
    
    return results


def analyze_results(
    results: Dict[str, List[Dict[str, Any]]],
    target_score: float = 0.6
) -> Dict[str, Any]:
    """
    Analyze retrieval results and generate quality report.
    
    Args:
        results: Query results from run_validation_queries
        target_score: Minimum acceptable score threshold
        
    Returns:
        Analysis report with metrics
    """
    logger.info("=" * 80)
    logger.info("STEP 4: RESULTS ANALYSIS")
    logger.info("=" * 80)
    
    analysis = {
        "total_queries": len(results),
        "queries_meeting_target": 0,
        "avg_top1_score": 0.0,
        "avg_top3_score": 0.0,
        "min_score": 1.0,
        "max_score": 0.0,
        "target_score": target_score,
        "quality_issues": [],
    }
    
    if not results:
        logger.warning("No results to analyze")
        return analysis
    
    top1_scores = []
    all_scores = []
    
    for query, query_results in results.items():
        if not query_results:
            analysis["quality_issues"].append(f"Query '{query}' returned no results")
            continue
        
        # Top-1 score
        top1_score = query_results[0]["score"]
        top1_scores.append(top1_score)
        
        # All scores for this query
        query_scores = [r["score"] for r in query_results]
        all_scores.extend(query_scores)
        
        # Track min/max
        analysis["min_score"] = min(analysis["min_score"], min(query_scores))
        analysis["max_score"] = max(analysis["max_score"], max(query_scores))
        
        # Check if query meets target
        if top1_score >= target_score:
            analysis["queries_meeting_target"] += 1
        else:
            analysis["quality_issues"].append(
                f"Query '{query}' below target: {top1_score:.4f} < {target_score}"
            )
        
        # Check for irrelevant results (score < 0.3)
        for result in query_results:
            if result["score"] < 0.3:
                analysis["quality_issues"].append(
                    f"Query '{query}' has low-quality result: "
                    f"score={result['score']:.4f}, source={result['source']}"
                )
    
    # Calculate averages
    if top1_scores:
        analysis["avg_top1_score"] = sum(top1_scores) / len(top1_scores)
    if all_scores:
        analysis["avg_top3_score"] = sum(all_scores) / len(all_scores)
    
    # Log summary
    logger.info(f"Total Queries: {analysis['total_queries']}")
    logger.info(f"Queries Meeting Target (>{target_score}): {analysis['queries_meeting_target']}")
    logger.info(f"Average Top-1 Score: {analysis['avg_top1_score']:.4f}")
    logger.info(f"Average Top-3 Score: {analysis['avg_top3_score']:.4f}")
    logger.info(f"Score Range: [{analysis['min_score']:.4f}, {analysis['max_score']:.4f}]")
    
    if analysis["quality_issues"]:
        logger.warning(f"\nQuality Issues Found: {len(analysis['quality_issues'])}")
        for issue in analysis["quality_issues"]:
            logger.warning(f"  - {issue}")
    else:
        logger.info("\n✓ No quality issues detected!")
    
    return analysis


def save_results(
    results: Dict[str, List[Dict[str, Any]]],
    analysis: Dict[str, Any],
    output_path: Path
) -> None:
    """Save results and analysis to JSON file."""
    output_data = {
        "validation_results": results,
        "analysis": analysis,
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✓ Results saved to: {output_path}")


def main():
    """Main execution flow."""
    logger.info("=" * 80)
    logger.info("HIGH-DENSITY RAG OPTIMIZATION & VALIDATION")
    logger.info("=" * 80)
    logger.info("Target: Retrieval scores > 0.6, eliminate hallucinated hits")
    logger.info("=" * 80 + "\n")
    
    # Configuration
    config = QdrantConfig()
    
    # Step 1: Clear collection
    if not clear_collection(config):
        logger.error("Failed to clear collection. Aborting.")
        sys.exit(1)
    
    print()
    
    # Step 2: Re-process documents
    if not process_documents_optimized():
        logger.error("Failed to process documents. Aborting.")
        sys.exit(1)
    
    print()
    
    # Step 3: Run validation queries
    results = run_validation_queries(config, top_k=3)
    
    print()
    
    # Step 4: Analyze results
    analysis = analyze_results(results, target_score=0.6)
    
    print()
    
    # Save results
    output_path = Path(__file__).parent / "test_output" / "validation_results.json"
    save_results(results, analysis, output_path)
    
    # Final summary
    logger.info("=" * 80)
    logger.info("OPTIMIZATION & VALIDATION COMPLETE")
    logger.info("=" * 80)
    
    success_rate = (analysis["queries_meeting_target"] / analysis["total_queries"]) * 100
    logger.info(f"Success Rate: {success_rate:.1f}% ({analysis['queries_meeting_target']}/{analysis['total_queries']} queries)")
    logger.info(f"Average Top-1 Score: {analysis['avg_top1_score']:.4f}")
    
    if success_rate >= 100.0 and analysis["avg_top1_score"] >= 0.6:
        logger.info("\n🎉 OPTIMIZATION SUCCESSFUL! All targets met.")
        sys.exit(0)
    elif success_rate >= 66.0:
        logger.info("\n⚠️  PARTIAL SUCCESS. Some queries need improvement.")
        sys.exit(0)
    else:
        logger.error("\n❌ OPTIMIZATION NEEDS WORK. Scores below target.")
        sys.exit(1)


if __name__ == "__main__":
    main()
