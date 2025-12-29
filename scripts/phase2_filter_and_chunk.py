#!/usr/bin/env python3
"""
PHASE 2: Intelligent Asset Filtering + Optimized Chunking
===========================================================
1. Filter assets: Only keep PNG > 100x100px AND > 10KB
2. Optimize chunking: 800 chars, 100 char overlap, sentence-aware
3. Process all 3 files (Hybrid, PCWorld, Combat Aircraft)
4. Output to optimized JSONL
"""

import json
import os
import re
import shutil
from pathlib import Path

from PIL import Image

# Asset filtering thresholds
MIN_WIDTH_PX = 100
MIN_HEIGHT_PX = 100
MIN_FILE_SIZE_KB = 10

# Chunking parameters
MAX_CHUNK_CHARS = 800
OVERLAP_CHARS = 100
SENTENCE_PATTERN = re.compile(r'[.!?]\s+')


def filter_assets():
    """Filter PNG files by size and dimensions."""
    assets_dir = Path("./data/assets/raw")
    filtered_count = 0
    discarded_count = 0
    
    if not assets_dir.exists():
        print("✗ No assets directory")
        return 0, 0
    
    png_files = list(assets_dir.glob("*.png"))
    print(f"\n[ASSET FILTERING]")
    print(f"Processing {len(png_files)} PNG files")
    print(f"Thresholds: {MIN_WIDTH_PX}x{MIN_HEIGHT_PX}px, >{MIN_FILE_SIZE_KB}KB")
    
    for png_file in png_files:
        try:
            # Check file size
            file_size_kb = png_file.stat().st_size / 1024
            if file_size_kb < MIN_FILE_SIZE_KB:
                print(f"  ✗ {png_file.name}: {file_size_kb:.1f}KB < {MIN_FILE_SIZE_KB}KB (DISCARD)")
                png_file.unlink()
                discarded_count += 1
                continue
            
            # Check image dimensions
            with Image.open(png_file) as img:
                width, height = img.size
                if width < MIN_WIDTH_PX or height < MIN_HEIGHT_PX:
                    print(f"  ✗ {png_file.name}: {width}x{height}px (DISCARD)")
                    png_file.unlink()
                    discarded_count += 1
                    continue
            
            print(f"  ✓ {png_file.name}: {width}x{height}px, {file_size_kb:.1f}KB")
            filtered_count += 1
        
        except Exception as e:
            print(f"  ✗ {png_file.name}: Error - {e}")
            png_file.unlink()
            discarded_count += 1
    
    print(f"\nFiltering complete: {filtered_count} kept, {discarded_count} discarded")
    return filtered_count, discarded_count


def chunk_text_with_overlap(text: str) -> list:
    """
    Split text into 800-char chunks with 100-char overlap.
    Sentence-aware: never break in middle of sentence.
    """
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    
    chunks = []
    sentences = SENTENCE_PATTERN.split(text)
    
    # Rebuild sentences with endings
    sentences_full = []
    pos = 0
    for sent in sentences:
        if sent.strip():
            start = text.find(sent, pos)
            if start >= 0:
                end = start + len(sent)
                if end < len(text) and text[end] in '.!?':
                    end += 1
                    if end < len(text) and text[end] == ' ':
                        end += 1
                sentences_full.append(text[start:end].strip())
                pos = end
    
    if not sentences_full:
        return [text]
    
    current_chunk = ""
    for sentence in sentences_full:
        if len(current_chunk) + len(sentence) + 1 > MAX_CHUNK_CHARS and current_chunk:
            chunks.append(current_chunk.strip())
            # Create overlap from end of chunk
            overlap = current_chunk[-OVERLAP_CHARS:].split()
            if overlap:
                overlap_start = current_chunk.rfind(overlap[0])
                if overlap_start >= 0:
                    current_chunk = current_chunk[overlap_start:].strip() + " " + sentence
                else:
                    current_chunk = sentence
            else:
                current_chunk = sentence
        else:
            current_chunk = (current_chunk + " " + sentence) if current_chunk else sentence
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text]


def process_jsonl_files():
    """Apply optimized chunking to all JSONL files."""
    extracts_dir = Path("./data/raw_extracts")
    jsonl_files = list(extracts_dir.glob("*.jsonl"))
    
    if not jsonl_files:
        print("\n✗ No JSONL files found")
        return
    
    print(f"\n[OPTIMIZED CHUNKING]")
    print(f"Processing {len(jsonl_files)} JSONL files")
    print(f"Settings: {MAX_CHUNK_CHARS}px max, {OVERLAP_CHARS}px overlap")
    
    total_original = 0
    total_optimized = 0
    
    for jsonl_file in jsonl_files:
        original_count = 0
        optimized_count = 0
        optimized_chunks = []
        
        # Read original chunks
        with open(jsonl_file) as f:
            for line in f:
                chunk = json.loads(line)
                original_count += 1
                
                # Re-chunk if it's text content
                if chunk.get("modality") == "text" or "content" in chunk:
                    content = chunk.get("content", "")
                    if len(content) > MAX_CHUNK_CHARS:
                        # Split and re-create chunks
                        for sub_content in chunk_text_with_overlap(content):
                            new_chunk = chunk.copy()
                            new_chunk["content"] = sub_content
                            optimized_chunks.append(new_chunk)
                            optimized_count += 1
                    else:
                        optimized_chunks.append(chunk)
                        optimized_count += 1
                else:
                    optimized_chunks.append(chunk)
                    optimized_count += 1
        
        # Write optimized chunks
        with open(jsonl_file, 'w') as f:
            for chunk in optimized_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        
        print(f"  {jsonl_file.name}: {original_count} → {optimized_count} chunks")
        total_original += original_count
        total_optimized += optimized_count
    
    print(f"\nTotal: {total_original} → {total_optimized} chunks")


def main():
    print("=" * 80)
    print("PHASE 2: Intelligent Filtering + Optimized Chunking")
    print("=" * 80)
    
    # Filter assets
    kept, discarded = filter_assets()
    
    # Optimize chunking
    process_jsonl_files()
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ PHASE 2 COMPLETE")
    print("=" * 80)
    print(f"Assets: {kept} kept, {discarded} discarded")
    print("\nNext steps:")
    print("  1. Process remaining files (PCWorld, Combat Aircraft)")
    print("  2. Clear Qdrant collection")
    print("  3. Ingest all data")
    print("  4. Run validation queries")


if __name__ == "__main__":
    main()
