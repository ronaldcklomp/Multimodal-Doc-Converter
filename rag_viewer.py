#!/usr/bin/env python3
"""
RAG-VIEWER: Interactive Multimodal Search with Image Display
==============================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

Features:
1. Semantic search on Qdrant collection
2. Display text context + breadcrumb hierarchy
3. Resolve asset paths correctly (data/[doc_folder]/assets/)
4. Open images automatically using PIL/system command

Author: Claude 4.5 Opus
Date: 2025-12-29
"""
import sys
import json
from pathlib import Path
from typing import Optional, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from database.config import QdrantConfig, EmbeddingModel
from database.retriever import QdrantRetriever, RichSearchResult


# ============================================================================
# DOCUMENT FOLDER MAPPING
# ============================================================================

DOC_FOLDER_MAPPING = {
    "a4c2916a64c2": "combat_aircraft_v2_output",  # Combat Aircraft
    "ae1c6740af40": "PCWorld_July_2025_USA_v2_output",  # PCWorld
}


def resolve_asset_path(asset_path: Optional[str], doc_id: Optional[str]) -> Optional[Path]:
    """
    Resolve asset path to actual file location.
    
    Maps: assets/a4c2916a64c2_022_figure_43.png
    To:   data/combat_aircraft_v2_output/assets/a4c2916a64c2_022_figure_43.png
    
    Args:
        asset_path: Path from search result (e.g., "assets/file.png")
        doc_id: Document ID to determine folder
        
    Returns:
        Full path to asset file or None if not found
    """
    if not asset_path or not doc_id:
        return None
    
    # Get document folder from mapping
    doc_folder = DOC_FOLDER_MAPPING.get(doc_id)
    if not doc_folder:
        return None
    
    # Resolve full path
    full_path = Path("data") / doc_folder / asset_path
    
    # Verify file exists
    if full_path.exists():
        return full_path
    
    return None


def open_image(image_path: Path) -> bool:
    """
    Open image using system default viewer or PIL.
    
    Args:
        image_path: Path to image file
        
    Returns:
        True if image was opened successfully
    """
    try:
        import subprocess
        import platform
        
        # Try system-specific opener
        if platform.system() == "Darwin":  # macOS
            subprocess.run(["open", str(image_path)])
        elif platform.system() == "Windows":
            subprocess.run(["start", str(image_path)], shell=True)
        else:  # Linux
            subprocess.run(["xdg-open", str(image_path)])
        
        return True
    except Exception as e:
        print(f"Error opening image: {e}")
        
        # Fallback: Try PIL
        try:
            from PIL import Image
            img = Image.open(image_path)
            img.show()
            return True
        except Exception as e2:
            print(f"PIL fallback failed: {e2}")
            return False


def format_result(result: RichSearchResult, index: int) -> str:
    """
    Format a search result for display.
    
    Args:
        result: Search result object
        index: Result index (1, 2, 3...)
        
    Returns:
        Formatted string for display
    """
    lines = []
    
    # Header
    lines.append(f"\n{'─' * 100}")
    lines.append(f"RESULT {index}: Score {result.score:.4f}")
    lines.append(f"{'─' * 100}")
    
    # Source info
    lines.append(f"\n📄 SOURCE")
    lines.append(f"   File: {result.source}")
    lines.append(f"   Page: {result.page_number}")
    lines.append(f"   Doc ID: {result.doc_id}")
    lines.append(f"   Modality: {result.modality.upper()}")
    
    # Hierarchy
    if result.breadcrumb:
        lines.append(f"\n📍 HIERARCHY")
        breadcrumb_str = " → ".join(result.breadcrumb)
        # Wrap long breadcrumbs
        if len(breadcrumb_str) > 90:
            breadcrumb_str = breadcrumb_str[:87] + "..."
        lines.append(f"   {breadcrumb_str}")
    
    # Asset path (if applicable)
    if result.asset_path:
        lines.append(f"\n🖼️  ASSET")
        lines.append(f"   Path: {result.asset_path}")
        
        # Check if file exists and show full resolution
        full_path = resolve_asset_path(result.asset_path, result.doc_id)
        if full_path:
            try:
                from PIL import Image
                img = Image.open(full_path)
                w, h = img.size
                lines.append(f"   ✓ File exists: {full_path}")
                lines.append(f"   Resolution: {w}x{h}px")
            except Exception as e:
                lines.append(f"   ⚠️ Could not read image: {e}")
        else:
            lines.append(f"   ✗ File not found")
    
    # Content
    lines.append(f"\n📝 CONTENT")
    content = result.text
    if len(content) > 200:
        content = content[:197] + "..."
    for line in content.split("\n"):
        lines.append(f"   {line}")
    
    return "\n".join(lines)


def run_query(query: str, top_k: int = 3) -> List[RichSearchResult]:
    """
    Execute a search query and return results.
    
    Args:
        query: Search query text
        top_k: Number of top results
        
    Returns:
        List of RichSearchResult objects
    """
    print(f"\n{'=' * 100}")
    print(f"SEARCHING: '{query}'")
    print(f"{'=' * 100}")
    
    # Initialize retriever
    config = QdrantConfig(
        local_path="./qdrant_storage",
        embedding_model=EmbeddingModel.MINILM,
    )
    retriever = QdrantRetriever(config=config)
    
    # Execute search
    print(f"\n⏳ Searching Qdrant...")
    results = retriever.search(query, top_k=top_k)
    
    if not results:
        print("\n❌ No results found")
        return []
    
    # Display results
    print(f"\n✓ Found {len(results)} results\n")
    
    for i, result in enumerate(results, 1):
        print(format_result(result, i))
    
    return results


def interactive_rag_viewer():
    """
    Interactive RAG viewer with query loop.
    
    Supports:
    - Semantic search on ingested documents
    - Display of text content with hierarchy
    - Automatic image opening
    """
    print("\n" + "=" * 100)
    print("RAG VIEWER: Multimodal Search with Image Display")
    print("=" * 100)
    print("ENGINE_USE: all-MiniLM-L6-v2 (384-dim) | Qdrant Vector Store")
    print("\nCommands:")
    print("  Type a search query and press Enter")
    print("  Type 'open [n]' to open the image from result N (e.g., 'open 1')")
    print("  Type 'quit' to exit")
    print("=" * 100)
    
    last_results = []
    
    while True:
        try:
            query = input("\n🔍 Query > ").strip()
            
            if not query:
                continue
            
            if query.lower() == "quit":
                print("\nGoodbye!")
                break
            
            # Handle "open N" command
            if query.lower().startswith("open "):
                try:
                    index = int(query.split()[1]) - 1
                    if 0 <= index < len(last_results):
                        result = last_results[index]
                        if result.asset_path:
                            full_path = resolve_asset_path(result.asset_path, result.doc_id)
                            if full_path:
                                print(f"\n🖼️  Opening: {full_path}")
                                if open_image(full_path):
                                    print("✓ Image opened successfully")
                                else:
                                    print("✗ Failed to open image")
                            else:
                                print(f"✗ Asset not found: {result.asset_path}")
                        else:
                            print("✗ No image in this result")
                    else:
                        print(f"✗ Invalid result index: {index + 1}")
                except (ValueError, IndexError):
                    print("Usage: open <result_number> (e.g., 'open 1')")
                continue
            
            # Execute search
            last_results = run_query(query, top_k=3)
        
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


def test_query_2_with_image_display():
    """
    Test Query 2 (B-2 Spirit) with automatic image display.
    
    This is the critical test to verify:
    1. Asset paths are correctly resolved
    2. Images are found and opened
    """
    print("\n" + "=" * 100)
    print("TEST: Query 2 - B-2 Spirit Technical Illustration")
    print("=" * 100)
    
    query = "B-2 Spirit technical illustration"
    results = run_query(query, top_k=3)
    
    if not results:
        return
    
    # Try to open first image result
    print(f"\n{'=' * 100}")
    print("AUTOMATIC IMAGE OPENING")
    print(f"{'=' * 100}")
    
    for result in results:
        if result.asset_path and result.modality == "image":
            full_path = resolve_asset_path(result.asset_path, result.doc_id)
            
            print(f"\nFound image: {result.asset_path}")
            print(f"Full path: {full_path}")
            print(f"Exists: {full_path.exists() if full_path else False}")
            
            if full_path and full_path.exists():
                print(f"\n🖼️  Opening image automatically...")
                if open_image(full_path):
                    print("✓ Image opened successfully!")
                else:
                    print("⚠️  Failed to open image with system viewer")
                    print(f"   Try: open {full_path}")
                break
    
    print("\n" + "=" * 100)


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="RAG Viewer: Interactive multimodal search with image display"
    )
    parser.add_argument(
        "--test-query-2",
        action="store_true",
        help="Run Query 2 test with automatic image display",
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Execute a single query and exit",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of top results to return",
    )
    
    args = parser.parse_args()
    
    if args.test_query_2:
        test_query_2_with_image_display()
    elif args.query:
        run_query(args.query, top_k=args.top_k)
    else:
        interactive_rag_viewer()


if __name__ == "__main__":
    main()
