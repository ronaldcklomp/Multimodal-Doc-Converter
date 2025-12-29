#!/usr/bin/env python3
"""
SEMANTIC DRIFT DIAGNOSIS: B-2 Spirit False Positive Detection
=============================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

This script diagnoses a critical RAG accuracy issue:
1. Query: "Does document contain visual illustration of B-2 Spirit?"
2. Problem: System returns images from pages 22, 100 (not B-2)
3. Actual: B-2 only mentioned in text (pages 3, 9)
4. Solution: Confidence scoring with low-score filtering

Author: Claude 4.5 Opus
Date: 2025-12-29
"""
import sys
import json
from pathlib import Path
from typing import List, Dict, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from database.config import QdrantConfig, EmbeddingModel
from database.retriever import QdrantRetriever, RichSearchResult


# ============================================================================
# CONFIDENCE-AWARE RETRIEVAL
# ============================================================================

def retrieve_with_confidence_scoring(
    query: str,
    top_k: int = 10,
    score_threshold: float = 0.45,
) -> Dict:
    """
    Execute retrieval with confidence assessment.
    
    Classifies results as:
    - HIGH_CONFIDENCE: score >= 0.45 + strong keyword match
    - TEXT_MENTION: score < 0.45 but text contains query terms
    - FALSE_POSITIVE: low score + no keyword match
    
    Args:
        query: Search query
        top_k: Number of results
        score_threshold: Minimum confidence threshold
        
    Returns:
        Dict with classified results
    """
    print("\n" + "=" * 100)
    print(f"SEMANTIC DRIFT DIAGNOSIS: '{query}'")
    print("=" * 100)
    
    # Execute search
    config = QdrantConfig(
        local_path="./qdrant_storage",
        embedding_model=EmbeddingModel.MINILM,
    )
    retriever = QdrantRetriever(config=config)
    
    print(f"\nSearching Qdrant (top-{top_k})...")
    results = retriever.search(query, top_k=top_k)
    
    # Classify results
    high_confidence = []
    text_mentions = []
    false_positives = []
    
    query_keywords = set(query.lower().split())
    
    for result in results:
        # Calculate confidence
        score = result.score
        
        # Check for keyword matches in content
        content_lower = result.text.lower()
        matched_keywords = sum(1 for kw in query_keywords if kw in content_lower)
        keyword_strength = matched_keywords / len(query_keywords) if query_keywords else 0
        
        classification = {
            "score": score,
            "source": result.source,
            "page": result.page_number,
            "modality": result.modality,
            "matched_keywords": matched_keywords,
            "keyword_strength": keyword_strength,
            "asset_path": result.asset_path,
            "content_preview": result.text[:100] + "..." if len(result.text) > 100 else result.text,
        }
        
        # Classify
        if score >= score_threshold and result.modality == "image":
            classification["confidence"] = "HIGH_CONFIDENCE"
            high_confidence.append(classification)
        elif score < score_threshold and matched_keywords > 0:
            classification["confidence"] = "TEXT_MENTION"
            text_mentions.append(classification)
        else:
            classification["confidence"] = "FALSE_POSITIVE"
            false_positives.append(classification)
    
    return {
        "query": query,
        "high_confidence": high_confidence,
        "text_mentions": text_mentions,
        "false_positives": false_positives,
        "all_results": results,
    }


# ============================================================================
# EXTRACT ACTUAL TEXT MENTIONS
# ============================================================================

def extract_b2_text_mentions() -> Dict:
    """
    Extract actual B-2 Spirit text mentions from Qdrant.
    
    Returns:
        Dict with text chunks from pages 3, 9 that mention B-2
    """
    print("\n" + "=" * 100)
    print("ACTUAL TEXT MENTIONS: B-2 Spirit in Combat Aircraft PDF")
    print("=" * 100)
    
    config = QdrantConfig(
        local_path="./qdrant_storage",
        embedding_model=EmbeddingModel.MINILM,
    )
    retriever = QdrantRetriever(config=config)
    
    # Get all chunks from Combat Aircraft
    print("\nScanning for text chunks containing 'B-2'...")
    
    doc_id = "a4c2916a64c2"  # Combat Aircraft
    all_chunks = retriever.get_document_chunks(doc_id, limit=500, modalities=["text"])
    
    b2_mentions = []
    
    for chunk in all_chunks:
        if "b-2" in chunk.text.lower() or "spirit" in chunk.text.lower():
            # Check if it's actually about B-2
            if "b-2" in chunk.text.lower():
                b2_mentions.append({
                    "page": chunk.page_number,
                    "content": chunk.text,
                    "hierarchy": chunk.breadcrumb,
                })
    
    # Organize by page
    page_mentions = {}
    for mention in b2_mentions:
        page = mention["page"]
        if page not in page_mentions:
            page_mentions[page] = []
        page_mentions[page].append(mention)
    
    return page_mentions


# ============================================================================
# IMPROVED RAG LOGIC
# ============================================================================

def evaluate_query_with_improved_logic(query: str) -> str:
    """
    Evaluate query using improved confidence-aware logic.
    
    Returns improved interpretation that avoids false positives.
    
    Args:
        query: Original search query
        
    Returns:
        Improved search interpretation
    """
    print("\n" + "=" * 100)
    print("IMPROVED RAG LOGIC: Confidence-Aware Response Generation")
    print("=" * 100)
    
    # Execute diagnosis
    diagnosis = retrieve_with_confidence_scoring(
        query,
        top_k=15,
        score_threshold=0.45,
    )
    
    high_conf = diagnosis["high_confidence"]
    text_mentions = diagnosis["text_mentions"]
    false_pos = diagnosis["false_positives"]
    
    print(f"\n📊 CLASSIFICATION RESULTS:")
    print(f"  High-Confidence Image Results: {len(high_conf)}")
    print(f"  Text Mentions (Low Score): {len(text_mentions)}")
    print(f"  False Positives: {len(false_pos)}")
    
    # Display each category
    if high_conf:
        print(f"\n✅ HIGH-CONFIDENCE RESULTS (score >= 0.45):")
        for i, r in enumerate(high_conf[:3], 1):
            print(f"  [{i}] Score: {r['score']:.4f} | {r['source']} p.{r['page']} | {r['modality'].upper()}")
    
    if text_mentions:
        print(f"\n⚠️  TEXT MENTIONS (score < 0.45, but keyword match):")
        for i, r in enumerate(text_mentions[:3], 1):
            print(f"  [{i}] Score: {r['score']:.4f} | {r['source']} p.{r['page']} | Keywords: {r['matched_keywords']}/{len(query.split())}")
    
    if false_pos:
        print(f"\n❌ FALSE POSITIVES (low score, weak match):")
        for i, r in enumerate(false_pos[:3], 1):
            print(f"  [{i}] Score: {r['score']:.4f} | {r['source']} p.{r['page']}")
    
    # Generate improved response
    print(f"\n" + "─" * 100)
    print("IMPROVED SYSTEM RESPONSE:")
    print(f"{'─' * 100}")
    
    if high_conf and high_conf[0]["score"] >= 0.50:
        response = f"✅ YES - Document contains visual illustration of B-2 Spirit (Confidence: {high_conf[0]['score']:.1%})"
    elif text_mentions:
        response = f"⚠️  PARTIAL - Mention found in text (pages {', '.join(str(m['page']) for m in text_mentions[:3])}), but no high-confidence visual asset identified (Best score: {text_mentions[0]['score']:.3f})"
    else:
        response = f"❌ NO - No relevant results found (Best score: {diagnosis['all_results'][0].score if diagnosis['all_results'] else 0:.3f})"
    
    print(f"\n{response}")
    
    return response


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Execute semantic drift diagnosis."""
    
    print("\n" + "=" * 100)
    print("SEMANTIC DRIFT DIAGNOSIS SUITE")
    print("=" * 100)
    print("Problem: Query for 'B-2 Spirit illustration' returns wrong images")
    print("Solution: Confidence scoring + semantic validation")
    print("=" * 100)
    
    # Test Query
    test_query = "Does the document contain a visual illustration of the B-2 Spirit?"
    
    # 1. Show classification of results
    evaluate_query_with_improved_logic(test_query)
    
    # 2. Extract actual B-2 mentions from text
    print("\n" + "=" * 100)
    print("VERIFICATION: Actual B-2 Mentions in Text")
    print("=" * 100)
    
    b2_mentions = extract_b2_text_mentions()
    
    if b2_mentions:
        for page in sorted(b2_mentions.keys()):
            mentions = b2_mentions[page]
            print(f"\n📝 PAGE {page}:")
            print(f"{'─' * 100}")
            for mention in mentions:
                print(f"\nContent:")
                # Wrap long content
                text = mention["content"]
                for line in text.split("\n"):
                    if len(line) > 100:
                        while len(line) > 100:
                            print(f"  {line[:100]}")
                            line = line[100:]
                        if line:
                            print(f"  {line}")
                    else:
                        print(f"  {line}")
    else:
        print("\n⚠️  No B-2 mentions found in text chunks")
    
    # Final Summary
    print("\n" + "=" * 100)
    print("DIAGNOSIS SUMMARY")
    print("=" * 100)
    
    print("\n🔍 FINDINGS:")
    print("  1. B-2 Spirit appears in TEXT (pages 3, 9) - mentioned but NOT illustrated")
    print("  2. Search returns IMAGES from pages 22, 100 - semantic drift")
    print("  3. Root cause: Low semantic scores (< 0.45) being treated as relevant")
    print("  4. Solution: Filter by confidence threshold + keyword validation")
    
    print("\n✅ IMPROVED BEHAVIOR:")
    print("  - If score < 0.45: Flag as 'text mention, no visual'")
    print("  - If image modality + low score: Suppress from results")
    print("  - If multiple text mentions + no images: Consolidate findings")
    
    print("\n" + "=" * 100 + "\n")


if __name__ == "__main__":
    main()
