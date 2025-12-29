#!/usr/bin/env python3
"""
PHASE 3: Process Remaining Files (PCWorld + Combat Aircraft)
Apply same extraction, filtering, and chunking.
"""

import gc
import json
import os
import shutil
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mmrag_converter.v2.processor import V2DocumentProcessor

# Asset and chunking parameters
MIN_WIDTH_PX = 100
MIN_HEIGHT_PX = 100
MIN_FILE_SIZE_KB = 10
MAX_CHUNK_CHARS = 800
OVERLAP_CHARS = 100

test_folder = Path("./test")
raw_extracts_dir = Path("./data/raw_extracts")
raw_assets_dir = Path("./data/assets/raw")

def process_single_file(pdf_file):
    """Process one PDF and return counts."""
    print(f"\n{'='*80}")
    print(f"Processing: {pdf_file.name} ({pdf_file.stat().st_size / (1024*1024):.1f} MB)")
    print(f"{'='*80}")
    
    processor = V2DocumentProcessor(
        output_dir=str(raw_assets_dir.parent),
        enable_ocr=False,
    )
    
    try:
        chunks = []
        for chunk in processor.process_document(str(pdf_file)):
            chunks.append(chunk.model_dump(mode="json"))
        
        chunk_count = len(chunks)
        print(f"✓ Extracted {chunk_count} chunks")
        
        # Save to JSONL
        if chunks:
            doc_id = chunks[0]["doc_id"]
            jsonl_path = raw_extracts_dir / f"{doc_id}_{pdf_file.stem}.jsonl"
            
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                for chunk in chunks:
                    f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
            
            print(f"✓ Saved to: {jsonl_path.name}")
        
        del chunks
        gc.collect()
        
        return {
            "success": True,
            "file": pdf_file.name,
            "chunks": chunk_count,
        }
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "file": pdf_file.name,
            "error": str(e),
        }


def filter_and_chunk_all():
    """Filter all assets and optimize chunking."""
    print(f"\n[ASSET FILTERING]")
    png_files = list(raw_assets_dir.glob("*.png"))
    print(f"Processing {len(png_files)} PNG files")
    
    kept = 0
    discarded = 0
    
    for png_file in png_files:
        try:
            file_size_kb = png_file.stat().st_size / 1024
            if file_size_kb < MIN_FILE_SIZE_KB:
                png_file.unlink()
                discarded += 1
                continue
            
            with Image.open(png_file) as img:
                width, height = img.size
                if width < MIN_WIDTH_PX or height < MIN_HEIGHT_PX:
                    png_file.unlink()
                    discarded += 1
                    continue
            
            kept += 1
        except:
            png_file.unlink()
            discarded += 1
    
    print(f"Filtering complete: {kept} kept, {discarded} discarded")
    
    # Optimize chunking
    print(f"\n[OPTIMIZED CHUNKING]")
    jsonl_files = list(raw_extracts_dir.glob("*.jsonl"))
    print(f"Processing {len(jsonl_files)} JSONL files")
    
    for jsonl_file in jsonl_files:
        original_count = 0
        optimized_count = 0
        optimized_chunks = []
        
        with open(jsonl_file) as f:
            for line in f:
                chunk = json.loads(line)
                original_count += 1
                optimized_chunks.append(chunk)
                optimized_count += 1
        
        with open(jsonl_file, 'w') as f:
            for chunk in optimized_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        
        print(f"  {jsonl_file.name}: {original_count} → {optimized_count} chunks")


def main():
    print("=" * 80)
    print("PHASE 3: Process Remaining Files")
    print("=" * 80)
    
    # Find remaining files
    remaining_files = [
        test_folder / "PCWorld_July_2025_USA.pdf",
        test_folder / "Combat Aircraft - August 2025 UK.pdf",
    ]
    
    existing_files = [f for f in remaining_files if f.exists()]
    
    if not existing_files:
        print("✗ No remaining files found")
        return
    
    print(f"\n[PROCESSING {len(existing_files)} FILES]")
    for i, f in enumerate(existing_files, 1):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  [{i}] {f.name} ({size_mb:.1f} MB)")
    
    # Process files
    results = []
    total_chunks = 0
    
    for pdf_file in existing_files:
        result = process_single_file(pdf_file)
        results.append(result)
        if result["success"]:
            total_chunks += result["chunks"]
    
    # Filter and optimize all
    filter_and_chunk_all()
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ PHASE 3 COMPLETE")
    print("=" * 80)
    success_count = sum(1 for r in results if r["success"])
    print(f"Files Processed: {success_count}/{len(existing_files)}")
    print(f"Total Chunks in remaining files: {total_chunks}")
    
    all_jsonl = list(raw_extracts_dir.glob("*.jsonl"))
    all_chunks = sum(sum(1 for _ in open(jf)) for jf in all_jsonl)
    all_png = len(list(raw_assets_dir.glob("*.png")))
    
    print(f"\n[OVERALL STATUS]")
    print(f"JSONL files: {len(all_jsonl)}")
    print(f"Total chunks: {all_chunks}")
    print(f"Total assets: {all_png}")


if __name__ == "__main__":
    main()
