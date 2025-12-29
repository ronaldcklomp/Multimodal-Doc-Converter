#!/usr/bin/env python3
"""
Retrieval Validation Script
============================
Run validation queries and analyze results without re-processing.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent / "src"))

from database.config import QdrantConfig
from database.retriever import QdrantRetriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_validation_queries(config: QdrantConfig, top_k: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """Run the 3 test queries and return Top 3 results for each."""
    logger.info("=" * 80)
    logger.info("VALIDATION QUERIES - TOP 3 RESULTS PER QUERY")
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
            search_results = retriever.search(query=query, top_k=top_k, filter=None)
            
            query_results = []
            for idx, hit in enumerate(search_results, 1):
                score = hit.score
                source_file = hit.source
                page_number = hit.page_number
                content = hit.text
                modality = hit.modality
                
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
                
                logger.info(f"  [{idx}] Score: {result_item['score']:.4f}")
                logger.info(f"      Source: {result_item['source']}")
                logger.info(f"      Page: {result_item['page']}")
                logger.info(f"      Snippet: {result_item['snippet'][:100]}...")
                logger.info("")
            
            results[query] = query_results
            
        except Exception as e:
            logger.error(f"Query '{query}' failed: {e}")
            results[query] = []
    
    return results


def analyze_results(results: Dict[str, List[Dict[str, Any]]], target_score: float = 0.6) -> Dict[str, Any]:
    """Analyze retrieval results."""
    logger.info("=" * 80)
    logger.info("RESULTS ANALYSIS")
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
        return analysis
    
    top1_scores = []
    all_scores = []
    
    for query, query_results in results.items():
        if not query_results:
            analysis["quality_issues"].append(f"Query '{query}' returned no results")
            continue
        
        top1_score = query_results[0]["score"]
        top1_scores.append(top1_score)
        
        query_scores = [r["score"] for r in query_results]
        all_scores.extend(query_scores)
        
        analysis["min_score"] = min(analysis["min_score"], min(query_scores))
        analysis["max_score"] = max(analysis["max_score"], max(query_scores))
        
        if top1_score >= target_score:
            analysis["queries_meeting_target"] += 1
        else:
            analysis["quality_issues"].append(
                f"Query '{query}' below target: {top1_score:.4f} < {target_score}"
            )
        
        for result in query_results:
            if result["score"] < 0.3:
                analysis["quality_issues"].append(
                    f"Query '{query}' low-quality result: score={result['score']:.4f}, source={result['source']}"
                )
    
    if top1_scores:
        analysis["avg_top1_score"] = sum(top1_scores) / len(top1_scores)
    if all_scores:
        analysis["avg_top3_score"] = sum(all_scores) / len(all_scores)
    
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


def main():
    config = QdrantConfig()
    
    logger.info("=" * 80)
    logger.info("RETRIEVAL VALIDATION")
    logger.info("=" * 80)
    logger.info(f"Collection: {config.collection_name}")
    logger.info(f"Target Score: > 0.6")
    logger.info("=" * 80 + "\n")
    
    # Run validation queries
    results = run_validation_queries(config, top_k=3)
    
    print()
    
    # Analyze results
    analysis = analyze_results(results, target_score=0.6)
    
    # Save results
    output_path = Path(__file__).parent / "test_output" / "validation_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump({"validation_results": results, "analysis": analysis}, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✓ Results saved to: {output_path}")
    
    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("VALIDATION COMPLETE")
    logger.info("=" * 80)
    
    success_rate = (analysis["queries_meeting_target"] / analysis["total_queries"]) * 100
    logger.info(f"Success Rate: {success_rate:.1f}% ({analysis['queries_meeting_target']}/{analysis['total_queries']} queries)")
    logger.info(f"Average Top-1 Score: {analysis['avg_top1_score']:.4f}")
    
    if success_rate >= 100.0 and analysis["avg_top1_score"] >= 0.6:
        logger.info("\n🎉 ALL TARGETS MET!")
    elif success_rate >= 66.0:
        logger.info("\n⚠️  PARTIAL SUCCESS")
    else:
        logger.info("\n❌ NEEDS IMPROVEMENT")


if __name__ == "__main__":
    main()
